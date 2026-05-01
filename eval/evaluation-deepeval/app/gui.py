from fastapi import FastAPI, UploadFile, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel
from pathlib import Path

from .scheuduler import Scheduler
from .evaluator import Evaluator
from .config import get_config

import json
import os

import logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

app = FastAPI()

evaluator = Evaluator(get_config(cache=True))
scheduler = Scheduler(evaluator)

@app.get("/", response_class=HTMLResponse)
async def serve_ui():
    ui_path = Path(__file__).parent / "static" / "index.html"
    return HTMLResponse(content=ui_path.read_text(encoding="utf-8"))
    
@app.post("/upload-testcases/")
async def upload(file: UploadFile):
    logger.info("received upload testcases request")
    if scheduler.is_running():
        raise HTTPException(status_code=409, detail="Evaluation already in progress")
    data = json.loads((await file.read()).decode())
    evaluator.set_testcases(data["tests"])
    return {"status": "uploaded", "count": len(data["tests"])}


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
    config = get_config(cache=True, strict=False)
    evaluator.reset_connection(config.subject, config.judge)

    
@app.get("/config/status/")
async def get_config_status():
    return evaluator.get_connection_status()

class EvalRequest(BaseModel):
    judge: str = ""
    models: list[str]
    metrics: list[str] = []
    invalidate_cache: bool = False
    mode: str = "evaluate"
 
@app.post("/evaluate/")
async def evaluate_models(req: EvalRequest, background_tasks: BackgroundTasks):
    if scheduler.is_running():
        raise HTTPException(status_code=409, detail="Evaluation already in progress")

    mode = req.mode.strip() or "evaluate"
    if mode not in {"evaluate", "generate_only"}:
        raise HTTPException(status_code=400, detail="Unknown run mode")

    models = [model.strip() for model in req.models if model.strip()]
    metrics = [metric.strip() for metric in req.metrics if metric.strip()]
    judge = req.judge.strip()

    if not models:
        raise HTTPException(status_code=400, detail="At least one subject model is required")
    if mode == "evaluate" and not judge:
        raise HTTPException(status_code=400, detail="Judge model is required for evaluation mode")
    if mode == "evaluate" and not metrics:
        raise HTTPException(status_code=400, detail="At least one metric is required for evaluation mode")

    scheduler.state["mode"] = mode
    scheduler.state["judge"] = judge
    scheduler.state["models"] = models
    scheduler.state["metrics"] = metrics
    scheduler.state["invalidate_cache"] = req.invalidate_cache
    scheduler.state["last_result_file"] = None

    background_tasks.add_task(
        scheduler.run_evaluation_task,
        judge,
        models,
        metrics,
        req.invalidate_cache,
        mode,
    )

    return {"status": "started"}
    
@app.get("/status/")
async def get_status():
    return scheduler.state

@app.get("/metrics/")
async def get_metrics_list():
    return evaluator.get_metric_names()

@app.get("/results/")
async def list_results():
    return scheduler.list_results()
 
@app.post("/results/clear")
async def clear_results():
    return scheduler.clear_results()
 
@app.get("/results/{filename}")
async def get_result(filename: str):
    result = scheduler.get_result(filename) 
    if not result:
        raise HTTPException(status_code=404, detail="Not found")
    return result

@app.get("/results/{filename}/dataset")
async def get_result_dataset(filename: str, model: str):
    artifact = scheduler.get_result_dataset_artifact(filename, model)
    if not artifact:
        raise HTTPException(status_code=404, detail="Dataset artifact not found")
    return FileResponse(artifact, media_type="application/json", filename=os.path.basename(artifact))