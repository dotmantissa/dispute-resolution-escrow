"""Deploy the exact checked-in primitive to Studio using GENLAYER_PRIVATE_KEY.

The transaction ID is persisted before polling so an interrupted deployment can
be recovered without submitting a second deployment.
"""
import hashlib
import json
import os
from pathlib import Path
import time

from genlayer_py import create_account, create_client
from genlayer_py.chains import studionet
from genlayer_py.types import TransactionStatus
from genlayer_escrow import execution_succeeded

ROOT = Path(__file__).resolve().parents[2]


def main():
    source = (ROOT / "contracts/dispute_escrow.py").read_bytes()
    account = create_account(os.environ["GENLAYER_PRIVATE_KEY"])
    client = create_client(chain=studionet, account=account)
    path = ROOT / "artifacts/deployment.json"
    digest = hashlib.sha256(source).hexdigest()
    if path.exists():
        data = json.loads(path.read_text())
        if data["source_sha256"] != digest:
            raise RuntimeError("Source changed since recorded deployment; archive the old manifest before redeploying")
        txid = data["transaction_hash"]
    else:
        txid = client.deploy_contract(code=source,args=[],leader_only=False)
        data = {"network":"studionet","rpc":"https://studio.genlayer.com/api",
                "deployer":account.address,"source":"contracts/dispute_escrow.py",
                "source_sha256":digest,"transaction_hash":txid,"state":"SUBMITTED"}
        path.write_text(json.dumps(data,indent=2,default=str)+"\n")
    print("Deployment transaction:",txid,flush=True)
    receipt=client.wait_for_transaction_receipt(transaction_hash=txid,
                status=TransactionStatus.FINALIZED,interval=6000,retries=180)
    if not execution_succeeded(receipt):
        (ROOT/"artifacts/failed-deployment.json").write_text(json.dumps(receipt,indent=2,default=str)+"\n")
        raise RuntimeError("Deployment execution failed; inspect artifacts/failed-deployment.json")
    address=receipt.get("contract_address") or receipt.get("to_address")
    if not address:
        raise RuntimeError("No contract address in successful deployment receipt")
    schema=client.get_contract_schema(address=address)
    data.update(state="FINALIZED",contract_address=address,
                explorer_url="https://explorer-studio.genlayer.com/address/"+address,
                execution_result="SUCCESS",verified_at=int(time.time()),
                votes=receipt.get("consensus_data",{}).get("votes",{}))
    path.write_text(json.dumps(data,indent=2,default=str)+"\n")
    (ROOT/"artifacts/schema.json").write_text(json.dumps(schema,indent=2,default=str)+"\n")
    print("Finalized contract:",address,flush=True)


if __name__=="__main__":
    main()
