import os
import sys
from app.llm_adapter import LLMAdapterSettings
from app.evaluator import EvaluatorSettings

import logging
logger = logging.getLogger(__name__)

def get_config(cache: bool = False, strict: bool = False, dataset_file: str = "golden-dataset.json") -> EvaluatorSettings:

    data_dir = os.environ.get("DEEPEVAL_RESULTS_FOLDER", "./data")
    os.makedirs(data_dir, exist_ok=True)

    if strict:
        required_vars = [
            "SUBJECT_LLM_BASE_URL",
            "SUBJECT_LLM_API_KEY",
            "SUBJECT_LLM_PROVIDER",
            "JUDGE_LLM_BASE_URL",
            "JUDGE_LLM_API_KEY",
            "JUDGE_LLM_PROVIDER",
            "DEEPEVAL_RESULTS_FOLDER"
        ]
        missing = [v for v in required_vars if not os.environ.get(v)]
        if missing:
            logger.error(f"Missing required environment variables: {', '.join(missing)}")
            sys.exit(1)

    return EvaluatorSettings(
        data_dir=data_dir,
        do_cache=cache,
        judge=LLMAdapterSettings(
            provider=os.environ.get("JUDGE_LLM_PROVIDER", "forgot to set judge provider"),
            base_url=os.environ.get("JUDGE_LLM_BASE_URL", ""),
            api_key=os.environ.get("JUDGE_LLM_API_KEY", ""),
        ),
        subject=LLMAdapterSettings(
            provider=os.environ.get("SUBJECT_LLM_PROVIDER", "forgot to set subject provider"),
            base_url=os.environ.get("SUBJECT_LLM_BASE_URL", ""),
            api_key=os.environ.get("SUBJECT_LLM_API_KEY", ""),
        ),
        dataset_file=dataset_file
    )