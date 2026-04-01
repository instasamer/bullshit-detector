"""
Bullshit Detector - Backend API
FastAPI server that interacts with GenLayer's Intelligent Contract
"""

import os
import json
import hashlib
import asyncio
import logging
import time
from dotenv import load_dotenv
load_dotenv()
from collections import defaultdict
from fastapi import FastAPI, HTTPException, Request, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
try:
    from backend.genlayer_service import GenLayerService
except ImportError:
    from genlayer_service import GenLayerService

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("bs-detector")

app = FastAPI(title="Bullshit Detector", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Simple in-memory rate limiter: max 10 verify requests per minute per IP
RATE_LIMIT = 10
RATE_WINDOW = 60
_rate_counts: dict[str, list[float]] = defaultdict(list)


def _check_rate_limit(ip: str):
    now = time.time()
    _rate_counts[ip] = [t for t in _rate_counts[ip] if now - t < RATE_WINDOW]
    if len(_rate_counts[ip]) >= RATE_LIMIT:
        raise HTTPException(status_code=429, detail="Too many requests. Try again in a minute.")
    _rate_counts[ip].append(now)

genlayer = GenLayerService()

# Local cache for verified claims (persists in memory, backed by contract on-chain)
_cache: dict[str, dict] = {}

# Async job tracking: tx_hash → {"status": "pending"|"done"|"error", "result": {}, "error": ""}
_jobs: dict[str, dict] = {}


async def _poll_until_done(tx_hash: str, cache_key: str):
    """Background task: poll GenLayer every 10s until tx is ACCEPTED/FINALIZED."""
    for attempt in range(180):  # up to 30 minutes
        await asyncio.sleep(10)
        try:
            status, verdict = await asyncio.get_event_loop().run_in_executor(
                None, genlayer.get_tx_status, tx_hash
            )
            if verdict is not None:
                _jobs[tx_hash] = {"status": "done", "result": verdict}
                _cache[cache_key] = verdict
                logger.info("Job %s done: %s (attempt %d)", tx_hash[:16], verdict.get("verdict"), attempt + 1)
                return
        except Exception as e:
            logger.warning("Poll attempt %d for %s: %s", attempt + 1, tx_hash[:16], e)
    _jobs[tx_hash] = {"status": "error", "error": "Timed out after 30 minutes waiting for consensus"}
    logger.error("Job %s timed out", tx_hash[:16])


def _cache_key(text: str) -> str:
    """Normalize and hash claim text for cache lookup."""
    normalized = " ".join(text.lower().split())
    return hashlib.sha256(normalized.encode()).hexdigest()[:16]


class VerifyTextRequest(BaseModel):
    claim_text: str
    source_url: str = ""


class VerifyUrlRequest(BaseModel):
    url: str


@app.post("/api/verify/text")
async def verify_text(request: VerifyTextRequest, req: Request, background_tasks: BackgroundTasks):
    """Submit a claim for verification. Returns job_id immediately; poll /api/poll/{job_id} for result."""
    if not request.claim_text.strip():
        raise HTTPException(status_code=400, detail="Claim text cannot be empty")

    _check_rate_limit(req.client.host)

    key = _cache_key(request.claim_text)
    if key in _cache:
        logger.info("Cache hit for claim (key=%s)", key)
        return {**_cache[key], "cached": True, "status": "done"}

    try:
        logger.info("Submitting claim: %.80s...", request.claim_text)
        tx_hash = await genlayer.submit_claim(
            claim_text=request.claim_text,
            source_url=request.source_url,
        )
        _jobs[tx_hash] = {"status": "pending"}
        background_tasks.add_task(_poll_until_done, tx_hash, key)
        logger.info("Submitted tx %s for claim", tx_hash)
        return {"job_id": tx_hash, "status": "pending"}
    except Exception as e:
        import traceback
        logger.error("Submit claim failed: %s\n%s", e, traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")


@app.post("/api/verify/url")
async def verify_url(request: VerifyUrlRequest, req: Request, background_tasks: BackgroundTasks):
    """Submit a URL for verification. Returns job_id immediately; poll /api/poll/{job_id} for result."""
    if not request.url.strip():
        raise HTTPException(status_code=400, detail="URL cannot be empty")

    _check_rate_limit(req.client.host)

    key = _cache_key(request.url)
    if key in _cache:
        logger.info("Cache hit for URL (key=%s)", key)
        return {**_cache[key], "cached": True, "status": "done"}

    try:
        logger.info("Submitting URL: %s", request.url)
        tx_hash = await genlayer.submit_url(url=request.url)
        _jobs[tx_hash] = {"status": "pending"}
        background_tasks.add_task(_poll_until_done, tx_hash, key)
        logger.info("Submitted tx %s for URL", tx_hash)
        return {"job_id": tx_hash, "status": "pending"}
    except Exception as e:
        logger.error("Submit URL failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/poll/{job_id}")
async def poll_job(job_id: str):
    """Poll the status of a verification job."""
    job = _jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if job["status"] == "done":
        return {**job["result"], "status": "done", "cached": False}
    if job["status"] == "error":
        raise HTTPException(status_code=500, detail=job.get("error", "Verification failed"))
    return {"status": "pending"}


@app.get("/api/results")
async def get_results():
    """Get all previously verified claims."""
    try:
        return await genlayer.get_all_results()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "contract_address": genlayer.contract_address,
        "chain": genlayer.chain_name,
    }


# Serve frontend
frontend_dir = os.path.join(os.path.dirname(__file__), "..", "frontend")


@app.get("/")
async def serve_frontend():
    return FileResponse(os.path.join(frontend_dir, "index.html"))


app.mount("/static", StaticFiles(directory=frontend_dir), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
