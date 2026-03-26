from app.evaluator import run_evaluation
from app.clients import client, judge_async_client, judge_client
from app.testcase_loader import load_testcases, get_testcases

import os

import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

def main():
    print("Hello from evaluation-deepeval!")

    print("Models")
    print(client.models.list())

    load_testcases()
    print(get_testcases())

    results = run_evaluation("gemma-3-27b-it", "gemma-3-27b-it", ["geval"])
    print(results)

if __name__ == "__main__":
    main()
