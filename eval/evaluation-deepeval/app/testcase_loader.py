import json
from pathlib import Path
from deepeval.test_case import LLMTestCase, ToolCall
from typing import Any

from pathlib import Path

# https://deepeval.com/docs/evaluation-test-cases

def read_testcases(path: Path) -> dict:
    if Path(path).exists():
        with open(path) as f:
            return json.load(f)
    else:
        return {}