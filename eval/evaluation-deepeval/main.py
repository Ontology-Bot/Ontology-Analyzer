from openai import OpenAI

import os
import logging

from app.evaluator import Evaluator, EvaluatorSettings
from app.llm_adapter import LLMAdapterSettings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

def main():
    print("Hello from evaluation-deepeval!")

    eval = Evaluator(EvaluatorSettings(
        data_dir="./data",
        do_cache=False,
        judge=LLMAdapterSettings(
            provider="ollama",
            base_url="http://localhost:11434",
            api_key=""
        ),
        subject=LLMAdapterSettings(
            provider="ollama",
            base_url="http://localhost:11434",
            api_key=""
        )
    ))
    print("Models")
    print(eval.get_connection_status())

    print(eval.get_testcases())

    results = eval.run_evaluation("qwen3:32b", "qwen3:32b", ["geval"])
    print(results)

if __name__ == "__main__":
    main()
