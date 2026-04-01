from deepeval.metrics import GEval
from deepeval.models import DeepEvalBaseLLM
from deepeval.test_case import LLMTestCaseParams

from app.metrics_impl.numeric_match_metric import SimpleNumericMatchMetric

def construct_metrics(judge_wrapper: DeepEvalBaseLLM):
    return {
        "simple_numeric": SimpleNumericMatchMetric(),
        "geval": GEval(
            name="Correctness",
            criteria="Determine whether the actual output is factually correct based on the expected output.",
            evaluation_params=[LLMTestCaseParams.INPUT, LLMTestCaseParams.ACTUAL_OUTPUT, LLMTestCaseParams.EXPECTED_OUTPUT],
            model=judge_wrapper
        )
    }

# criteria="Determine whether the actual output is factually correct based on the expected output.",
#     # NOTE: you can only provide either criteria or evaluation_steps, and not both
#     evaluation_steps=[
#         "Check whether the facts in 'actual output' contradicts any facts in 'expected output'",
#         "You should also heavily penalize omission of detail",
#         "Vague language, or contradicting OPINIONS, are OK"
#     ],