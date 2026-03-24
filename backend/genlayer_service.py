"""
GenLayer Service - Wrapper for interacting with GenLayer contracts
"""

import os
import json
import asyncio
from functools import partial


class GenLayerService:
    def __init__(self):
        self.contract_address = os.environ.get("GENLAYER_CONTRACT_ADDRESS", "")
        self.private_key = os.environ.get("GENLAYER_PRIVATE_KEY", "")
        self.chain_name = os.environ.get("GENLAYER_CHAIN", "studionet")
        self._client = None
        self._account = None

    def _get_client(self):
        if self._client is None:
            from genlayer_py import create_client, create_account
            from genlayer_py import chains

            chain = getattr(chains, self.chain_name)
            self._account = create_account(self.private_key) if self.private_key else create_account()
            self._client = create_client(chain=chain, account=self._account)
        return self._client

    async def verify_claim(self, claim_text: str, source_url: str = "") -> dict:
        """Send a claim to the GenLayer contract for verification."""
        client = self._get_client()

        tx_hash = await asyncio.to_thread(
            partial(
                client.write_contract,
                account=self._account,
                address=self.contract_address,
                function_name="verify_claim",
                args=[claim_text, source_url],
                value=0,
            )
        )

        try:
            receipt = await asyncio.to_thread(
                partial(
                    client.wait_for_transaction_receipt,
                    transaction_hash=tx_hash,
                    interval=6000,
                    retries=100,
                )
            )
            return _parse_receipt(receipt)
        except Exception as e:
            # Timeout or other error - try to get partial result from leader
            error_msg = str(e)
            result = _extract_leader_result_from_error(error_msg)
            if result:
                result["consensus_note"] = "Leader analysis complete. Validator consensus still in progress."
                return result
            raise

    async def verify_url(self, url: str) -> dict:
        """Send a URL to the GenLayer contract for verification."""
        client = self._get_client()

        tx_hash = await asyncio.to_thread(
            partial(
                client.write_contract,
                account=self._account,
                address=self.contract_address,
                function_name="verify_url",
                args=[url],
                value=0,
            )
        )

        receipt = await asyncio.to_thread(
            partial(
                client.wait_for_transaction_receipt,
                transaction_hash=tx_hash,
                interval=6000,
                retries=100,
            )
        )

        return _parse_receipt(receipt)

    async def get_all_results(self) -> dict:
        """Get all stored results from the contract."""
        client = self._get_client()

        result = await asyncio.to_thread(
            partial(
                client.read_contract,
                address=self.contract_address,
                function_name="get_all_results",
                args=[],
            )
        )

        if isinstance(result, str):
            return json.loads(result)
        return result


def _extract_leader_result_from_error(error_msg: str) -> dict:
    """Try to extract the leader's analysis from a timeout error message."""
    try:
        # The error message contains a JSON representation of the transaction
        # Try to find the leader result in the eq_outputs or result payload
        # Look for the readable JSON in the error
        import re
        # Find verdict JSON pattern in the error message
        pattern = r'\{"verdict":\s*"(?:BULLSHIT|LEGIT|INCONCLUSIVE)"[^}]*\}'
        matches = re.findall(pattern, error_msg)
        if matches:
            # Take the last (most complete) match
            for match in reversed(matches):
                try:
                    return json.loads(match)
                except json.JSONDecodeError:
                    continue

        # Try to find escaped JSON
        pattern2 = r'"readable":\s*"(\{.*?\})"'
        matches2 = re.findall(pattern2, error_msg)
        if matches2:
            for match in reversed(matches2):
                try:
                    unescaped = match.replace('\\"', '"').replace('\\\\', '\\')
                    return json.loads(unescaped)
                except (json.JSONDecodeError, ValueError):
                    continue
    except Exception:
        pass
    return {}


def _parse_receipt(receipt) -> dict:
    """Parse a GenLayer transaction receipt into a result dict."""
    # Handle dict receipts (studionet format)
    if isinstance(receipt, dict):
        # Try to extract from leader_receipt
        leader = receipt.get("consensus_data", {}).get("leader_receipt", [])
        if leader:
            lr = leader[0]
            res = lr.get("result", {})
            if isinstance(res, dict) and res.get("status") == "return":
                payload = res.get("payload", {})
                readable = payload.get("readable", "") if isinstance(payload, dict) else ""
                if readable and readable != "null":
                    try:
                        return json.loads(readable)
                    except json.JSONDecodeError:
                        return {"raw": readable}

        # Fallback
        return {
            "status": receipt.get("status_name", "unknown"),
            "tx_hash": receipt.get("hash", ""),
        }

    # Handle object receipts
    if hasattr(receipt, "result") and receipt.result:
        result = receipt.result
        if isinstance(result, str):
            try:
                return json.loads(result)
            except json.JSONDecodeError:
                return {"raw": result}
        return result

    return {
        "status": getattr(receipt, "status", "unknown"),
        "tx_hash": getattr(receipt, "transaction_hash", ""),
    }
