
import json
import os
from datetime import datetime

import logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

from .evaluator import run_evaluation

class Scheduler:
    def __init__(self, data_dir: str) -> None:
        self.data_dir = data_dir
        self.state = {
            "status": "idle",       # idle | running | done | error
            "judge": "",
            "models": [],
            "metrics": [],
            "progress": {
                "tests_generated": 0,
                "tests_ran": 0,
                "total": 0,
                "current_model": ""
            },
            "error": None,
            "last_result_file": None
        }

    def is_running(self) -> bool:
        return self.state["status"] == "running"
 
    def run_evaluation_task(self, judge: str, models: list[str], metrics: list[str]):
        try:
            self.state["status"] = "running"
            self.state["error"] = None
            self.state["progress"]["tests_ran"] = 0
            self.state["progress"]["tests_generated"] = 0
            self.state["progress"]["total"] = 0
 
            all_results = {}
            for model in models:
                self.state["progress"]["current_model"] = model
                logger.info(f"running evaluation for model '{model}'")
                result = run_evaluation(judge, model, metrics)
                all_results[model] = result.model_dump()
 
                # Try to update progress counters if result exposes them
                if isinstance(result, dict):
                    ran = result.get("tests_ran", result.get("total_cases", 0))
                    self.state["progress"]["tests_ran"] += ran
 
            # Save to timestamped file
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filepath = os.path.join(self.data_dir, f"r_{timestamp}.json")
            payload = {
                "timestamp": timestamp,
                "judge": judge,
                "models": models,
                "metrics": metrics,
                "results": all_results
            }
            with open(filepath, "w") as f:
                json.dump(payload, f, indent=2)
 
            self.state["last_result_file"] = filepath
            self.state["status"] = "done"
 
        except Exception as e:
            logger.exception("Evaluation failed")
            self.state["status"] = "error"
            self.state["error"] = str(e)