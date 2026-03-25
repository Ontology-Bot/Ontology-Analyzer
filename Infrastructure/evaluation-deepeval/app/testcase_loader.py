import json
from pathlib import Path
from deepeval.test_case import LLMTestCase, ToolCall

# https://deepeval.com/docs/evaluation-test-cases

TEST_CASES = []

def load_testcases(path="data/golden-dataset.json"):
    global TEST_CASES
    if Path(path).exists():
        with open(path) as f:
            TEST_CASES = json.load(f)["tests"]
    else:
        TEST_CASES = []

def set_testcases(new_cases):
    global TEST_CASES
    TEST_CASES = new_cases

def get_testcases():
    return TEST_CASES