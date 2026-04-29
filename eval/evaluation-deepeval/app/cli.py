import os
import sys
import json
import logging
from pathlib import Path
from dotenv import load_dotenv
import click

from app.config import get_config
from app.evaluator import Evaluator
from app.repo.snapshot import EvaluationRequest

# Configure logging
def setup_logging(level: int | str):
    logging.basicConfig(
        level=level or logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)]
    )
    return logging.getLogger("deepeval-cli")

@click.command()
@click.argument("judge", envvar="DEEPEVAL_JUDGE", required=True)
@click.argument("models", envvar="DEEPEVAL_MODELS", required=True)
@click.argument("metrics", required=True)
@click.option("--testcases", help="Name of .json file where golden dataset is", default="golden-dataset.json")
@click.option("--env", required=True, type=click.Path(exists=True, file_okay=True), help="Path to .env file to load credentials from")
@click.option('-v', '--verbose', is_flag=True,
              help='Enable verbose logging (log level DEBUG)')
@click.option('-c', '--cache', is_flag=True,
              help='Enable caching of LLM responses')
def main(judge: str, models: str, metrics: str, env: Path, testcases: str, verbose: bool, cache: bool):
    """
    CLI runner for DeepEval.
    """
    global logger
    logger = setup_logging(logging.DEBUG if verbose else logging.INFO)

    load_dotenv(env)
    logger.info(f"Loaded environment variables from {env}")
    #
    models_list = [m.strip() for m in models.split(",") if m.strip()]
    if not models_list:
        logger.error("No models provided. Use --models or DEEPEVAL_MODELS env var.")
        sys.exit(1)

    metrics_list = [m.strip() for m in metrics.split(",") if m.strip()]
    if not metrics_list:
        logger.error("No metrics provided. Use --metrics.")
        sys.exit(1)

    evaluator = Evaluator(get_config(strict=True, cache=cache, dataset_file=testcases))

    # Run evaluation for all models at once
    logger.info(f"Starting evaluation with judge '{judge}' for models: {models_list}")

    result = None
    try:
        result = evaluator.run_evaluation(EvaluationRequest(
            judge=judge,
            models=models_list,
            metrics=metrics_list,
            tests=None,  # Run all tests
            refresh_subject=not cache,
            refresh_judge=not cache,
        ))
    except Exception as e:
        logger.exception("Evaluation failed")
        sys.exit(1)

    if result is None:
        err = evaluator.last_error
        if err:
            logger.error("Evaluation failed: %s", err)
        else:
            logger.error("Evaluation did not return any results.")
        sys.exit(1)

    # Print summary
    logger.info("=== Evaluation Summary ===")
    logger.info(f"Total tests: {result.summary.total}")
    logger.info(f"Tests evaluated: {result.summary.tests_evaluated}")
    logger.info(f"Tests generated: {result.summary.tests_generated}")   
    logger.info(f"Tests ready: {result.summary.tests_ready}")
    logger.info(f"Errors: {result.summary.errors}")


if __name__ == "__main__":
    main()