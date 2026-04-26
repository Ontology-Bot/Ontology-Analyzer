from datetime import datetime
from typing import Literal
from pydantic import BaseModel

from collections import defaultdict
from copy import deepcopy

from deepeval.evaluate.types import EvaluationResult, TestResult

import logging
logger = logging.getLogger(__name__)


class EvaluationSummary(BaseModel):
    errors: int = 0
    tests_evaluated: int = 0
    tests_generated: int = 0
    tests_ready: int = 0
    total: int = 0
    current_model: str | None = None

class EvaluationRequest(BaseModel):
    judge: str
    models: list[str]
    metrics: list[str]
    tests: list[str] | None = None
    invalidate_cache: bool = False

    @classmethod
    def empty(cls):
        return cls(judge="", models=[], metrics=[])

class EvaluatedTestResult(BaseModel):
    '''
    Small Proxy for model x test 
    '''
    test_id: str
    status: Literal["cached", "pending", "generated", "pass", "fail", "error"]
    output: str | None = None
    result: TestResult | None = None
    error: str | None = None


class TestCase(BaseModel):
    '''
    Test inside json has:
    {
      "name": "<uid>",
      "input": "<question>",
      "expected_output": "<answer>",
      "label": "<dataset label>",
    }
    '''
    name: str
    input: str
    expected_output: str
    label: str
    idx: int | None = None

    def get_key(self) -> str:
        return f"{self.input}|{self.expected_output}"


class Snapshot(BaseModel):
    ''' This class is a full snapshot
    '''
    repo_id: str
    timestamp: datetime
    task: EvaluationRequest # immutable
    tests: dict[str, TestCase] # test case bodies, immutable
    models: dict[str, dict[str, EvaluatedTestResult]] # results per model
    
    @classmethod
    def same(cls, s1: "Snapshot", s2: "Snapshot") -> bool:
        if s1.repo_id != s2.repo_id:
            return False
        if len(s1.tests) != len(s2.tests):
            return False
        old_tests = {t.get_key() for t in s1.tests.values()}
        new_tests = {t.get_key() for t in s2.tests.values()}
        return old_tests == new_tests
    
    @staticmethod
    def _build_model_results(
        prev: "Snapshot | None", 
        target_models: list[str], # requested models for display
        current_tests: dict[str, TestCase], # full list of tests
        ids_to_run: set[str] # tests 
    ) -> dict[str, dict[str, EvaluatedTestResult]]:
        """
        generic logic to carry over results or initialize new ones.
        """
        output = {}
        prev_models = prev.models if prev else {}

        for model_id in target_models: # for each model
            model_results = {} 
            existing_results = prev_models.get(model_id, {})

            for t_id, test in current_tests.items(): # each test
                is_pending = t_id in ids_to_run
                
                if not is_pending and t_id in existing_results:
                    # carry over existing result
                    model_results[t_id] = existing_results[t_id].model_copy()
                else:
                    # create stub for execution
                    model_results[t_id] = EvaluatedTestResult(
                        test_id=test.name, # carry over new test name
                        status="pending" if is_pending else "cached"
                    )
            output[model_id] = model_results
            
        return output

    @classmethod
    def from_dataset(cls, prev: "Snapshot | None", task: EvaluationRequest | None, dataset: dict) -> "Snapshot":
        repo_id = dataset.get("name")
        if not repo_id:
            raise ValueError("Invalid dataset - no name provided")
        if prev and prev.repo_id != repo_id:
            raise ValueError("Repo ID mismatch")
        # Set task - try carry over from prev, otherwise use empty task
        if task is None:
            if prev:
                task = prev.task
            else:
                logger.warning("No task provided for new dataset and no previous snapshot found - using empty task")
                task = EvaluationRequest.empty()
        # init from dataset 
        merged_tests: dict[str, TestCase] = {}
        content_to_new: dict[str, TestCase] = {}
        
        for i, t in enumerate(dataset.get("tests", [])):
            test_obj = TestCase.model_validate({**t, "idx": i}) # validate schema
            
            if test_obj.name in merged_tests: # catch duplicates
                raise ValueError(f"Duplicate test name found in dataset: {test_obj.name}")
            
            merged_tests[test_obj.name] = test_obj # save by name
            content_to_new[test_obj.get_key()] = test_obj # and by key (to detect renaming)

        if prev:
            for old_test in prev.tests.values():
                match = content_to_new.get(old_test.get_key())
                if match and match.name != old_test.name:
                    # pop new test & store it under old name (to be able to resolve later)
                    merged_tests[old_test.name] = merged_tests.pop(match.name)
        
        return cls(
            repo_id=repo_id,
            timestamp=datetime.now(),
            task=task,
            tests=merged_tests,
            models=cls._build_model_results(prev, task.models, merged_tests, set()) # mark all as cached
        )

    @classmethod
    def from_task(cls, prev: "Snapshot", task: EvaluationRequest) -> "Snapshot":
        # if tests_to_run is None - run everything from prev
        run_set = set(task.tests) if task.tests is not None else set(prev.tests.keys())

        return cls(
            repo_id=prev.repo_id,
            timestamp=datetime.now(),
            task=task,
            tests=prev.tests,
            models=cls._build_model_results(prev, task.models, prev.tests, run_set)
        )
    
    def to_dataset(self):
        return {
            "name": self.repo_id,
            "tests": self.tests
        }
        


class EvaluationTracker:
    def __init__(self, request: EvaluationRequest, snapshot: Snapshot):
        self.snapshot = snapshot
        self.request = request
        # When tests is None, run every test in the snapshot (same semantics as Snapshot.from_task).
        self.test_set = set(request.tests) if request.tests is not None else set(snapshot.tests.keys())
        self.summary = EvaluationSummary(total=len(self.test_set) * len(request.models))
        self.current_tests: dict[str, EvaluatedTestResult] | None = None
        self.failed: set[str] = set()

    def set_current_model(self, model: str):
        self.summary.current_model = model
        self.current_tests = {k: v for k, v in self.snapshot.models[self.summary.current_model].items() if k in self.test_set}

    def get_current_tests(self) -> dict[str, EvaluatedTestResult]:
        if self.current_tests is None:
            raise ValueError("Required to run test without a model set")
        return self.current_tests
    
    def get_test_body(self, test_id: str) -> TestCase:
        if test_id not in self.snapshot.tests:
            raise ValueError(f"Test with id '{test_id}' not found in snapshot")
        return self.snapshot.tests[test_id]

    def _get_test_throw(self, test_id: str) -> EvaluatedTestResult:
        if self.current_tests is None:
            raise ValueError("Required to run test without a model set")
        if test_id not in self.snapshot.tests:
            raise ValueError(f"Test with id '{test_id}' not found in snapshot")
        return self.current_tests[test_id]

    def set_test_generated(self, test_id: str, output: str | None, error: str | None):
        tracker = self._get_test_throw(test_id)
        if output is None and error is None:
            logger.warning(f"Setting test result for '{test_id}' without result or error - error asumed")
            tracker.status = "error"
            self.summary.errors += 1
        if error is not None:
            tracker.status = "error"
            tracker.error = error
            self.summary.errors += 1
        if output is not None:
            tracker.status = "generated"
            tracker.output = output
            self.summary.tests_generated += 1
            
        logger.info(f"\t{tracker.status} at '{test_id}' for model '{self.summary.current_model}' ({self.summary.tests_generated}/{self.summary.total})")

    def set_test_result(self, test_id: str, result: TestResult | None = None, error: str | None = None):
        tracker = self._get_test_throw(test_id)
        if result and result.metrics_data:
            for md in result.metrics_data:
                error = error or md.error
        if error is not None:
            tracker.status = "error"
            self.summary.errors += 1
        if result:
            tracker.result = result
            tracker.status = "pass" if result.success else "fail"
            self.summary.tests_evaluated += 1
        if result is None and error is None:
            logger.warning(f"Setting test result for '{test_id}' without result or error - error asumed")
            tracker.status = "error"
            self.summary.errors += 1

        logger.info(f"\t{tracker.status} at '{test_id}' for model '{self.summary.current_model}' ({self.summary.tests_evaluated}/{self.summary.total})")

