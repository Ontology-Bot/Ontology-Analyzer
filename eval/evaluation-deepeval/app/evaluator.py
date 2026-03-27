from deepeval import evaluate
from deepeval.test_case import LLMTestCase

from .testcase_loader import get_testcases
from .metrics import get_metrics
from .clients import get_subject_client

import logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def run_evaluation(judge: str, model: str, metric_list: list[str], tracker: dict[str, int] | None = None):
    testcases = get_testcases()
    metrics = get_metrics(judge)

    # get model responces and create deepeval cases
    deepeval_cases = []
    for i, testcase in enumerate(testcases):
        if "output" in testcase:
            output = testcase["output"]
        else:
            logger.info(f"\tawaiting model completion for '{testcase['input']}' ({i}/{len(testcases)})")
            if tracker:
                tracker["tests_generated"] += 1

            # response = get_subject_client().responses.create(
            #     model=model,
            #     input=testcase["input"],
            # )
            # output = response.output_text

            # use standard API - new one might be not available
            response = None
            try:
                response = get_subject_client().chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "user", "content": testcase["input"]}
                    ]
                )
            except Exception as e:
                logger.exception(e)
                raise
            if not response:
                logger.error("Invalid response")

            output = response.choices[0].message.content or ""

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
    results = evaluate(deepeval_cases, selected_metrics)

    if tracker:
        tracker["tests_ran"] += len(deepeval_cases)

    return results