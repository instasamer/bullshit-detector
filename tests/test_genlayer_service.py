"""Tests for GenLayer service helper functions."""

import json
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from genlayer_service import _extract_leader_result_from_error, _parse_receipt


class TestExtractLeaderResult:
    def test_extracts_verdict_from_error(self):
        error = 'some error {"verdict": "BULLSHIT", "confidence": 85, "reason": "test"} more text'
        result = _extract_leader_result_from_error(error)
        assert result["verdict"] == "BULLSHIT"
        assert result["confidence"] == 85

    def test_returns_empty_on_no_match(self):
        result = _extract_leader_result_from_error("some random error")
        assert result == {}

    def test_returns_empty_on_empty_string(self):
        result = _extract_leader_result_from_error("")
        assert result == {}

    def test_picks_last_match(self):
        error = '{"verdict": "LEGIT"} then {"verdict": "BULLSHIT", "confidence": 90}'
        result = _extract_leader_result_from_error(error)
        assert result["verdict"] == "BULLSHIT"


class TestParseReceipt:
    def test_parses_dict_receipt_with_leader(self):
        receipt = {
            "consensus_data": {
                "leader_receipt": [{
                    "result": {
                        "status": "return",
                        "payload": {
                            "readable": json.dumps({
                                "verdict": "LEGIT",
                                "confidence": 80,
                                "reason": "checks out",
                            })
                        }
                    }
                }]
            }
        }
        result = _parse_receipt(receipt)
        assert result["verdict"] == "LEGIT"
        assert result["confidence"] == 80

    def test_fallback_dict_receipt(self):
        receipt = {"status_name": "ACCEPTED", "hash": "0xabc"}
        result = _parse_receipt(receipt)
        assert result["status"] == "ACCEPTED"
        assert result["tx_hash"] == "0xabc"

    def test_parses_object_receipt_with_string_result(self):
        class FakeReceipt:
            result = json.dumps({"verdict": "INCONCLUSIVE", "confidence": 50})
            status = "ok"
            transaction_hash = "0x123"

        result = _parse_receipt(FakeReceipt())
        assert result["verdict"] == "INCONCLUSIVE"

    def test_parses_object_receipt_with_dict_result(self):
        class FakeReceipt:
            result = {"verdict": "BULLSHIT", "confidence": 95}

        result = _parse_receipt(FakeReceipt())
        assert result["verdict"] == "BULLSHIT"

    def test_fallback_object_receipt(self):
        class FakeReceipt:
            result = None
            status = "PENDING"
            transaction_hash = "0xdef"

        result = _parse_receipt(FakeReceipt())
        assert result["status"] == "PENDING"
