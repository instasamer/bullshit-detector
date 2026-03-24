"""
Deploy the BullshitDetector contract to GenLayer Studionet
"""

import os
import sys
import json
from genlayer_py import create_client, create_account, generate_private_key
from genlayer_py.chains import studionet
from genlayer_py.types import TransactionStatus

def main():
    # Create or load account
    private_key = generate_private_key()
    account = create_account(private_key)
    print(f"Account address: {account.address}")

    # Create client
    client = create_client(chain=studionet, account=account)

    # Read contract code
    contract_path = os.path.join(os.path.dirname(__file__), "contracts", "bullshit_detector.py")
    with open(contract_path, "r") as f:
        contract_code = f.read()

    print(f"Contract code loaded ({len(contract_code)} bytes)")
    print(f"Deploying to Studionet (https://studio.genlayer.com/api)...")

    # Deploy the contract
    try:
        tx_hash = client.deploy_contract(
            account=account,
            contract_code=contract_code,
            args=[],
        )
        print(f"Deploy TX hash: {tx_hash}")

        # Wait for transaction to be accepted
        print("Waiting for transaction to be accepted...")
        receipt = client.wait_for_transaction_receipt(
            transaction_hash=tx_hash,
            status=TransactionStatus.ACCEPTED,
        )
        print(f"Receipt: {receipt}")

        # Extract contract address
        if hasattr(receipt, 'contract_address'):
            contract_address = receipt.contract_address
        elif isinstance(receipt, dict):
            contract_address = receipt.get('contract_address', receipt.get('contractAddress', 'unknown'))
        else:
            contract_address = str(receipt)

        print(f"\n{'='*60}")
        print(f"CONTRACT DEPLOYED SUCCESSFULLY!")
        print(f"Contract address: {contract_address}")
        print(f"Account address:  {account.address}")
        print(f"{'='*60}")

        # Save config
        config = {
            "contract_address": str(contract_address),
            "account_address": str(account.address),
            "chain": "studionet",
            "rpc": "https://studio.genlayer.com/api",
        }

        config_path = os.path.join(os.path.dirname(__file__), "deploy_config.json")
        with open(config_path, "w") as f:
            json.dump(config, f, indent=2)
        print(f"\nConfig saved to {config_path}")

    except Exception as e:
        print(f"Deploy failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
