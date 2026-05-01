import json
import os
import glob
import re
from datetime import datetime

import logging
from app.evaluator import Evaluator

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

class Scheduler:
    def __init__(self, evaluator: Evaluator) -> None:
        self.evaluator = evaluator
        self.data_dir = evaluator.get_config().data_dir
        self.state = {
            "status": "idle",       # idle | running | done | error
            "mode": "evaluate",
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

    def _sanitize_name(self, value: str) -> str:
        sanitized = re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip())
        return sanitized.strip("._") or "model"

    def _dataset_artifact_path(self, filename: str):
        safe_name = os.path.basename(filename)
        return os.path.join(self.data_dir, safe_name)

    def store_dataset_artifact(self, timestamp: str, model: str, generated_cases: list[dict]):
        filename = f"dataset_{timestamp}_{self._sanitize_name(model)}.json"
        filepath = self._dataset_artifact_path(filename)
        with open(filepath, "w") as f:
            json.dump({
                "tests": [
                    {
                        "input": testcase["input"],
                        "expected_output": testcase["expected_output"],
                        "output": testcase["output"],
                        "duration": testcase["duration"],
                        "token_usage": testcase["token_usage"],
                    }
                    for testcase in generated_cases
                ]
            }, f, indent=2)
        return filename
 
    def run_evaluation_task(self, judge: str, models: list[str], metrics: list[str], invalidate_cache: bool = False, mode: str = "evaluate"):
        try:
            self.state["status"] = "running"
            self.state["mode"] = mode
            self.state["error"] = None
            self.state["progress"]["errors"] = 0
            self.state["progress"]["tests_ran"] = 0
            self.state["progress"]["tests_generated"] = 0
            self.state["progress"]["total"] = len(models) * len(self.evaluator.get_testcases())
 
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            all_results = {}
            dataset_artifacts = {}
            for model in models:
                tracker = self.state["progress"]
                tracker["current_model"] = model
                if mode == "generate_only":
                    logger.info(f"running generation-only flow for model '{model}'")
                    generated_cases = self.evaluator.prepare_subject_outputs(model, invalidate_cache, tracker)
                    all_results[model] = self.evaluator.create_test_results(generated_cases)
                    dataset_artifacts[model] = self.store_dataset_artifact(timestamp, model, generated_cases)
                else:
                    logger.info(f"running evaluation for model '{model}'")
                    result = self.evaluator.run_evaluation(judge, model, metrics, invalidate_cache, tracker)
                    all_results[model] = result.model_dump()
 
            # Save to timestamped file
            self.store_result(timestamp, judge, models, metrics, all_results, mode, dataset_artifacts)
            self.state["status"] = "done"
 
        except Exception as e:
            logger.exception("Evaluation failed")
            self.state["status"] = "error"
            self.state["error"] = str(e)

    
    def store_result(self, timestamp: str, judge: str, models: list[str], metrics: list[str], all_results: dict, mode: str = "evaluate", dataset_artifacts: dict[str, str] | None = None):
        result = {
            "timestamp": timestamp,
            "mode": mode,
            "judge": judge,
            "models": models,
            "metrics": metrics,
            "dataset_artifacts": dataset_artifacts or {},
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
                mode = data.get("mode", "evaluate")
                pass_rates = {}
                generated_counts = {}
                metrics = data.get("metrics", [])
                models = data.get("models", [])
                tests_res = data.get("results", {})
                for m, entry in tests_res.items():
                    tests = entry.get("test_results", [])
                    total = len(tests)
                    if mode == "generate_only":
                        generated_counts[m] = total
                        continue
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
                    "mode": mode,
                    "judge": data.get("judge", ""),
                    "models": models,
                    "metrics": metrics,
                    "pass_rates": pass_rates,
                    "generated_counts": generated_counts,
                    "dataset_artifacts": data.get("dataset_artifacts", {})
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
        for f in glob.glob(os.path.join(self.data_dir, "dataset_*.json")):
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

    def get_result_dataset_artifact(self, filename: str, model: str):
        result = self.get_result(filename)
        if not result:
            return None
        artifact_name = (result.get("dataset_artifacts") or {}).get(model)
        if not artifact_name:
            return None
        artifact_path = self._dataset_artifact_path(artifact_name)
        if not os.path.exists(artifact_path):
            return None
        return artifact_path