from .clients import get_judge_async_client, get_judge_client

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
            model=OpenAIBaseLLM(judge, get_judge_client(), get_judge_async_client())
        )
    }

# criteria="Determine whether the actual output is factually correct based on the expected output.",
#     # NOTE: you can only provide either criteria or evaluation_steps, and not both
#     evaluation_steps=[
#         "Check whether the facts in 'actual output' contradicts any facts in 'expected output'",
#         "You should also heavily penalize omission of detail",
#         "Vague language, or contradicting OPINIONS, are OK"
#     ],