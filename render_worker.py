import logging
import os
import threading
from datetime import datetime
from typing import Dict

import requests
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from main_scraper import CompanyJobScraper

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("render-worker")

app = FastAPI(title="Scraper Render Worker", version="1.0.0")

INTERNAL_TOKEN = os.getenv("INTERNAL_RENDER_TOKEN")
CALLBACK_TIMEOUT = int(os.getenv("RENDER_CALLBACK_TIMEOUT", "15"))


class ScraperRequest(BaseModel):
    company: str
    geminiApiKey: str
    jobId: str
    callbackUrl: str


class ScraperResponse(BaseModel):
    jobId: str
    status: str = "accepted"


def _utc_timestamp() -> str:
    return datetime.utcnow().isoformat()


def _post_callback(url: str, payload: Dict) -> None:
    try:
        requests.post(url, json=payload, timeout=CALLBACK_TIMEOUT)
    except Exception as exc:
        logger.warning("Callback delivery failed: %s", exc)


def _run_job(payload: ScraperRequest) -> None:
    callback_url = payload.callbackUrl
    company = payload.company
    job_id = payload.jobId

    def emit(progress: Dict) -> None:
        event = {
            "company": company,
            "jobId": job_id,
            **progress,
        }
        event.setdefault("timestamp", _utc_timestamp())
        event.setdefault("type", event.get("stage", "update"))
        event.setdefault("status", event.get("status", "info"))
        _post_callback(callback_url, event)

    emit({
        "stage": "render-dispatch",
        "message": "Render worker accepted job",
    })

    try:
        scraper = CompanyJobScraper(
            gemini_api_key=payload.geminiApiKey,
            progress_callback=lambda evt: emit(dict(evt)),
        )
        success = scraper.add_company(
            payload.company,
            gemini_api_key=payload.geminiApiKey,
            progress_callback=lambda evt: emit(dict(evt)),
        )
        emit({
            "type": "finalized",
            "stage": "finalized",
            "status": "success" if success else "error",
            "message": "Workflow finished" if success else "Workflow ended with errors",
        })
    except Exception as exc:
        logger.exception("Scraper job failed: %s", exc)
        emit({
            "type": "error",
            "stage": "error",
            "status": "error",
            "message": str(exc),
        })
        emit({
            "type": "finalized",
            "stage": "finalized",
            "status": "error",
            "message": "Workflow terminated unexpectedly",
        })


@app.post("/scraper", response_model=ScraperResponse)
async def create_scraper(req: ScraperRequest, request: Request):
    if INTERNAL_TOKEN:
        auth_header = request.headers.get("Authorization", "")
        if auth_header != f"Bearer {INTERNAL_TOKEN}":
            raise HTTPException(status_code=401, detail="Unauthorized")

    if not req.company.strip():
        raise HTTPException(status_code=400, detail="Company is required")

    thread = threading.Thread(
        target=_run_job,
        args=(req,),
        name=f"render-worker-{req.jobId}",
        daemon=True,
    )
    thread.start()

    return ScraperResponse(jobId=req.jobId)


@app.get("/healthz")
async def healthz():
    return JSONResponse({"status": "ok"})