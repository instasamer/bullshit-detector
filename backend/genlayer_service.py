"""
GenLayer Service - Wrapper for interacting with GenLayer contracts
"""

import os
import json
import asyncio
from functools import partial


def _patch_genlayer_provider():
    """
    Patch genlayer_py provider to send a browser User-Agent header.
    Without this, Cloudflare blocks requests to rpc-bradbury.genlayer.com.
    Also patches actions.py to fix valid_until=0 and CreatedTransaction event name.
    """
    import time as _time
    import requests as _requests
    try:
        from genlayer_py.provider import provider as _prov_mod
        _orig_make_request = _prov_mod.GenLayerProvider.make_request

        def _patched_make_request(self, method, params):
            import requests
            payload = {
                "jsonrpc": "2.0",
                "id": int(_time.time() * 1000),
                "method": method,
                "params": params,
            }
            try:
                response = requests.post(
                    self.url,
                    json=payload,
                    headers={
                        "Content-Type": "application/json",
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36",
                    },
                )
            except requests.exceptions.RequestException as err:
                from genlayer_py.exceptions import GenLayerError
                raise GenLayerError(f"Request to {self.url} failed: {str(err)}") from err
            try:
                resp = response.json()
            except ValueError as err:
                from genlayer_py.exceptions import GenLayerError
                preview = response.text[:500] if len(response.text) <= 500 else f"{response.text[:500]}..."
                raise GenLayerError(f"{method} returned invalid JSON: {err}. Response content: {preview}") from err
            self._raise_on_error(resp, method)
            return resp

        _prov_mod.GenLayerProvider.make_request = _patched_make_request
    except Exception:
        pass

    try:
        import genlayer_py.contracts.actions as _actions
        _orig_encode = _actions._encode_add_transaction_data

        def _patched_encode(self, sender_account, recipient, consensus_max_rotations, data, valid_until=0):
            from eth_abi import encode as abi_encode
            import eth_utils
            consensus_main_contract = self.w3.eth.contract(
                abi=self.chain.consensus_main_contract["abi"]
            )
            contract_fn = consensus_main_contract.get_function_by_name("addTransaction")
            add_transaction_args = [
                sender_account.address,
                recipient,
                self.chain.default_number_of_initial_validators,
                consensus_max_rotations,
                self.w3.to_bytes(hexstr=data),
            ]
            if len(contract_fn.argument_types) >= 6:
                effective_valid_until = valid_until if valid_until > 0 else int(_time.time()) + 3600
                add_transaction_args.append(effective_valid_until)
            params = abi_encode(contract_fn.argument_types, add_transaction_args)
            function_selector = eth_utils.keccak(text=contract_fn.signature)[:4].hex()
            return "0x" + function_selector + params.hex()

        _actions._encode_add_transaction_data = _patched_encode

        from web3.logs import DISCARD
        _orig_send = _actions._send_transaction

        def _patched_send(self, encoded_data, sender_account=None, value=0, sim_config=None):
            from genlayer_py.exceptions import GenLayerError
            if sender_account is None:
                raise GenLayerError("No account set.")
            if self.chain.consensus_main_contract is None:
                raise GenLayerError("Consensus main contract not initialized.")
            transaction = _actions._prepare_transaction(
                self=self,
                sender=sender_account.address,
                recipient=self.chain.consensus_main_contract["address"],
                data=encoded_data,
                value=value,
            )
            signed_transaction = sender_account.sign_transaction(transaction)
            serialized_transaction = self.w3.to_hex(signed_transaction.raw_transaction)
            params = [serialized_transaction]
            if sim_config is not None:
                params.append(sim_config)
            tx_hash = self.provider.make_request(
                method="eth_sendRawTransaction", params=params
            )["result"]
            tx_receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash)
            if tx_receipt.status != 1:
                raise GenLayerError("Transaction failed")
            consensus_main_contract = self.w3.eth.contract(
                abi=self.chain.consensus_main_contract["abi"]
            )
            events = []
            for event_name in ("CreatedTransaction", "NewTransaction"):
                try:
                    event = consensus_main_contract.get_event_by_name(event_name)
                    events = event.process_receipt(tx_receipt, DISCARD)
                    if events:
                        break
                except Exception:
                    continue
            if len(events) == 0:
                raise GenLayerError("Transaction not processed by consensus")
            return self.w3.to_hex(events[0]["args"]["txId"])

        _actions._send_transaction = _patched_send
    except Exception:
        pass

    # Patch GenLayerRawTransaction.LastRound.decode to handle Bradbury bytes32 votes
    try:
        from genlayer_py.types.transactions import GenLayerRawTransaction, VOTE_TYPE_NUMBER_TO_NAME as _VOTE_MAP

        def _patched_last_round_decode(self):
            return {
                "round": str(self.round),
                "leader_index": str(self.leader_index),
                "votes_committed": str(self.votes_committed),
                "votes_revealed": str(self.votes_revealed),
                "appeal_bond": str(self.appeal_bond),
                "rotations_left": str(self.rotations_left),
                "result": str(self.result),
                "round_validators": self.round_validators,
                "validator_votes_hash": self.validator_votes_hash,
                "validator_votes": self.validator_votes,
                "validator_votes_name": [
                    _VOTE_MAP[str(vote)].value if str(vote) in _VOTE_MAP else str(vote)
                    for vote in self.validator_votes
                ],
            }

        GenLayerRawTransaction.LastRound.decode = _patched_last_round_decode
    except Exception:
        pass


_patch_genlayer_provider()


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

        # Wait for ACCEPTED (validators have reached consensus)
        await asyncio.to_thread(
            partial(
                client.wait_for_transaction_receipt,
                transaction_hash=tx_hash,
                interval=6000,
                retries=100,
            )
        )

        # Extract verdict from consensus data contract directly
        return await asyncio.to_thread(
            partial(_extract_verdict_from_tx, client, tx_hash)
        )

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

        await asyncio.to_thread(
            partial(
                client.wait_for_transaction_receipt,
                transaction_hash=tx_hash,
                interval=6000,
                retries=100,
            )
        )

        return await asyncio.to_thread(
            partial(_extract_verdict_from_tx, client, tx_hash)
        )

    async def get_all_results(self) -> dict:
        """Get cached results from memory (on-chain read is unavailable on testnet)."""
        return {}


def _extract_verdict_from_tx(client, tx_hash: str) -> dict:
    """
    Extract verdict JSON from a completed GenLayer transaction using
    getTransactionAllData on the consensus_data_contract.
    Falls back to error message parsing if raw data extraction fails.
    """
    import re
    try:
        import eth_utils
        from eth_abi import encode as abi_encode
        from web3 import Web3

        w3 = client.w3
        chain = client.chain
        cdc = w3.eth.contract(abi=chain.consensus_data_contract["abi"])
        fn = cdc.get_function_by_name("getTransactionAllData")
        selector = eth_utils.keccak(text=fn.signature)[:4].hex()
        tx_bytes = bytes.fromhex(tx_hash[2:] if tx_hash.startswith("0x") else tx_hash)
        encoded = abi_encode(fn.argument_types, [tx_bytes])
        call_data = "0x" + selector + encoded.hex()

        from genlayer_py.provider.provider import GenLayerProvider
        provider = client.provider
        result = provider.make_request(
            method="eth_call",
            params=[{"to": chain.consensus_data_contract["address"], "data": call_data}, "latest"],
        )["result"]

        raw_bytes = bytes.fromhex(result[2:]) if result and result != "0x" else b""
        text = raw_bytes.decode("utf-8", errors="replace")

        # Find verdict JSON in the raw bytes
        pattern = r'\{"verdict"\s*:\s*"(?:BULLSHIT|LEGIT|INCONCLUSIVE)"[^{}]*\}'
        matches = re.findall(pattern, text)
        for match in reversed(matches):
            try:
                return json.loads(match)
            except json.JSONDecodeError:
                continue
    except Exception:
        pass

    return {"verdict": "INCONCLUSIVE", "confidence": 0, "reason": "Could not extract result from consensus data", "red_flags": [], "evidence_summary": ""}


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
