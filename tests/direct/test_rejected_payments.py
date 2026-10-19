"""Supported payable rejections preserve every incoming wei as caller-owned credit."""
import pytest


def test_rejected_creation_preserves_attached_value(escrow,direct_vm,direct_alice,direct_bob,evidence):
    direct_vm.sender=direct_alice
    direct_vm.value=12345
    d=evidence["terms.md"]
    result=escrow.create_escrow("bad",direct_bob.as_hex,d["url"],d["sha256"],0,100,1000)
    assert not result["accepted"] and result["refund_credit"]==12345
    assert "Delivery period" in result["error"]
    assert escrow.credit_of(direct_alice.as_hex)==12345
    a=escrow.get_accounting()
    assert a["escrow_count"]==0 and a["withdrawal_credits"]==12345 and a["conserved"]


def test_successful_public_creation_returns_explicit_result(escrow,direct_vm,direct_alice,direct_bob,evidence):
    direct_vm.sender=direct_alice
    direct_vm.value=10001
    d=evidence["terms.md"]
    result=escrow.create_escrow("ok",direct_bob.as_hex,d["url"],d["sha256"],100,100,1000)
    assert result=={"accepted":True,"method":"create_escrow","escrow_id":"1","refund_credit":0,"error":""}
    assert escrow.get_escrow("1")["status"]=="FUNDED"


@pytest.mark.parametrize("delta",[-1,1,-1001])
def test_wrong_bond_is_credited_without_opening_dispute(delivered,escrow,direct_vm,direct_alice,evidence,delta):
    d=evidence["dispute-half.md"]
    direct_vm.sender=direct_alice
    amount=1001+delta
    direct_vm.value=amount
    result=escrow.dispute(delivered,d["url"],d["sha256"])
    assert not result["accepted"] and result["refund_credit"]==amount
    assert escrow.get_escrow(delivered)["status"]=="DELIVERED"
    assert escrow.credit_of(direct_alice.as_hex)==amount
    assert escrow.get_accounting()["locked_bonds"]==0 and escrow.get_accounting()["conserved"]


def test_unauthorized_bond_goes_to_its_actual_sender(delivered,escrow,direct_vm,direct_charlie,direct_alice,evidence):
    direct_vm.sender=direct_charlie
    direct_vm.value=1001
    d=evidence["dispute-half.md"]
    result=escrow.dispute(delivered,d["url"],d["sha256"])
    assert not result["accepted"] and "Only payer" in result["error"]
    assert escrow.credit_of(direct_charlie.as_hex)==1001
    assert escrow.credit_of(direct_alice.as_hex)==0
    assert escrow.get_escrow(delivered)["status"]=="DELIVERED"


def test_bad_document_submission_returns_full_payment_credit(escrow,direct_vm,direct_alice,direct_bob,evidence):
    direct_vm.sender=direct_alice
    direct_vm.value=10001
    result=escrow.create_escrow("bad-hash",direct_bob.as_hex,evidence["terms.md"]["url"],"0"*64,100,100,1000)
    assert not result["accepted"] and "SHA-256 mismatch" in result["error"]
    assert escrow.credit_of(direct_alice.as_hex)==10001 and escrow.get_accounting()["conserved"]


def test_lifetime_audit_counters_can_exceed_uint256(escrow,direct_vm,direct_alice,direct_bob,evidence):
    # Lifetime throughput can exceed a single-balance limit without risking overflow.
    ceiling=(1<<256)-1
    escrow.total_deposited=str(ceiling)
    escrow.total_withdrawn=str(ceiling)
    direct_vm.sender=direct_alice
    direct_vm.value=10
    d=evidence["terms.md"]
    result=escrow.create_escrow("next",direct_bob.as_hex,d["url"],d["sha256"],100,100,1000)
    assert result["accepted"]
    assert escrow.get_accounting()["total_deposited"]==ceiling+10
    assert escrow.get_accounting()["conserved"]
