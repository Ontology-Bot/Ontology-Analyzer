
import json
from pathlib import Path

def read_json(path: Path) -> dict:
    with open(path, "r") as f:
        return json.load(f)
    
def write_json(path: Path, data: dict):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)