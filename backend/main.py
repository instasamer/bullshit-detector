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
from fastapi import FastAPI, HTTPException, Request
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
async def verify_text(request: VerifyTextRequest, req: Request):
    """Verify a claim by its text content."""
    if not request.claim_text.strip():
        raise HTTPException(status_code=400, detail="Claim text cannot be empty")

    _check_rate_limit(req.client.host)

    # Check cache first
    key = _cache_key(request.claim_text)
    if key in _cache:
        logger.info("Cache hit for claim (key=%s)", key)
        return {**_cache[key], "cached": True}

    try:
        logger.info("Verifying claim: %.80s...", request.claim_text)
        result = await genlayer.verify_claim(
            claim_text=request.claim_text,
            source_url=request.source_url,
        )
        _cache[key] = result
        logger.info("Verdict: %s (confidence: %s)", result.get("verdict"), result.get("confidence"))
        return {**result, "cached": False}
    except Exception as e:
        logger.error("Verify text failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/verify/url")
async def verify_url(request: VerifyUrlRequest, req: Request):
    """Verify a claim by fetching its URL."""
    if not request.url.strip():
        raise HTTPException(status_code=400, detail="URL cannot be empty")

    _check_rate_limit(req.client.host)

    key = _cache_key(request.url)
    if key in _cache:
        logger.info("Cache hit for URL (key=%s)", key)
        return {**_cache[key], "cached": True}

    try:
        logger.info("Verifying URL: %s", request.url)
        result = await genlayer.verify_url(url=request.url)
        _cache[key] = result
        logger.info("Verdict: %s (confidence: %s)", result.get("verdict"), result.get("confidence"))
        return {**result, "cached": False}
    except Exception as e:
        logger.error("Verify URL failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


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
