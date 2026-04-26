from deepeval.metrics import GEval
from deepeval.models import DeepEvalBaseLLM
from deepeval.test_case import LLMTestCaseParams

from app.metrics_impl.numeric_match_metric import SimpleNumericMatchMetric

def construct_metrics(judge_wrapper: DeepEvalBaseLLM, metric_names: list[str] | None = None):
    all_metrics = {
        "simple_numeric": SimpleNumericMatchMetric(),
        "geval": GEval(
            name="Correctness",
            criteria="Determine whether the actual output is factually correct based on the expected output.",
            evaluation_params=[LLMTestCaseParams.INPUT, LLMTestCaseParams.ACTUAL_OUTPUT, LLMTestCaseParams.EXPECTED_OUTPUT],
            model=judge_wrapper
        )
    }
    if metric_names is None:
        return all_metrics
    metrics: dict = {}
    for m in metric_names:
        if m in all_metrics:
            metrics[m] = all_metrics[m]
        else:
            raise ValueError(f"unknow metric name {m}")
    return metrics

# criteria="Determine whether the actual output is factually correct based on the expected output.",
#     # NOTE: you can only provide either criteria or evaluation_steps, and not both
#     evaluation_steps=[
#         "Check whether the facts in 'actual output' contradicts any facts in 'expected output'",
#         "You should also heavily penalize omission of detail",
#         "Vague language, or contradicting OPINIONS, are OK"
#     ],