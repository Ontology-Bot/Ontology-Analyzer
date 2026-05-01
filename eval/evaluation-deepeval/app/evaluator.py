from deepeval import evaluate
from deepeval.evaluate import ErrorConfig
from deepeval.test_case import LLMTestCase

from dataclasses import dataclass
from typing import Any

import logging

from app.llm_adapter import LLMAdapterSettings, LLMUsage, build_llm_adapter, test_connection
from app.llm_cache import LLMCache
from app.metrics import construct_metrics
from app.metrics_impl.judge_wrapper import OpenAIBaseLLM, StubLLM
from app.testcase_loader import load_testcases

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


@dataclass
class EvaluatorSettings:
    data_dir: str
    do_cache: bool
    judge: LLMAdapterSettings
    subject: LLMAdapterSettings
    dataset_file: str = "golden-dataset.json"


class Evaluator:
    def __init__(self, settings: EvaluatorSettings) -> None:
        self.settings = settings
        self._testcases = load_testcases(f"{settings.data_dir}/{settings.dataset_file}")
        self._judge_cache = LLMCache(f"{settings.data_dir}/judge_cache") if settings.do_cache else None
        self._subject_cache = LLMCache(f"{settings.data_dir}/subject_cache") if settings.do_cache else None
        self.reset_connection(settings.subject, settings.judge)

    def get_config(self) -> EvaluatorSettings:
        return self.settings

    def set_testcases(self, testcases: list[dict]):
        self._testcases = testcases

    def get_testcases(self):
        return self._testcases

    def reset_connection(self, subject: LLMAdapterSettings, judge: LLMAdapterSettings):
        self._subject = build_llm_adapter(subject, self._subject_cache)
        try:
            self._judge = build_llm_adapter(judge, self._judge_cache)
        except ValueError:
            self._judge = None

    def get_connection_status(self):
        return {
            "subject": test_connection(self._subject),
            "judge": test_connection(self._judge) if self._judge else False,
        }

    def get_metric_names(self):
        return list(construct_metrics(StubLLM("")).keys())

    def _needs_subject_generation(self) -> bool:
        return any(testcase.get("output") is None for testcase in self._testcases)

    def _build_generated_case(self, testcase: dict[str, Any], output: str, usage: LLMUsage | None):
        return {
            "input": testcase["input"],
            "expected_output": testcase["expected_output"],
            "output": output,
            "duration": usage.duration if usage else None,
            "token_usage": usage.total_tokens if usage else None,
            "additional_metadata": usage.model_dump() if usage else None,
        }

    def prepare_subject_outputs(self, model: str, invalidate_cache: bool = True, tracker: dict[str, int] | None = None):
        if self._needs_subject_generation():
            err = self._subject.test_model(model)
            if err:
                raise ValueError(f"subject model error '{model}': {err}")

        generated_cases = []
        total_cases = len(self._testcases)
        for i, testcase in enumerate(self._testcases):
            if tracker:
                tracker["tests_generated"] += 1

            output = testcase.get("output")
            usage = LLMUsage(
                duration=testcase.get("duration"),
                total_tokens=testcase.get("token_usage"),
            )

            if output is None:
                logger.info(f"\tawaiting model completion for '{testcase['input']}' ({i}/{total_cases})")
                try:
                    output, usage = self._subject.chat_text(model, testcase["input"], invalidate_cache) or ("", LLMUsage())
                except Exception:
                    logger.exception(f"Invalid response from model {model}")
                    if tracker:
                        tracker["errors"] += 1
                    raise

            output = output or ""
            logger.info(f"\tgot response for '{testcase['input']}' ({i}/{total_cases})")
            generated_case = self._build_generated_case(testcase, output, usage)
            logger.info(f"\trecorded usage: {generated_case['additional_metadata']} for model '{model}'")
            generated_cases.append(generated_case)

        logger.info(f"completions for model '{model}' done")
        return generated_cases

    def create_test_results(self, generated_cases: list[dict[str, Any]]):
        return {
            "test_results": [
                {
                    "input": testcase["input"],
                    "actual_output": testcase["output"],
                    "expected_output": testcase["expected_output"],
                    "additional_metadata": testcase["additional_metadata"],
                    "token_cost": testcase["token_usage"],
                    "completion_time": testcase["duration"],
                }
                for testcase in generated_cases
            ]
        }

    def run_evaluation(self, judge: str, model: str, metric_list: list[str], invalidate_cache: bool = True, tracker: dict[str, int] | None = None):
        if len(metric_list) == 0:
            raise ValueError("no metrics providen")
        if self._judge is None:
            raise ValueError("judge adapter not configured")

        judge_wrapper = OpenAIBaseLLM(judge, self._judge, invalidate_cache)
        metrics = construct_metrics(judge_wrapper)

        err = self._judge.test_model(judge)
        if err:
            raise ValueError(f"judge model error '{judge}': {err}")

        generated_cases = self.prepare_subject_outputs(model, invalidate_cache, tracker)
        deepeval_cases = []
        for testcase in generated_cases:
            deepeval_cases.append(
                LLMTestCase(
                    input=testcase["input"],
                    actual_output=testcase["output"],
                    expected_output=testcase["expected_output"],
                    additional_metadata=testcase["additional_metadata"],
                    token_cost=testcase["token_usage"],
                    completion_time=testcase["duration"],
                )
            )

        selected_metrics = []
        for name in metric_list:
            if name not in metrics:
                raise ValueError(f"Unknown metric '{name}'")
            selected_metrics.append(metrics[name])

        results = evaluate(
            deepeval_cases,
            selected_metrics,
            error_config=ErrorConfig(ignore_errors=True),
        )

        if tracker:
            tracker["tests_ran"] += len(deepeval_cases)
            for tr in results.test_results:
                for mr in tr.metrics_data or []:
                    if mr.error:
                        tracker["errors"] += 1

        return results