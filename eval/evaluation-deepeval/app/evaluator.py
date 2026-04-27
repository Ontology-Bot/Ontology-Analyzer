from deepeval import evaluate
from deepeval.test_case import LLMTestCase
from deepeval.evaluate import ErrorConfig, DisplayConfig
from deepeval.evaluate.types import EvaluationResult

from dataclasses import dataclass
from pathlib import Path

import logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


from app.testcase_loader import read_testcases
from app.metrics import construct_metrics
from app.llm_adapter import LLMAdapter, LLMUsage, test_connection, build_llm_adapter, LLMAdapterSettings
from app.llm_cache import LLMCache
from app.metrics_impl.judge_wrapper import OpenAIBaseLLM, StubLLM

from app.repo.snapshot import Snapshot, EvaluationRequest, EvaluationTracker
from app.repo.repository import Repository


def _test_model_throw(client: LLMAdapter, model_name: str):
    err = client.test_model(model_name)
    if err:
        raise ValueError(f"ping model error '{model_name}': {err}")

@dataclass
class EvaluatorSettings:
    data_dir: str
    do_cache: bool
    judge: LLMAdapterSettings
    subject: LLMAdapterSettings
    dataset_file: str = "golden-dataset.json"

class Evaluator:
    def __init__(self, settings: EvaluatorSettings) -> None:
        self._is_running = False
        # open dir from settings and make sure it exists
        self.path = Path(settings.data_dir)
        self.path.mkdir(exist_ok=True, parents=True)
        #
        self._judge_cache = LLMCache(self.path / "judge_cache") if settings.do_cache else None
        self._subject_cache = LLMCache(self.path / "subject_cache") if settings.do_cache else None
        #
        self.reset_connection(settings.subject, settings.judge)
        # load repo
        self.repo = Repository(self.path / "repo")
        self.tracker: EvaluationTracker | None = None
        self.last_error: str | None = None
        head = self.repo.get_at_head()
        if self.repo.repo_id is None or head is None:
            self.load_testcases(read_testcases(self.path / "golden-dataset.json"))
        else:
            self.snapshot = head

    def is_running(self) -> bool:
        return self._is_running

    def reset_connection(self, subject: LLMAdapterSettings, judge: LLMAdapterSettings):
        self._subject = build_llm_adapter(subject, self._subject_cache)
        self._judge = build_llm_adapter(judge, self._judge_cache)

    def get_connection_status(self):
        return {
            "subject": test_connection(self._subject),
            "judge": test_connection(self._judge),
        }
    
    def get_metric_names(self):
        metrics = construct_metrics(StubLLM(""))
        return list(metrics.keys()) if metrics else []
    
    def load_testcases(self, testcases: dict, task: EvaluationRequest | None = None):
        self.snapshot = Snapshot.from_dataset(self.repo.get_at_head(), task, testcases)
        self.repo.commit(self.snapshot)

    def add_models(self, models: list[str]):
        self.snapshot = Snapshot.from_task(self.snapshot, self.snapshot.task.model_copy(update={"models": models, "tests": []}))  # do not mark tests pending on add
        self.repo.commit(self.snapshot)
    
    def run_evaluation(self, task: EvaluationRequest):
        if self._is_running:
            logger.error("Already running")
            return

        self.last_error = None
        self._is_running = True
        try:
            # validate input
            if len(task.metrics) == 0:
                raise ValueError("no metrics providen")
            # judge must be available
            _test_model_throw(self._judge, task.judge)
            judge_wrapper = OpenAIBaseLLM(task.judge, self._judge, task.invalidate_cache)
            # build metric list
            metrics = construct_metrics(judge_wrapper, task.metrics)

            # create new snapshot
            if self.snapshot is None:
                raise ValueError("No snapshot loaded")
            snapshot = Snapshot.from_task(self.snapshot, task)

            self.tracker = EvaluationTracker(
                request=task,
                snapshot=snapshot
            )
            # for each model
            for model in task.models:
                self.tracker.set_current_model(model)
                deepeval_cases = []
                for test_id, testcase in self.tracker.get_current_tests().items():
                    body = self.tracker.get_test_body(test_id)
                    output = testcase.output  # not nice (tracker must expose readonly test body) TODO
                    error = None
                    usage = None  # TODO
                    # do completions
                    if not output:
                        try:
                            output, usage = self._subject.chat_text(model, body.input, task.invalidate_cache)
                        except Exception as exc:
                            logger.exception("Invalid response from model %s", model)
                            error = str(exc)
                    else:
                        logger.info(f"Using preset output for model {model} test '{test_id}'")
                    # update tracker
                    self.tracker.set_test_generated(test_id, output=output, error=error)
                    # create testcase if not error
                    if output and not error:
                        deepeval_cases.append(
                            LLMTestCase(
                                name=test_id,
                                input=body.input,
                                actual_output=output,
                                expected_output=body.expected_output,
                                additional_metadata=usage.model_dump() if usage else None,
                                token_cost=usage.total_tokens if usage else None,
                                completion_time=usage.duration if usage else None
                            ))
                # run evaluation
                results = evaluate(
                    deepeval_cases,
                    list(metrics.values()),
                    error_config=ErrorConfig(ignore_errors=True),  # allow metrics to fail
                    display_config=DisplayConfig(show_indicator=False, print_results=False)
                )
                # put results
                for r in results.test_results:
                    self.tracker.set_test_result(r.name, r)

            self.repo.commit(self.tracker.snapshot)
            self.snapshot = self.tracker.snapshot
            self.last_error = None
            return self.tracker
        except Exception as exc:
            logger.exception("Evaluation failed")
            self.last_error = str(exc)
            return None
        finally:
            self._is_running = False