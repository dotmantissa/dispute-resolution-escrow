import hashlib
import json
from pathlib import Path

import pytest
from genlayer_escrow import Document, EscrowClient, ExecutionFailed, execution_succeeded
from genlayer_py import create_account, create_client
from genlayer_py.chains import studionet


@pytest.mark.parametrize("content",[b"",b"x"*32769,b"\x00",b" \n",b"\xff"])
def test_invalid_document_bytes(content):
    with pytest.raises((ValueError,UnicodeDecodeError)):
        Document.from_bytes("https://evidence.example.com/doc",content)


def test_document_hashes_exact_bytes():
    a=Document.from_bytes("https://evidence.example.com/doc",b"terms\n")
    b=Document.from_bytes("https://evidence.example.com/doc",b"terms\r\n")
    assert a.sha256==hashlib.sha256(b"terms\n").hexdigest()
    assert a.sha256!=b.sha256


@pytest.mark.parametrize("url,digest",[("http://example.com","0"*64),("https://example.com","G"*64),("https://example.com","0"*63)])
def test_invalid_document_metadata(url,digest):
    with pytest.raises(ValueError):
        Document(url,digest)


def test_real_document_fetch_matches_committed_evidence():
    manifest=json.loads((Path(__file__).parent/"evidence/manifest.json").read_text())
    doc=Document(**manifest["documents"]["terms.md"])
    assert Document.fetch(doc.url)==doc


@pytest.mark.parametrize("receipt,success",[
    ({},False),({"status":"FINALIZED"},False),
    ({"tx_execution_result":0},False),({"tx_execution_result":1},True),
    ({"tx_execution_result":2},False),({"tx_execution_result":True},False),
    ({"consensus_data":{"leader_receipt":[{"execution_result":"ERROR"}]}},False),
    ({"consensus_data":{"leader_receipt":[{"execution_result":"SUCCESS"}]}},True),
    ({"consensus_data":{"leader_receipt":{"execution_result":"SUCCESS"}}},True),
])
def test_receipt_parser_requires_actual_execution_success(receipt,success):
    assert execution_succeeded(receipt) is success


def test_execution_failure_preserves_receipt():
    receipt={"status":"FINALIZED","tx_execution_result":2}
    assert ExecutionFailed(receipt).receipt is receipt


@pytest.mark.parametrize("principal",[0,-1,True,"100"])
def test_client_rejects_invalid_principal_before_submission(principal):
    sdk=create_client(chain=studionet,account=create_account())
    binding=EscrowClient(sdk,"0x"+"12"*20)
    with pytest.raises(ValueError,match="Principal"):
        binding.create("order","0x"+"34"*20,Document("https://evidence.example.com/terms","0"*64),principal)


@pytest.mark.parametrize("bond",[0,-1,True,"100"])
def test_client_rejects_invalid_bond_before_submission(bond):
    sdk=create_client(chain=studionet,account=create_account())
    binding=EscrowClient(sdk,"0x"+"12"*20)
    with pytest.raises(ValueError,match="Bond"):
        binding.dispute("1",Document("https://evidence.example.com/dispute","0"*64),bond=bond)


def test_payment_result_decodes_rejected_credit_without_calling_it_execution_failure():
    import base64
    from genlayer_py.abi import calldata
    from genlayer_escrow import payment_result,PaymentRejected
    value={"accepted":False,"method":"dispute","escrow_id":"","refund_credit":1001,"error":"Only payer"}
    raw=base64.b64encode(b"\x00"+calldata.encode(value)).decode()
    receipt={"consensus_data":{"leader_receipt":[{"execution_result":"SUCCESS","result":{"raw":raw}}]}}
    assert execution_succeeded(receipt)
    assert payment_result(receipt)==value
    error=PaymentRejected(receipt,value)
    assert error.refund_credit==1001 and error.result==value and error.receipt is receipt
