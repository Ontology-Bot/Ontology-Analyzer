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
    
@app.post("/upload-testcases/")
async def upload(file: UploadFile):
    logger.info("received upload testcases request")
    data = json.loads((await file.read()).decode())
    evaluator.load_testcases(data["tests"])
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
    return evaluator.tracker.model_dump()

@app.get("/metrics/")
async def get_metrics_list():
    return evaluator.get_metric_names()

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