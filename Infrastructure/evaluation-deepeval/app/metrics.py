from .clients import judge_async_client, judge_client

from deepeval.metrics import GEval
from deepeval.test_case import LLMTestCaseParams

from app.metrics_impl.numeric_match_metric import SimpleNumericMatchMetric
from app.metrics_impl.judge_wrapper import OpenAIBaseLLM

def get_metrics(judge: str):
    return {
        "simple_numeric": SimpleNumericMatchMetric(),
        "geval": GEval(
            name="Correctness",
            criteria="Determine whether the actual output is factually correct based on the expected output.",
            evaluation_params=[LLMTestCaseParams.INPUT, LLMTestCaseParams.ACTUAL_OUTPUT, LLMTestCaseParams.EXPECTED_OUTPUT],
            model=OpenAIBaseLLM(judge, judge_client, judge_async_client)
        )
    }