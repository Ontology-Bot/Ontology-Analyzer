import re
from deepeval.metrics import BaseMetric
from deepeval.test_case import LLMTestCase

class SimpleNumericMatchMetric(BaseMetric):

    def __init__(
        self,
        threshold: float = 0.5,
    ):
        self.threshold = threshold
        self.include_reason = True

    @property
    def __name__(self): # type: ignore
        return "Simple Numeric Match Metric"
    
    def _score(self, test_case: LLMTestCase) -> tuple[float, str]:
        gt_numbers = re.findall(r"\d+\.?\d*", test_case.expected_output or "")
        pred_numbers = re.findall(r"\d+\.?\d*", test_case.actual_output or "")

        if not gt_numbers:
            return 1.0, "No numbers to check"
        
        if gt_numbers == pred_numbers:
            return 1.0, "Numbers match" 
        return 0.0, "Numbers do not match"


    def measure(self, test_case: LLMTestCase):
        try:
            self.score, reason = self._score(test_case)

            if self.include_reason:
                self.reason = reason
            self.success = self.score >= self.threshold
            return self.score
        except Exception as e:
            # set metric error and re-raise it
            self.error = str(e)
            raise

    async def a_measure(self, test_case: LLMTestCase) -> float:
        return self.measure(test_case)
    
    def is_successful(self) -> bool:
        if self.error is not None:
            self.success = False
        else:
            try:
                self.success = (self.score or 0) >= self.threshold
            except TypeError:
                self.success = False
        return self.success
        

        