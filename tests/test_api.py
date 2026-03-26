"""
Tests for the BS Detector API endpoints.
Uses a mocked GenLayer service to avoid real contract calls.
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient

import sys
import os

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))


@pytest.fixture
def mock_genlayer():
    """Mock the GenLayerService before importing the app."""
    with patch.dict(os.environ, {
        "GENLAYER_CONTRACT_ADDRESS": "0xTEST",
        "GENLAYER_PRIVATE_KEY": "0xTESTKEY",
        "GENLAYER_CHAIN": "studionet",
    }):
        with patch("main.GenLayerService") as MockService:
            instance = MagicMock()
            instance.contract_address = "0xTEST"
            instance.chain_name = "studionet"
            instance.verify_claim = AsyncMock(return_value={
                "verdict": "BULLSHIT",
                "confidence": 92,
                "reason": "Unrealistic profit claims",
                "red_flags": ["Fake urgency", "DM sales funnel"],
                "evidence_summary": "No evidence found",
            })
            instance.verify_url = AsyncMock(return_value={
                "verdict": "LEGIT",
                "confidence": 78,
                "reason": "Supported by NASA press release",
                "red_flags": [],
                "evidence_summary": "Confirmed by multiple sources",
            })
            instance.get_all_results = AsyncMock(return_value={})
            MockService.return_value = instance

            # Force reimport to use the mock
            if "main" in sys.modules:
                del sys.modules["main"]

            from main import app
            # Replace the genlayer instance
            import main
            main.genlayer = instance
            main._cache.clear()

            yield instance, TestClient(app)


class TestHealthEndpoint:
    def test_health_returns_ok(self, mock_genlayer):
        service, client = mock_genlayer
        resp = client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["contract_address"] == "0xTEST"
        assert data["chain"] == "studionet"


class TestVerifyTextEndpoint:
    def test_verify_text_success(self, mock_genlayer):
        service, client = mock_genlayer
        resp = client.post("/api/verify/text", json={
            "claim_text": "I made $100k in 2 weeks",
            "source_url": "https://x.com/user/status/123",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["verdict"] == "BULLSHIT"
        assert data["confidence"] == 92
        assert data["cached"] is False
        assert len(data["red_flags"]) == 2

    def test_verify_text_empty_rejected(self, mock_genlayer):
        _, client = mock_genlayer
        resp = client.post("/api/verify/text", json={"claim_text": ""})
        assert resp.status_code == 400

    def test_verify_text_whitespace_rejected(self, mock_genlayer):
        _, client = mock_genlayer
        resp = client.post("/api/verify/text", json={"claim_text": "   "})
        assert resp.status_code == 400

    def test_verify_text_caches_result(self, mock_genlayer):
        service, client = mock_genlayer
        # First call
        resp1 = client.post("/api/verify/text", json={"claim_text": "test claim"})
        assert resp1.json()["cached"] is False

        # Second call - should be cached
        resp2 = client.post("/api/verify/text", json={"claim_text": "test claim"})
        assert resp2.json()["cached"] is True
        assert resp2.json()["verdict"] == "BULLSHIT"

        # Service should only be called once
        assert service.verify_claim.await_count == 1

    def test_verify_text_cache_is_case_insensitive(self, mock_genlayer):
        service, client = mock_genlayer
        client.post("/api/verify/text", json={"claim_text": "Test Claim"})
        resp = client.post("/api/verify/text", json={"claim_text": "test claim"})
        assert resp.json()["cached"] is True
        assert service.verify_claim.await_count == 1


class TestVerifyUrlEndpoint:
    def test_verify_url_success(self, mock_genlayer):
        _, client = mock_genlayer
        resp = client.post("/api/verify/url", json={
            "url": "https://x.com/nasa/status/123",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["verdict"] == "LEGIT"
        assert data["cached"] is False

    def test_verify_url_empty_rejected(self, mock_genlayer):
        _, client = mock_genlayer
        resp = client.post("/api/verify/url", json={"url": ""})
        assert resp.status_code == 400


class TestGetResultsEndpoint:
    def test_get_results_empty(self, mock_genlayer):
        _, client = mock_genlayer
        resp = client.get("/api/results")
        assert resp.status_code == 200
        assert resp.json() == {}


class TestServeFrontend:
    def test_serves_index_html(self, mock_genlayer):
        _, client = mock_genlayer
        resp = client.get("/")
        assert resp.status_code == 200
        assert "BS Detector" in resp.text
