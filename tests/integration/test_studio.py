"""End-to-end custody and consensus on hosted Studio, with real HTTP and models.

Enable explicitly with GENLAYER_PRIVATE_KEY. No mock validators, mock responses,
leader-only execution, or manufactured judgments are used. Actors other than the
payer are generated and kept in a mode-600 file outside the repository for recovery.
"""
import base64
import hashlib
import json
import os
from pathlib import Path
import secrets
import tempfile
import time

import pytest
from genlayer_py import create_account, create_client
from genlayer_py.chains import studionet
from genlayer_py.types import TransactionStatus
from genlayer_escrow import Document, EscrowClient, execution_succeeded, payment_result, PaymentRejected
from tests.integration.transport import attach_transport

ROOT=Path(__file__).resolve().parents[2]
pytestmark=[pytest.mark.integration,pytest.mark.skipif(not os.environ.get("GENLAYER_PRIVATE_KEY"),
             reason="Set GENLAYER_PRIVATE_KEY to run real Studio transactions")]
PRINCIPAL=10001


def leader(receipt):
    rows=(receipt.get("consensus_data") or {}).get("leader_receipt") or []
    return rows[0] if isinstance(rows,list) and rows else rows if isinstance(rows,dict) else {}


def failure_text(receipt):
    result=leader(receipt).get("result",{})
    if isinstance(result,dict):
        payload=result.get("payload",{})
        if isinstance(payload,str):
            return payload
        raw=payload.get("raw") if isinstance(payload,dict) else None
        raw=raw or result.get("raw")
        if isinstance(raw,str):
            try:
                return base64.b64decode(raw)[1:].decode(errors="replace")
            except Exception:
                pass
        if isinstance(raw,list):
            return bytes(raw[1:]).decode(errors="replace")
    return json.dumps(result,default=str)


class Live:
    def __init__(self, report_name="studio-verification.json"):
        self.deployment=json.loads((ROOT/"artifacts/deployment.json").read_text())
        self.address=self.deployment["contract_address"]
        self.payer=create_client(chain=studionet,account=create_account(os.environ["GENLAYER_PRIVATE_KEY"]))
        secret_path=os.environ.get("GENLAYER_TEST_KEYS_FILE")
        if not secret_path:
            fd,secret_path=tempfile.mkstemp(prefix="escrow-test-actors-",suffix=".json")
            os.close(fd)
        self.secret_path=Path(secret_path)
        if not self.secret_path.exists():
            self.secret_path.parent.mkdir(parents=True,exist_ok=True)
            self.secret_path.touch(mode=0o600)
        self.secret_path.chmod(0o600)
        if self.secret_path.stat().st_size:
            keys=json.loads(self.secret_path.read_text())
        else:
            keys={name:"0x"+secrets.token_hex(32) for name in ("payee","outsider")}
            self.secret_path.write_text(json.dumps(keys))
        self.payee=create_client(chain=studionet,account=create_account(keys["payee"]))
        self.outsider=create_client(chain=studionet,account=create_account(keys["outsider"]))
        for client in (self.payer,self.payee,self.outsider):
            attach_transport(client)
        self.bindings={name:EscrowClient(getattr(self,name),self.address) for name in ("payer","payee","outsider")}
        self.manifest=json.loads((ROOT/"tests/evidence/manifest.json").read_text())["documents"]
        self.run=secrets.token_hex(6)
        self.path=ROOT/"artifacts"/report_name
        self.report={"run_id":self.run,"network":"studionet","contract_address":self.address,
             "source_sha256":self.deployment["source_sha256"],"started_at":int(time.time()),
             "actors":{name:getattr(self,name).local_account.address for name in self.bindings},
             "transactions":[],"scenarios":[]}
        if self.path.exists() and os.environ.get("GENLAYER_RESUME_RUN"):
            self.report=json.loads(self.path.read_text())
            self.run=self.report["run_id"]
        elif self.path.exists():
            old=self.path.with_name(self.path.stem+"-"+str(int(time.time()))+".json")
            self.path.rename(old)
        self.save()
        print("Recover actor keys from:",self.secret_path,flush=True)
        for client in (self.payer,self.payee,self.outsider):
            result=self.payer.provider.make_request("sim_fundAccount",[client.local_account.address,10**18])
            assert "error" not in result,result
            time.sleep(2)

    def save(self):
        temporary=self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(self.report,indent=2,default=str)+"\n")
        temporary.replace(self.path)

    def doc(self,name):
        return Document(**self.manifest[name])

    def read(self,method,args=None,address=None):
        time.sleep(1)
        return self.payer.read_contract(address=address or self.address,function_name=method,args=args or [])

    def balance(self,address):
        time.sleep(1)
        return self.payer.get_balance(address)

    def tx(self,role,method,args,value=0,*,error=None,address=None):
        time.sleep(2)
        client=getattr(self,role)
        txid=client.write_contract(address=address or self.address,function_name=method,
                                  args=args,value=value,leader_only=False)
        entry={"method":method,"caller":client.local_account.address,"transaction_hash":txid,
               "value":value,"expected":("payment_rejection" if method in ("create_escrow","dispute") else "revert") if error else "success","state":"SUBMITTED"}
        self.report["transactions"].append(entry)
        self.save()
        print(method,txid,flush=True)
        receipt=client.wait_for_transaction_receipt(transaction_hash=txid,
                    status=TransactionStatus.FINALIZED if method=="withdraw" else TransactionStatus.ACCEPTED,
                    interval=6000,retries=150,full_transaction=True)
        success=execution_succeeded(receipt)
        votes=receipt.get("consensus_data",{}).get("votes",{})
        entry.update(state="FINALIZED" if method=="withdraw" else "ACCEPTED",execution="SUCCESS" if success else "REVERT",
                     votes=votes,agree_count=sum(str(v).lower()=="agree" for v in votes.values()))
        if not success:
            entry["error"]=failure_text(receipt)
        self.save()
        if error and method in ("create_escrow","dispute"):
            assert success,receipt
            outcome=payment_result(receipt)
            assert outcome is not None and not outcome["accepted"],receipt
            assert error in outcome["error"] and outcome["refund_credit"]==value,outcome
            entry["payment_result"]=outcome
            self.save()
        elif error:
            assert not success,receipt
            assert error in failure_text(receipt),failure_text(receipt)
        else:
            assert success,receipt
        return receipt

    def create(self,label,*,terms="terms.md",delivery_period=3600,review_period=3600):
        reference=self.run+":"+label
        # Recover a funded creation after an interrupted read without depositing twice.
        previous=next((entry for entry in self.report["transactions"]
                       if entry.get("reference")==reference),None)
        if previous:
            self.bindings["payer"].wait(previous["transaction_hash"])
            existing=self.bindings["payer"].find_escrow(self.payer.local_account.address,reference)
            record=self.bindings["payer"].get_escrow(existing)
            if record["status"] not in ("FUNDED","DELIVERED","DISPUTED"):
                raise RuntimeError("Existing test scenario is terminal; reconcile its journal before resuming")
            print("Recovered open escrow",existing,record["status"],flush=True)
            return existing
        doc=self.doc(terms)
        # Exercise the shipped builder client for the funded creation.
        time.sleep(2)
        txid=self.bindings["payer"].create(reference,self.payee.local_account.address,doc,
                    PRINCIPAL,delivery_period,review_period,1000)
        self.report["transactions"].append({"method":"create_escrow","transaction_hash":txid,
              "reference":reference,"value":PRINCIPAL,"state":"SUBMITTED"})
        self.save()
        print("create_escrow",txid,flush=True)
        receipt=self.bindings["payer"].wait(txid,finalized=False)
        self.report["transactions"][-1].update(state="ACCEPTED",execution="SUCCESS",
                    votes=receipt.get("consensus_data",{}).get("votes",{}))
        self.save()
        eid=self.bindings["payer"].find_escrow(self.payer.local_account.address,reference,finalized=False)
        assert eid
        r=self.bindings["payer"].get_escrow(eid,finalized=False)
        assert r["principal"]==PRINCIPAL and r["status"]=="FUNDED"
        return eid

    def deliver(self,eid,name="delivery-full.md"):
        d=self.doc(name)
        record=self.read("get_escrow",[eid])
        if record["delivery"] is not None:
            assert record["delivery"]["url"]==d.url and record["delivery"]["sha256"]==d.sha256
            print("Recovered committed delivery",eid,flush=True)
            return
        self.tx("payee","claim_delivery",[eid,d.url,d.sha256])

    def dispute(self,eid,name="dispute-good-faith.md"):
        d=self.doc(name)
        record=self.read("get_escrow",[eid])
        bond=record["bond_required"]
        if record["status"]=="DISPUTED":
            assert record["dispute"]["url"]==d.url and record["dispute"]["sha256"]==d.sha256
            assert record["bond_paid"]==bond
            print("Recovered committed dispute",eid,flush=True)
            return bond
        self.tx("payer","dispute",[eid,d.url,d.sha256],value=bond)
        return bond

    def finalize_journal(self):
        # Pipeline accepted transactions to reduce redundant finality polling, then
        # recheck every actual execution at FINALIZED before claiming completion.
        for entry in self.report["transactions"]:
            if entry["state"]=="FINALIZED":
                continue
            receipt=self.payer.wait_for_transaction_receipt(
                transaction_hash=entry["transaction_hash"],status=TransactionStatus.FINALIZED,
                interval=12000,retries=90)
            succeeded=execution_succeeded(receipt)
            assert succeeded==(entry.get("expected","success")!="revert"),receipt
            entry["state"]="FINALIZED"
            entry["finalized_execution"]="SUCCESS" if succeeded else "REVERT"
            self.save()
        self.report["all_transactions_finalized"]=True
        self.save()

    def check_accounting(self):
        accounting=self.read("get_accounting")
        assert accounting["conserved"]
        actual=self.balance(self.address)
        assert actual==accounting["accounted_balance"],(actual,accounting)
        return accounting


@pytest.fixture(scope="module")
def live():
    instance=Live()
    yield instance
    instance.report["finished_at"]=int(time.time())
    instance.save()


def test_01_deployed_source_schema_and_config(live):
    assert hashlib.sha256((ROOT/"contracts/dispute_escrow.py").read_bytes()).hexdigest()==live.deployment["source_sha256"]
    code=live.payer.provider.make_request("gen_getContractCode",[live.address])
    assert base64.b64decode(code["result"])==(ROOT/"contracts/dispute_escrow.py").read_bytes()
    time.sleep(2)
    response=live.payer.provider.make_request("gen_getContractSchema",[live.address])
    assert "error" not in response,response
    config=live.bindings["payer"].get_config()
    assert config["asset"]=="native GEN" and config["administrator"] is None
    assert config["transfer_timing"]=="finalized"
    live.check_accounting()


def test_02_funded_custody_auth_reverts_and_acceptance(live):
    before=live.balance(live.address)
    eid=live.create("accept")
    assert live.balance(live.address)==before+PRINCIPAL
    d=live.doc("delivery-full.md")
    live.tx("outsider","claim_delivery",[eid,d.url,d.sha256],error="Only payee")
    live.tx("payee","claim_delivery",[eid,d.url,"0"*64],error="SHA-256 mismatch")
    live.deliver(eid)
    live.tx("outsider","accept_delivery",[eid],error="Only payer")
    payee_before=live.read("credit_of",[live.payee.local_account.address])
    live.tx("payer","accept_delivery",[eid])
    assert live.read("credit_of",[live.payee.local_account.address])==payee_before+PRINCIPAL
    live.tx("payer","accept_delivery",[eid],error="DELIVERED")
    live.check_accounting()
    live.report["scenarios"].append({"case":"payer_acceptance","escrow_id":eid,"verified":True})
    live.save()


@pytest.mark.parametrize("label,delivery,dispute,share,bad",[
    ("partial","delivery-half.md","dispute-half.md",5000,False),
    ("no-delivery","delivery-none.md","dispute-none.md",0,False),
    ("bad-faith","delivery-full.md","dispute-bad-faith.md",10000,True),
    ("honest-dispute","delivery-full.md","dispute-good-faith.md",10000,False),
    ("prompt-injection","delivery-injection.md","dispute-none.md",0,False),
])
def test_03_real_validator_adjudication(live,label,delivery,dispute,share,bad):
    eid=live.create(label)
    live.deliver(eid,delivery)
    bond=live.dispute(eid,dispute)
    assert live.read("get_escrow",[eid])["status"]=="DISPUTED"
    if label=="partial":
        live.tx("outsider","release_expired",[eid],error="DELIVERED")
    receipt=live.tx("outsider","adjudicate",[eid])
    votes=receipt.get("consensus_data",{}).get("votes",{})
    assert len(votes)>=3 and sum(str(v).lower()=="agree" for v in votes.values())>=3,votes
    r=live.read("get_escrow",[eid])
    assert r["last_assessment"]["conclusive"] is True,r
    assert r["payee_bps"]==share and r["payer_bad_faith"] is bad,r
    payee=PRINCIPAL*share//10000+(bond if bad else 0)
    assert r["payee_credit"]==payee and r["payer_credit"]==PRINCIPAL+bond-payee
    assert r["assessment_count"]==1
    if label=="partial":
        live.tx("outsider","adjudicate",[eid],error="DISPUTED")
    live.check_accounting()
    live.report["scenarios"].append({"case":label,"escrow_id":eid,"payee_bps":share,
        "payer_bad_faith":bad,"payee_credit":payee,"payer_credit":PRINCIPAL+bond-payee,
        "assessment":r["last_assessment"],"verified":True})
    live.save()


def test_04_inconclusive_preserves_funds_and_bilateral_exit(live):
    eid=live.create("inconclusive",terms="terms-inconclusive.md")
    live.deliver(eid,"delivery-inconclusive.md")
    bond=live.dispute(eid,"dispute-inconclusive.md")
    before=live.check_accounting()
    live.tx("outsider","adjudicate",[eid])
    r=live.read("get_escrow",[eid])
    assert r["status"]=="DISPUTED" and r["last_assessment"]["conclusive"] is False,r
    assert live.check_accounting()==before
    live.tx("payer","offer_settlement",[eid,3000])
    live.tx("payer","cancel_offer",[eid])
    live.tx("payee","offer_settlement",[eid,3000])
    assert live.read("get_escrow",[eid])["status"]=="DISPUTED"
    live.tx("payer","offer_settlement",[eid,3000])
    r=live.read("get_escrow",[eid])
    assert r["payee_credit"]==3000 and r["payer_credit"]==PRINCIPAL+bond-3000
    live.check_accounting()
    live.report["scenarios"].append({"case":"inconclusive_and_bilateral_exit","escrow_id":eid,"verified":True})
    live.save()


def test_05_delivery_timeout_review_timeout_and_rejection(live):
    eid=live.create("delivery-timeout",delivery_period=1)
    live.tx("outsider","refund_undelivered",[eid])
    assert live.read("get_escrow",[eid])["payer_credit"]==PRINCIPAL
    eid2=live.create("review-timeout",review_period=1)
    live.deliver(eid2)
    live.tx("outsider","release_expired",[eid2])
    assert live.read("get_escrow",[eid2])["payee_credit"]==PRINCIPAL
    eid3=live.create("rejection")
    live.tx("payee","reject_escrow",[eid3])
    assert live.read("get_escrow",[eid3])["status"]=="REFUNDED"
    live.check_accounting()
    live.report["scenarios"].append({"case":"timeouts_and_rejection","escrow_ids":[eid,eid2,eid3],"verified":True})
    live.save()


def test_06_rejected_bonds_and_duplicate_reference_credits(live):
    eid=live.create("bond-reverts")
    live.deliver(eid)
    doc=live.doc("dispute-half.md")
    r=live.read("get_escrow",[eid])
    before=live.balance(live.address)
    live.tx("payer","dispute",[eid,doc.url,doc.sha256],value=r["bond_required"]-1,error="exact dispute bond")
    live.tx("outsider","dispute",[eid,doc.url,doc.sha256],value=r["bond_required"],error="Only payer")
    assert live.balance(live.address)==before+2*r["bond_required"]-1
    assert live.read("get_escrow",[eid])["status"]=="DELIVERED"
    live.check_accounting()
    terms=live.doc("terms.md")
    live.tx("payer","create_escrow",[r["reference"],r["payee"],terms.url,terms.sha256,100,100,1000],
            value=PRINCIPAL,error="Reference already used")
    assert live.balance(live.address)==before+2*r["bond_required"]-1+PRINCIPAL
    live.tx("payer","create_escrow",[r["reference"]+":bad-document",r["payee"],terms.url,"0"*64,100,100,1000],
            value=17,error="SHA-256 mismatch")
    rejected_tx=live.report["transactions"][-1]["transaction_hash"]
    with pytest.raises(PaymentRejected) as rejected:
        live.bindings["payer"].wait(rejected_tx)
    assert rejected.value.refund_credit==17
    assert live.balance(live.address)==before+2*r["bond_required"]-1+PRINCIPAL+17
    live.tx("payer","accept_delivery",[eid])
    live.check_accounting()


def test_07_native_withdrawals_to_account_and_real_intelligent_contract(live):
    # Deploy a real receiver. Its receive method executes in a child transaction.
    source=(ROOT/"tests/integration/contracts/value_receiver.py").read_bytes()
    txid=live.payer.deploy_contract(code=source,args=[],leader_only=False)
    live.report["transactions"].append({"method":"deploy_value_receiver","transaction_hash":txid,"state":"SUBMITTED"})
    live.save()
    receipt=live.payer.wait_for_transaction_receipt(transaction_hash=txid,
             status=TransactionStatus.FINALIZED,interval=6000,retries=150)
    assert execution_succeeded(receipt),receipt
    receiver=receipt.get("contract_address") or receipt.get("to_address")
    live.report["transactions"][-1].update(state="FINALIZED",execution="SUCCESS",contract_address=receiver)
    live.save()
    payer=live.payer.local_account.address
    payee=live.payee.local_account.address
    payer_credit=live.read("credit_of",[payer])
    payee_credit=live.read("credit_of",[payee])
    assert payer_credit>0 and payee_credit>0
    outsider=live.outsider.local_account.address
    outsider_credit=live.read("credit_of",[outsider])
    live.tx("outsider","withdraw",[outsider_credit+1,payer,"account"],error="Insufficient withdrawal credit")
    if outsider_credit:
        live.tx("outsider","withdraw",[outsider_credit,outsider,"account"])
    live.tx("payer","withdraw",[payer_credit+1,payer,"account"],error="Insufficient withdrawal credit")
    before=live.balance(payee)
    live.tx("payee","withdraw",[payee_credit,payee,"account"])
    assert live.balance(payee)==before+payee_credit
    live.tx("payer","withdraw",[payer_credit,receiver,"contract"])
    # Child IC execution may finalize after its parent; follow the emitted transaction.
    deadline=time.monotonic()+600
    while time.monotonic()<deadline:
        received=live.read("get_received",address=receiver)
        if received==payer_credit:
            break
        time.sleep(6)
    assert received==payer_credit
    assert live.read("get_balance",address=receiver)==payer_credit
    live.tx("payer","withdraw",[1,payer,"account"],error="Insufficient withdrawal credit")
    assert live.read("credit_of",[payer])==0 and live.read("credit_of",[payee])==0
    accounting=live.check_accounting()
    assert accounting["locked_principal"]==0 and accounting["locked_bonds"]==0
    assert accounting["withdrawal_credits"]==0 and accounting["accounted_balance"]==0
    live.finalize_journal()
    live.report.update(complete=True,final_accounting=accounting,
                receiver_address=receiver,receiver_received=payer_credit,
                payee_withdrawn=payee_credit)
    live.save()
