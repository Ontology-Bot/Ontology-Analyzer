import os
import sys
import json
import logging
from pathlib import Path
from dotenv import load_dotenv
import click

from app.scheuduler import Scheduler
from app.testcase_loader import load_testcases

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
@click.option("--testcases", required=True, type=click.Path(exists=True, file_okay=True), help="Path to .json file where golden dataset is")
@click.option("--env", required=True, type=click.Path(exists=True, file_okay=True), help="Path to .env file to load credentials from")
@click.option('-v', '--verbose', is_flag=True,
              help='Enable verbose logging (equivalent to --log-level DEBUG)')
def main(judge: str, models: str, metrics: str, env: Path, testcases: Path, verbose: bool):
    """
    CLI runner for DeepEval.
    """
    global logger
    logger = setup_logging(logging.DEBUG if verbose else logging.INFO)

    load_dotenv(env)
    logger.info(f"Loaded environment variables from {env}")
    #
    required_vars = [
        "OPENAI_SUBJECT_BASE_URL",
        "OPENAI_SUBJECT_API_KEY",
        "OPENAI_JUDGE_BASE_URL",
        "OPENAI_JUDGE_API_KEY",
        "DEEPEVAL_RESULTS_FOLDER"

    ]
    missing = [v for v in required_vars if not os.environ.get(v)]
    if missing:
        logger.error(f"Missing required environment variables: {', '.join(missing)}")
        sys.exit(1)
    #
    load_testcases(str(testcases))

    models_list = [m.strip() for m in models.split(",") if m.strip()]
    if not models_list:
        logger.error("No models provided. Use --models or DEEPEVAL_MODELS env var.")
        sys.exit(1)

    metrics_list = [m.strip() for m in metrics.split(",") if m.strip()]
    if not models_list:
        logger.error("No metrics provided. Use --metrics.")
        sys.exit(1)

    DATA_DIR = os.environ.get("DEEPEVAL_RESULTS_FOLDER") or "./data"
    os.makedirs(DATA_DIR, exist_ok=True)

    scheduler = Scheduler(DATA_DIR)

    # Run evaluation for all models at once
    logger.info(f"Starting evaluation with judge '{judge}' for models: {models_list}")

    try:
        scheduler.run_evaluation_task(judge, models_list, metrics_list)
    except Exception as e:
        logger.exception("Evaluation failed")
        sys.exit(1)

    # Read results from last saved file
    last_file = scheduler.state.get("last_result_file")
    if not last_file or not os.path.exists(last_file):
        logger.error("No results file found after evaluation")
        sys.exit(1)

    with open(last_file) as f:
        data = json.load(f)

    results = {}
    for model, model_results in data.get("results", {}).items():
        tests = model_results.get("test_results", [])
        total = len(tests)
        passed = sum(1 for t in tests if t.get("success") is True)
        results[model] = (passed, total)

    # Print summary
    logger.info("=== Evaluation Summary ===")
    for model, (passed, total) in results.items():
        pct = round((passed / total) * 100) if total else 0
        logger.info(f"{model}: {pct}% ({passed}/{total})")

    logger.info(f"All results saved in {os.path.dirname(last_file)}")


if __name__ == "__main__":
    main()