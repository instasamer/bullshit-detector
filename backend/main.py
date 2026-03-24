"""
Bullshit Detector - Backend API
FastAPI server that interacts with GenLayer's Intelligent Contract
"""

import os
import json
import hashlib
import asyncio
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from genlayer_service import GenLayerService

app = FastAPI(title="Bullshit Detector", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
async def verify_text(request: VerifyTextRequest):
    """Verify a claim by its text content."""
    if not request.claim_text.strip():
        raise HTTPException(status_code=400, detail="Claim text cannot be empty")

    # Check cache first
    key = _cache_key(request.claim_text)
    if key in _cache:
        return {**_cache[key], "cached": True}

    try:
        result = await genlayer.verify_claim(
            claim_text=request.claim_text,
            source_url=request.source_url,
        )
        _cache[key] = result
        return {**result, "cached": False}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/verify/url")
async def verify_url(request: VerifyUrlRequest):
    """Verify a claim by fetching its URL."""
    if not request.url.strip():
        raise HTTPException(status_code=400, detail="URL cannot be empty")

    key = _cache_key(request.url)
    if key in _cache:
        return {**_cache[key], "cached": True}

    try:
        result = await genlayer.verify_url(url=request.url)
        _cache[key] = result
        return {**result, "cached": False}
    except Exception as e:
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
