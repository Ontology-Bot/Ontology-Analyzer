from deepeval import evaluate
from deepeval.test_case import LLMTestCase
from deepeval.evaluate import ErrorConfig

from dataclasses import dataclass

import logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


from app.testcase_loader import load_testcases
from app.metrics import construct_metrics
from app.llm_adapter import test_connection, build_llm_adapter, LLMAdapterSettings
from app.llm_cache import LLMCache
from app.metrics_impl.judge_wrapper import OpenAIBaseLLM, StubLLM

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
        self._judge = build_llm_adapter(judge, self._judge_cache)
        

    def get_connection_status(self):
        return {
            "subject": test_connection(self._subject),
            "judge": test_connection(self._judge),
        }
    
    def get_metric_names(self):
        return list(construct_metrics(StubLLM("")).keys())

    def run_evaluation(self, judge: str, model: str, metric_list: list[str], invalidate_cache: bool = True, tracker: dict[str, int] | None = None):
        judge_wrapper = OpenAIBaseLLM(judge, self._judge, invalidate_cache)
        metrics = construct_metrics(judge_wrapper)
        # validate input
        if len(metric_list) == 0:
            raise ValueError("no metrics providen")
        # check so both models are available
        err = self._subject.test_model(model)
        if err:
            raise ValueError(f"subject model error '{model}': {err}")
        err = self._judge.test_model(judge)
        if err:
            raise ValueError(f"judge model error '{judge}': {err}")

        # get model responces and create deepeval cases
        deepeval_cases = []
        for i, testcase in enumerate(self._testcases):
            output = testcase.get("output")
            
            if not output: # do completions
                logger.info(f"\tawaiting model completion for '{testcase['input']}' ({i}/{len(self._testcases)})")
                if tracker:
                    tracker["tests_generated"] += 1
                
                try:
                    output = self._subject.chat_text(model, testcase["input"], invalidate_cache) or ""
                except Exception as e:
                    import traceback
                    logger.error(f"Invalid response from model {model}")
                    logger.exception(traceback.print_exc())
                    output = ""
                    if tracker:
                        tracker["errors"] += 1
                    raise
            
            # create testcase
            deepeval_cases.append(LLMTestCase(
                input=testcase["input"],
                actual_output=output,
                expected_output=testcase["expected_output"],
            ))
        logger.info(f"completions for model '{model}' done")
            
        # select metrics
        selected_metrics = []
        for name in metric_list:
            if name not in metrics:
                raise ValueError(f"Unknown metric '{name}'")
            selected_metrics.append(metrics[name])

        # run evaluation
        results = evaluate(deepeval_cases, selected_metrics, error_config=ErrorConfig(
            ignore_errors=True # allow metrics to fail
        ))

        # update stats
        if tracker:
            tracker["tests_ran"] += len(deepeval_cases)

            for tr in results.test_results:
                for mr in tr.metrics_data or []:
                    if mr.error:
                        tracker["errors"] += 1

        return results