import os
import sys
import json
import logging
from pathlib import Path
from dotenv import load_dotenv
import click

from app.config import get_config
from app.scheuduler import Scheduler
from app.evaluator import Evaluator

# Configure logging
def setup_logging(level: int | str):
    logging.basicConfig(
        level=level or logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)]
    )
    return logging.getLogger("deepeval-cli")

@click.command()
@click.argument("judge", envvar="DEEPEVAL_JUDGE", required=False, default="")
@click.argument("models", envvar="DEEPEVAL_MODELS", required=False, default="")
@click.argument("metrics", required=False, default="")
@click.option("--testcases", help="Name of .json file where golden dataset is", default="golden-dataset.json")
@click.option("--env", required=True, type=click.Path(exists=True, file_okay=True), help="Path to .env file to load credentials from")
@click.option("--mode", type=click.Choice(["evaluate", "generate_only"]), default="evaluate", show_default=True,
              help="Run full evaluation or only generate subject outputs")
@click.option('-v', '--verbose', is_flag=True,
              help='Enable verbose logging (log level DEBUG)')
@click.option('-c', '--cache', is_flag=True,
              help='Enable caching of LLM responses')
def main(judge: str, models: str, metrics: str, env: Path, testcases: str, mode: str, verbose: bool, cache: bool):
    """
    CLI runner for DeepEval.
    """
    global logger
    logger = setup_logging(logging.DEBUG if verbose else logging.INFO)

    load_dotenv(env)
    logger.info(f"Loaded environment variables from {env}")
    #
    judge = judge.strip()
    models_list = [m.strip() for m in models.split(",") if m.strip()]
    if not models_list:
        logger.error("No models provided. Use --models or DEEPEVAL_MODELS env var.")
        sys.exit(1)

    metrics_list = [m.strip() for m in metrics.split(",") if m.strip()]
    if mode == "evaluate" and not judge:
        logger.error("No judge provided. Supply the judge positional argument or DEEPEVAL_JUDGE.")
        sys.exit(1)
    if mode == "evaluate" and not metrics_list:
        logger.error("No metrics provided. Use --metrics.")
        sys.exit(1)

    evaluator = Evaluator(get_config(strict=mode == "evaluate", cache=cache, dataset_file=testcases))
    scheduler = Scheduler(evaluator)

    # Run evaluation for all models at once
    logger.info(f"Starting {mode} with judge '{judge or '-'}' for models: {models_list}")

    try:
        scheduler.run_evaluation_task(judge, models_list, metrics_list, mode=mode)
    except Exception as e:
        logger.exception("Evaluation failed")
        sys.exit(1)

    if scheduler.state.get("status") == "error":
        logger.error(scheduler.state.get("error") or "Run failed")
        sys.exit(1)

    # Read results from last saved file
    last_file = scheduler.state.get("last_result_file")
    if not last_file or not os.path.exists(last_file):
        logger.error("No results file found after evaluation")
        sys.exit(1)

    with open(last_file) as f:
        data = json.load(f)

    if mode == "generate_only":
        artifacts = data.get("dataset_artifacts", {})
        logger.info("=== Generation Summary ===")
        for model, artifact in artifacts.items():
            logger.info(f"{model}: {artifact}")
        logger.info(f"All generated datasets saved in {os.path.dirname(last_file)}")
        return

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