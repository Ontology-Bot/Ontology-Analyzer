from fastapi import FastAPI, UploadFile, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel

from app.repo.snapshot import EvaluationRequest

from .evaluator import Evaluator
from .config import get_config

import json
import os

from functools import reduce

import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

app = FastAPI()

evaluator = Evaluator(get_config(cache=True))

# UI
from pathlib import Path
import os

@app.get("/", response_class=HTMLResponse)
async def serve_ui():
    ui_path = Path(__file__).parent / "static" / "index.html"
    return HTMLResponse(content=ui_path.read_text(encoding="utf-8"))
    
def _normalize_upload_dataset(raw) -> dict: # TODO is it required?
    """Build a dataset dict with name + tests for Snapshot.from_dataset."""
    if isinstance(raw, list):
        return {"name": "uploaded-dataset", "tests": raw}
    if isinstance(raw, dict):
        tests = raw.get("tests")
        if not isinstance(tests, list):
            raise HTTPException(status_code=400, detail="JSON must contain a 'tests' array")
        name = raw.get("name") or "uploaded-dataset"
        return {"name": name, "tests": tests, "model": raw.get("model")}
    raise HTTPException(status_code=400, detail="JSON must be an object or a tests array")


@app.post("/upload-testcases/")
async def upload(file: UploadFile):
    logger.info("received upload testcases request")
    data = json.loads((await file.read()).decode())
    dataset = _normalize_upload_dataset(data)
    evaluator.load_testcases(dataset)
    return {"status": "uploaded", "count": len(dataset["tests"])}


class ConfigRequest(BaseModel):
    SUBJECT_LLM_BASE_URL: str
    SUBJECT_LLM_API_KEY: str
    SUBJECT_LLM_PROVIDER: str
    JUDGE_LLM_BASE_URL: str
    JUDGE_LLM_API_KEY: str
    JUDGE_LLM_PROVIDER: str

    @classmethod
    def from_env(cls):
        return cls(
            SUBJECT_LLM_BASE_URL=os.environ.get("SUBJECT_LLM_BASE_URL", ""),
            SUBJECT_LLM_API_KEY=os.environ.get("SUBJECT_LLM_API_KEY", ""),
            SUBJECT_LLM_PROVIDER=os.environ.get("SUBJECT_LLM_PROVIDER", ""),
            JUDGE_LLM_BASE_URL=os.environ.get("JUDGE_LLM_BASE_URL", ""),
            JUDGE_LLM_API_KEY=os.environ.get("JUDGE_LLM_API_KEY", ""),
            JUDGE_LLM_PROVIDER=os.environ.get("JUDGE_LLM_PROVIDER", ""),
        )
    
    def apply_to_env(self):
        os.environ["SUBJECT_LLM_BASE_URL"] = self.SUBJECT_LLM_BASE_URL
        os.environ["SUBJECT_LLM_API_KEY"] = self.SUBJECT_LLM_API_KEY
        os.environ["SUBJECT_LLM_PROVIDER"] = self.SUBJECT_LLM_PROVIDER
        os.environ["JUDGE_LLM_BASE_URL"] = self.JUDGE_LLM_BASE_URL
        os.environ["JUDGE_LLM_API_KEY"] = self.JUDGE_LLM_API_KEY
        os.environ["JUDGE_LLM_PROVIDER"] = self.JUDGE_LLM_PROVIDER
 

@app.get("/config/")
async def get_config_():
    return ConfigRequest.from_env()

@app.post("/config/")
async def set_config(cr: ConfigRequest):
    cr.apply_to_env()
    config = get_config(cache=True, strict=True)
    evaluator.reset_connection(config.subject, config.judge)

    
@app.get("/config/status/")
async def get_config_status():
    return evaluator.get_connection_status()
 
@app.post("/evaluate/")
async def evaluate_models(req: EvaluationRequest, background_tasks: BackgroundTasks):
    if evaluator.is_running():
        raise HTTPException(status_code=409, detail="Evaluation already in progress")

    background_tasks.add_task(
        evaluator.run_evaluation, req
    )

    return {"status": "started"}
    
@app.get("/status/")
async def get_status():
    """UI: running + snapshot, idle, or error after failed background evaluation."""
    if evaluator.is_running():
        tracker = evaluator.tracker
        if tracker is None:
            return {"status": "running", "summary": None, "snapshot": None, "error": None}
        return {
            "status": "running",
            "summary": tracker.summary.model_dump(),
            "snapshot": tracker.snapshot.model_dump(),
            "error": None,
        }
    if evaluator.last_error:
        return {"status": "error", "error": evaluator.last_error, "judge": None, "summary": None, "snapshot": None}
    return {"status": "idle", "judge": None, "error": None, "summary": None, "snapshot": None}

@app.get("/metrics/")
async def get_metrics_list():
    return evaluator.get_metric_names()

# @app.get("/models/")
# async def get_models_list():
#     return evaluator.snapshot.task.models

@app.post("/models/")
async def add_models_list(models: list[str]):
    evaluator.add_models(models)

@app.get("/results/")
async def list_results():
    return evaluator.repo.list()
 
@app.post("/results/clear")
async def clear_results():
    return evaluator.repo.drop()

@app.post("/results/clear/{timestamp}")
async def clear_results_at(timestamp: str):
    return evaluator.repo.drop_at_timestamp(timestamp)

@app.get("/results/{timestamp}")
async def get_result(timestamp: str):
    result = evaluator.repo.get_at_timestamp(timestamp) 
    if not result:
        raise HTTPException(status_code=404, detail="Not found")
    return result


@app.get("/results/{timestamp}/summary")
async def get_result_summary(timestamp: str):
    """Pandas aggregates for Scientific Summary UI (disk snapshot or live run)."""
    from app.repo.analytics import build_summary

    if timestamp == "live":
        snapshot = evaluator.tracker.snapshot if evaluator.tracker else None
    else:
        snapshot = evaluator.repo.get_at_timestamp(timestamp)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="snapshot not found")
    return build_summary(snapshot)