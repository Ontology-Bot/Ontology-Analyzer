from fastapi import FastAPI, UploadFile, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel

from .testcase_loader import set_testcases, load_testcases
from .metrics import get_metrics
from .scheuduler import Scheduler
from .clients import get_subject_client, get_judge_client, test_connection, reset_connection

import json
import os
import glob

from functools import reduce

import logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

app = FastAPI()

load_testcases()

DATA_DIR = os.environ.get("DEEPEVAL_RESULTS_FOLDER") or "./data"
os.makedirs(DATA_DIR, exist_ok=True)

scheduler = Scheduler(DATA_DIR)

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
    set_testcases(data["tests"])
    return {"status": "uploaded", "count": len(data["tests"])}
 

@app.get("/config/")
async def get_config():
    return {
        "OPENAI_SUBJECT_BASE_URL": os.environ.get("OPENAI_SUBJECT_BASE_URL"),
        "OPENAI_SUBJECT_API_KEY": os.environ.get("OPENAI_SUBJECT_API_KEY"),
        "OPENAI_JUDGE_BASE_URL": os.environ.get("OPENAI_JUDGE_BASE_URL"),
        "OPENAI_JUDGE_API_KEY": os.environ.get("OPENAI_JUDGE_API_KEY"),
    }

class ConfigRequest(BaseModel):
    OPENAI_SUBJECT_BASE_URL: str
    OPENAI_SUBJECT_API_KEY: str
    OPENAI_JUDGE_BASE_URL: str
    OPENAI_JUDGE_API_KEY: str

@app.post("/config/")
async def set_config(cr: ConfigRequest):
    os.environ["OPENAI_SUBJECT_BASE_URL"] = cr.OPENAI_SUBJECT_BASE_URL
    os.environ["OPENAI_SUBJECT_API_KEY"] = cr.OPENAI_SUBJECT_API_KEY
    os.environ["OPENAI_JUDGE_BASE_URL"] = cr.OPENAI_JUDGE_BASE_URL
    os.environ["OPENAI_JUDGE_API_KEY"] = cr.OPENAI_JUDGE_API_KEY
    reset_connection()

    
@app.get("/config/status/")
async def get_config_status():
    return {
        "subject": test_connection(get_subject_client()),
        "judge": test_connection(get_judge_client()),
    }

class EvalRequest(BaseModel):
    judge: str
    models: list[str]
    metrics: list[str]
 
@app.post("/evaluate/")
async def evaluate_models(req: EvalRequest, background_tasks: BackgroundTasks):
    if scheduler.is_running():
        raise HTTPException(status_code=409, detail="Evaluation already in progress")

    scheduler.state["judge"] = req.judge
    scheduler.state["models"] = req.models
    scheduler.state["metrics"] = req.metrics
    scheduler.state["last_result_file"] = None

    background_tasks.add_task(
        scheduler.run_evaluation_task,
        req.judge,
        req.models,
        req.metrics
    )

    return {"status": "started"}
    
@app.get("/status/")
async def get_status():
    return scheduler.state

@app.get("/metrics/")
async def get_metrics_list():
    return list(get_metrics("").keys())

@app.get("/results/")
async def list_results():
    files = sorted(glob.glob(os.path.join(DATA_DIR, "r_*.json")), reverse=True)
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
                passed = sum(1 for t in tests if t.get("success") is True)
                pass_rates[m] = (passed, total)
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
            pass
    return results
 
@app.post("/results/clear")
async def clear_results():
    logger.warning("Deleting ALL results")
    for f in glob.glob(os.path.join(DATA_DIR, "r_*.json")):
        os.remove(f)
    for f in glob.glob(os.path.join(DATA_DIR, "*[!.json]")):
        os.remove(f)
 
@app.get("/results/{filename}")
async def get_result(filename: str):
    filepath = os.path.join(DATA_DIR, filename)
    if not os.path.exists(filepath) or not filename.endswith(".json"):
        raise HTTPException(status_code=404, detail="Not found")
    with open(filepath) as f:
        return json.load(f)