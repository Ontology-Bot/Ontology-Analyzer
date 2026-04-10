
import json
import os
import glob
from datetime import datetime

import logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

from app.evaluator import Evaluator

class Scheduler:
    def __init__(self, evaluator: Evaluator) -> None:
        self.evaluator = evaluator
        self.data_dir = evaluator.get_config().data_dir
        self.state = {
            "status": "idle",       # idle | running | done | error
            "judge": "",
            "models": [],
            "metrics": [],
            "invalidate_cache": False,
            "progress": {
                "tests_generated": 0,
                "tests_ran": 0,
                "errors": 0,
                "total": 0,
                "current_model": ""
            },
            "error": None,
            "last_result_file": None
        }

    def is_running(self) -> bool:
        return self.state["status"] == "running"
 
    def run_evaluation_task(self, judge: str, models: list[str], metrics: list[str], invalidate_cache: bool = False):
        try:
            self.state["status"] = "running"
            self.state["error"] = None
            self.state["progress"]["errors"] = 0
            self.state["progress"]["tests_ran"] = 0
            self.state["progress"]["tests_generated"] = 0
            self.state["progress"]["total"] = len(models) * len(self.evaluator.get_testcases())
 
            all_results = {}
            for model in models:
                tracker = self.state["progress"]
                tracker["current_model"] = model
                logger.info(f"running evaluation for model '{model}'")
                result = self.evaluator.run_evaluation(judge, model, metrics, invalidate_cache, tracker)
                all_results[model] = result.model_dump()
 
            # Save to timestamped file
            self.store_result(judge, models, metrics, all_results)
            self.state["status"] = "done"
 
        except Exception as e:
            logger.exception("Evaluation failed")
            self.state["status"] = "error"
            self.state["error"] = str(e)

    
    def store_result(self, judge: str, models: list[str], metrics: list[str], all_results: dict):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        result = {
            "timestamp": timestamp,
            "judge": judge,
            "models": models,
            "metrics": metrics,
            "results": all_results
        }
        filepath = os.path.join(self.data_dir, f"r_{timestamp}.json")
        with open(filepath, "w") as f:
            json.dump(result, f, indent=2)
        self.state["last_result_file"] = filepath

    def list_results(self):
        files = sorted(glob.glob(os.path.join(self.data_dir, "r_*.json")), reverse=True)
        results = []
        for f in files:
            name = os.path.basename(f)
            ts = name.replace(".json", "")
            try:
                with open(f) as fp:
                    data = json.load(fp)
                # calculate pass rate
                pass_rates = {}
                metrics = data.get("metrics", [])
                models = data.get("models", [])
                tests_res = data.get("results", {})
                for m, entry in tests_res.items():
                    tests = entry["test_results"]
                    total = len(tests)
                    passed = 0
                    errors = 0
                    for tr in tests:
                        if tr.get("success", False):
                            passed += 1
                        md = tr.get("metrics_data", None)
                        for md_entry in md or []:
                            if md_entry.get("error", None):
                                errors += 1
                    pass_rates[m] = (passed, total, errors)
                #
                results.append({
                    "filename": name,
                    "timestamp": data.get("timestamp", ts),
                    "judge": data.get("judge", ""),
                    "models": models,
                    "metrics": metrics,
                    "pass_rates": pass_rates
                })
            except Exception:
                import traceback
                logger.error(f"Error loading result file '{f}'")
                logger.exception(traceback.print_exc())
        return results
 
    def clear_results(self):
        logger.warning("Deleting ALL results")
        for f in glob.glob(os.path.join(self.data_dir, "r_*.json")):
            os.remove(f)
        for f in glob.glob(os.path.join(self.data_dir, "*")):
            # Check if it is a file and has no extension
            if os.path.isfile(f) and os.path.splitext(f)[1] == "":
                os.remove(f)
 
    def get_result(self, filename: str):
        filepath = os.path.join(self.data_dir, filename)
        if not os.path.exists(filepath) or not filename.endswith(".json"):
            return None
        with open(filepath) as f:
            return json.load(f)