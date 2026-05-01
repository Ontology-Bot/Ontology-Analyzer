from datetime import datetime
from typing import Literal
from pydantic import BaseModel, model_validator

from copy import deepcopy

from deepeval.evaluate.types import TestResult

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
    refresh_subject: bool = False
    refresh_judge: bool = False

    @model_validator(mode="before")
    @classmethod
    def _migrate_invalidate_cache(cls, value):
        if not isinstance(value, dict):
            return value
        if "refresh_subject" in value or "refresh_judge" in value:
            return value
        if "invalidate_cache" not in value:
            return value
        migrated = dict(value)
        legacy_refresh = bool(migrated.get("invalidate_cache", False))
        migrated["refresh_subject"] = legacy_refresh
        migrated["refresh_judge"] = legacy_refresh
        return migrated


class EvaluatedTestResult(BaseModel):
    '''
    Small Proxy for model x test 
    '''
    test_id: str
    status: Literal["cached", "pending", "generated", "pass", "fail", "error"]
    output: str | None = None
    result: TestResult | None = None
    error: str | None = None
    duration: float | None = None
    token_usage: int | None = None


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
    def filter_present_keys(
        tests: list[str] | None,
        valid_keys: set[str],
    ) -> tuple[list[str] | None, list[str]]:
        """If tests is None, return (None, []). Else intersection (sorted) and unknown ids (sorted)."""
        if tests is None:
            return None, []
        requested = set(tests)
        return sorted(requested & valid_keys), sorted(requested - valid_keys)

    @staticmethod
    def _build_model_results(
        models: list[str] | None,  # models to run (none for all)
        tests: list[str] | None,  # tests to run (None = all tests; [] = none pending, all cached)
        current_models: dict[str, dict[str, EvaluatedTestResult]],  # full list of models with results
        current_tests: dict[str, TestCase],  # full list of tests
    ) -> dict[str, dict[str, EvaluatedTestResult]]:
        """
        generic logic to carry over results or initialize new ones.
        """
        all_models = set(current_models.keys())
        all_tests = set(current_tests.keys())
        # resolve models and tests to run - if not provided, run all
        run_tests = set(tests) if tests is not None else all_tests
        run_models = set(models) if models is not None else all_models

        # resolve unknown tests - ignore (drop ids that are not in the current test list)
        unknown_tests = run_tests - all_tests
        if unknown_tests:
            logger.warning("Ignoring unknown tests for snapshot: %s", sorted(unknown_tests))
            run_tests -= unknown_tests

        # resolve unknown models - append
        new_models = run_models - all_models
        if new_models:
            logger.info("Adding new models to snapshot: %s", sorted(new_models))
            all_models |= run_models

        # build on top of existing results
        output = deepcopy(current_models)
        for model_id in all_models:
            is_selected = model_id in run_models
            results = output.setdefault(model_id, {})

            # test got removed from snapshot — drop stale rows
            for stale_id in list(results.keys()):
                if stale_id not in all_tests:
                    del results[stale_id]

            for test_id, test in current_tests.items():
                is_pending = is_selected and test_id in run_tests
                existing = results.get(test_id)
                if is_pending or not existing:  # cant carry over old result
                    results[test_id] = EvaluatedTestResult(
                        test_id=test.name,  # carry over new test name
                        status="pending" if is_pending else "cached",
                        output=existing.output if existing else None,  # carry over output if any
                        duration=existing.duration if existing else None,
                        token_usage=existing.token_usage if existing else None,
                    )

        return output

    @classmethod
    def from_dataset(cls, prev: "Snapshot | None", dataset: dict) -> "Snapshot":
        repo_id = dataset.get("name")
        if not repo_id:
            raise ValueError("Invalid dataset - no name provided")
        if prev and prev.repo_id != repo_id:
            raise ValueError("Repo ID mismatch")
        # Task always comes from the prior snapshot; first commit uses a placeholder until evaluate/config.
        task = prev.task if prev else EvaluationRequest(judge="", models=[], metrics=[])
        # init tests from dataset
        merged_tests: dict[str, TestCase] = {}
        content_to_new: dict[str, TestCase] = {}
        
        for i, t in enumerate(dataset.get("tests", [])):
            test_obj = TestCase.model_validate({**t, "idx": i, "output": None}) # validate schema
            
            if test_obj.name in merged_tests: # catch duplicates
                raise ValueError(f"Duplicate test name found in dataset: {test_obj.name}")
            
            merged_tests[test_obj.name] = test_obj # save by name
            content_to_new[test_obj.get_key()] = test_obj  # and by key (to detect renaming)

        if prev:
            for old_test in prev.tests.values():
                match = content_to_new.get(old_test.get_key())
                if match and match.name != old_test.name:
                    # pop new test & store it under old name (to be able to resolve later)
                    merged_tests[old_test.name] = merged_tests.pop(match.name)

        # Models to refresh: task list, any column from prev, optional dataset "model" field.
        models_for_merge = set(task.models)
        if prev:
            models_for_merge |= set(prev.models.keys())
        dataset_model = dataset.get("model")
        if dataset_model:
            models_for_merge.add(dataset_model)

        models_data = prev.models if prev else {}
        # [] => no pending rows; everything stays cached for the new test list.
        models_data = cls._build_model_results(list(models_for_merge), [], models_data, merged_tests)

        # inject model results
        if dataset_model:
            logger.info("Dataset has model '%s' — injecting into snapshot", dataset_model)
            if dataset_model not in task.models:
                logger.warning("Model '%s' was added to the task", dataset_model)
                task.models.append(dataset_model)
            # put results for this model
            model_results = models_data.setdefault(dataset_model, {})
            for i, t in enumerate(dataset.get("tests", [])):
                output = t.get("output")  # if output is set — override model output
                test_id = t.get("name")
                if output is not None and test_id in merged_tests:  # ensure that test exists
                    existing_result = model_results.get(test_id)
                    if existing_result is None or existing_result.output != output:
                        logger.debug(
                            "Injecting output for model '%s' test '%s'",
                            dataset_model,
                            test_id,
                        )
                        model_results[test_id] = EvaluatedTestResult(
                            test_id=test_id,
                            status="cached",
                            output=output,
                            duration=t.get("duration"),
                            token_usage=t.get("token_usage"),
                        )
                    else:
                        model_results[test_id].duration = t.get("duration")
                        model_results[test_id].token_usage = t.get("token_usage")


        return cls(
            repo_id=repo_id,
            timestamp=datetime.now(),
            task=task,
            tests=merged_tests,
            models=models_data,
        )

    @classmethod
    def from_task(cls, prev: "Snapshot", task: EvaluationRequest) -> "Snapshot":
        tests = set(prev.tests.keys())
        valid_tests, unknown_tests = cls.filter_present_keys(task.tests, tests)
        if unknown_tests:
            logger.warning("Ignoring unknown test ids not in snapshot: %s", unknown_tests)
        # New instance: avoids mutating caller / prev.task when they share the same object.
        task = task.model_copy(update={"tests": valid_tests})

        models_data = cls._build_model_results(
            task.models,
            valid_tests,
            prev.models,
            prev.tests,
        )
        return cls(
            repo_id=prev.repo_id,
            timestamp=datetime.now(),
            task=task,
            tests=prev.tests,
            models=models_data,
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
        tests = set(snapshot.tests.keys())
        valid_tests, unknown_tests = Snapshot.filter_present_keys(request.tests, tests)
        if unknown_tests:
            logger.warning(
                "EvaluationTracker: ignoring test ids not in snapshot: %s",
                unknown_tests,
            )
        self.test_set = set(valid_tests) if valid_tests is not None else tests
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

