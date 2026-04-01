import json
from pathlib import Path
from deepeval.test_case import LLMTestCase, ToolCall
from typing import Any

# https://deepeval.com/docs/evaluation-test-cases

def load_testcases(path="data/golden-dataset.json") -> list[dict[str, Any]]:
    if Path(path).exists():
        with open(path) as f:
            return json.load(f)["tests"]
    else:
        return []