from datetime import datetime
from typing import Literal
from pydantic import BaseModel

from deepeval.evaluate.types import EvaluationResult, TestResult

class EvaluationSummary(BaseModel):
    errors: int = 0
    tests_ran: int = 0
    tests_generated: int = 0
    total: int = 0
    current_model: str | None = None

class EvaluationRequest(BaseModel):
    judge: str
    models: list[str]
    metrics: list[str]
    invalidate_cache: bool = False

class EvaluatedTestResult(BaseModel):
    '''
    Test inside json has:
    {
      "name": "<uid>",
      "input": "<question>",
      "expected_output": "<answer>",
      "label": "<dataset label>",
      "output": "[opt] <model output>",
    }
    '''
    test_id: str
    status: Literal["cached", "pending","generating","evaluating", "done", "error"]
    body: dict
    result: list[TestResult] | None = None
    error: str | None = None

    def get_key(self) -> str:
        return f"{self.body.get('input', '')}|{self.body.get('expected_output', '')}"



class Snapshot(BaseModel):
    ''' This class is a full snapshot
    '''
    repo_id: str
    timestamp: datetime
    tests: dict[str, EvaluatedTestResult]

    @classmethod
    def from_dataset(cls, dataset: dict):
        repo_id = dataset.get("name", "default")
        tests = dataset.get("tests", [])
        r_tests: dict[str, EvaluatedTestResult] = {}
        for t in tests:
            test_id = t.get("name", None)
            if not test_id:
                raise ValueError("Each test must have a 'name' field as unique identifier")
            r_tests[test_id] = EvaluatedTestResult(
                test_id=test_id,
                status="cached",
                body=t,
                result=None,
                error=None
            )
        return cls(
            repo_id=repo_id,
            timestamp=datetime.now(),
            tests=r_tests
        )
    
    @classmethod
    def same(cls, s1: "Snapshot", s2: "Snapshot") -> bool:
        if s1.repo_id != s2.repo_id:
            return False
        if len(s1.tests) != len(s2.tests):
            return False
        old_tests = {t.get_key() for t in s1.tests.values()}
        new_tests = {t.get_key() for t in s2.tests.values()}
        return old_tests == new_tests

    @classmethod
    def merge(cls, prev: "Snapshot", new: "Snapshot"):
        if prev.repo_id != new.repo_id:
            raise ValueError("Cannot merge snapshots with different repo_id")
        old_tests = {t.get_key(): t for t in prev.tests.values()}
        merged_tests: dict[str, EvaluatedTestResult] = {}
        for test_id, test in new.tests.items():
            old_test = old_tests.get(test.get_key())
            if old_test is None:
                # new test
                merged_tests[test_id] = test
                continue
            # core of the test is the same -> update body
            old_test.test_id = test_id # update test_id to new one
            old_test.body = test.body # update body to new one
            merged_tests[test_id] = old_test
        return cls(
            repo_id=prev.repo_id,
            timestamp=datetime.now(),
            tests=merged_tests
        )
    

    @classmethod
    def from_testlist(cls, prev: "Snapshot", tests: list[str] | None):
        if tests is None:
            # full copy
            return cls(
                repo_id=prev.repo_id,
                timestamp=datetime.now(),
                tests=prev.tests
            )
        # copy from prev, if in tests -> "pending", else "cached"
        tests_to_run = set(tests)
        r_tests = {}
        for test_id, test in prev.tests.items():
            to_run = test_id in tests_to_run
            status = "pending" if to_run else "cached"
            r_tests[test_id] = EvaluatedTestResult(
                test_id=test_id,
                status=status,
                body=test.body,
                result=test.result if not to_run else None,
                error=test.error if not to_run else None
            )
        return cls(
            repo_id=prev.repo_id,
            timestamp=datetime.now(),
            tests=r_tests
        )
    
    def to_json_model(self):
        return self.model_dump(mode="json")
    
    def to_dataset(self):
        return {
            "name": self.repo_id,
            "tests": [t.body for t in self.tests.values()]
        }
        


class EvaluationTracker:
    def __init__(self, request: EvaluationRequest, snapshot: Snapshot, tests: list[str] | None):
        self.summary = EvaluationSummary(total=(len(tests or []) * len(request.models)))
        self.snapshot = snapshot    
        self.request = request

    def set_current_model(self, model: str):
        self.summary.current_model = model

    def _get_test_throw(self, test_id: str) -> EvaluatedTestResult:
        if test_id not in self.snapshot.tests:
            raise ValueError(f"Test with id '{test_id}' not found in snapshot")
        return self.snapshot.tests[test_id]

    def set_test_status(self, test_id: str, status: Literal["pending","generating","evaluating"], body: dict | None = None):
        test = self._get_test_throw(test_id)
        test.status = status
        if body is not None:
            test.body = {**test.body, **body}

    def set_test_result(self, test_id: str, result: EvaluationResult | str):
        test = self._get_test_throw(test_id)
        # handle errors
        error: str | None = result.test_results .get("error", None)
        cnt = 1 if error else 0
        for md in result.get("metrics_data", []):
            if md.get("error", None):
                error = error or md.get("error")
                cnt += 1
        error = f"{error}{f' ({cnt-1} more)' if cnt > 1 else ''}" if error else None
        #
        test.result = result.test_results
        if error:
            test.status = "error"
            test.error = error
        else:
            test.status = "done"
            test.error = None

