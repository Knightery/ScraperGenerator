import logging
import os
import threading
from datetime import datetime
from queue import Queue

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

# Simple job queue
job_queue: Queue = Queue()


class ScraperRequest(BaseModel):
    company: str
    geminiApiKey: str
    jobId: str
    callbackUrl: str

class ScraperResponse(BaseModel):
    jobId: str
    queuePosition: int


def _post_callback(url: str, payload: dict) -> None:
    """Send callback to Vercel."""
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as exc:
        logger.warning(f"Callback failed: {exc}")


def _run_job(payload: ScraperRequest) -> None:
    """Execute a single scraper job."""
    def emit(progress: dict) -> None:
        event = {
            "company": payload.company,
            "jobId": payload.jobId,
            "timestamp": datetime.utcnow().isoformat(),
            **progress,
        }
        _post_callback(payload.callbackUrl, event)

    emit({"stage": "running", "message": f"Processing {payload.company}"})

    try:
        scraper = CompanyJobScraper(
            gemini_api_key=payload.geminiApiKey,
            progress_callback=emit,
        )
        success = scraper.add_company(
            payload.company,
            gemini_api_key=payload.geminiApiKey,
            progress_callback=emit,
        )
        
        emit({
            "type": "finalized",
            "stage": "finalized",
            "status": "success" if success else "error",
            "message": "Workflow finished" if success else "Workflow failed",
        })
    except Exception as exc:
        logger.exception(f"Job {payload.jobId} failed: {exc}")
        emit({
            "type": "error",
            "stage": "error",
            "status": "error",
            "message": str(exc),
        })


def _worker_thread() -> None:
    """Process jobs from queue sequentially."""
    logger.info("Worker thread started")
    
    while True:
        payload = job_queue.get(block=True)
        if payload is None:
            break
            
        logger.info(f"Processing {payload.company} (job {payload.jobId})")
        _run_job(payload)
        job_queue.task_done()


@app.post("/scraper", response_model=ScraperResponse)
async def create_scraper(req: ScraperRequest, request: Request):
    """Queue a scraper job."""
    if INTERNAL_TOKEN:
        auth = request.headers.get("Authorization", "")
        if auth != f"Bearer {INTERNAL_TOKEN}":
            raise HTTPException(status_code=401, detail="Unauthorized")

    if not req.company.strip():
        raise HTTPException(status_code=400, detail="Company required")

    # Add to queue
    job_queue.put(req)
    position = job_queue.qsize()
    
    # Notify queued
    _post_callback(req.callbackUrl, {
        "type": "queued",
        "stage": "queued",
        "jobId": req.jobId,
        "company": req.company,
        "message": f"Queued (position {position})" if position > 1 else "Starting soon",
        "queuePosition": position,
        "timestamp": datetime.utcnow().isoformat(),
    })
    
    logger.info(f"Queued {req.company} at position {position}")
    return ScraperResponse(jobId=req.jobId, queuePosition=position)


@app.get("/healthz")
async def healthz():
    """Health check."""
    return {"status": "ok", "queue_size": job_queue.qsize()}


@app.on_event("startup")
async def startup():
    """Start worker thread."""
    threading.Thread(target=_worker_thread, daemon=True).start()
    logger.info("Worker started")