"""Adversarial state and accounting properties using the real direct-mode SDK."""
import pytest


def test_uint256_registry_ceiling_rejects_unrepresentable_liability(create,escrow,direct_vm):
    # The registry reserves space for an escrow's possible bond before accepting it.
    ceiling=(1<<256)-1
    with direct_vm.expect_revert("Registry value limit"):
        create(principal=ceiling,bond_bps=1)
    assert escrow.get_accounting()["total_deposited"]==0


def test_distinct_payers_can_reuse_a_reference(create,escrow,direct_vm,direct_alice,direct_bob,direct_charlie,evidence):
    first=create(reference="same-reference")
    direct_vm.sender=direct_charlie
    direct_vm.value=1
    d=evidence["terms.md"]
    second=escrow.create_escrow("same-reference",direct_bob.as_hex,d["url"],d["sha256"],100,100,1000)
    assert second!=first
    assert escrow.find_escrow(direct_alice.as_hex,"same-reference")==first
    assert escrow.find_escrow(direct_charlie.as_hex,"same-reference")==second


def test_wrong_party_cannot_submit_dispute(delivered,escrow,direct_vm,direct_bob,evidence):
    direct_vm.sender=direct_bob
    direct_vm.value=escrow.get_escrow(delivered)["bond_required"]
    d=evidence["dispute-half.md"]
    with direct_vm.expect_revert("Only payer"):
        escrow.dispute(delivered,d["url"],d["sha256"])


def test_dispute_replay_is_blocked_before_new_value_is_recorded(disputed,escrow,direct_vm,direct_alice,evidence):
    before=escrow.get_accounting()
    direct_vm.sender=direct_alice
    direct_vm.value=1001
    d=evidence["dispute-half.md"]
    with direct_vm.expect_revert("DELIVERED"):
        escrow.dispute(disputed,d["url"],d["sha256"])
    assert escrow.get_accounting()==before


@pytest.mark.parametrize("share",[-1,10001,True])
def test_invalid_bilateral_share_does_not_create_consent(disputed,escrow,direct_vm,direct_alice,share):
    direct_vm.sender=direct_alice
    with direct_vm.expect_revert("Share outside"):
        escrow.offer_settlement(disputed,share)
    assert escrow.get_escrow(disputed)["payer_offer"]==-1


def test_payee_cannot_reject_after_delivery(delivered,escrow,direct_vm,direct_bob):
    direct_vm.sender=direct_bob
    with direct_vm.expect_revert("FUNDED"):
        escrow.reject_escrow(delivered)


def test_settlement_replay_cannot_credit_a_second_time(disputed,escrow,direct_vm,direct_alice,direct_bob):
    direct_vm.sender=direct_alice
    escrow.offer_settlement(disputed,5000)
    direct_vm.sender=direct_bob
    escrow.offer_settlement(disputed,5000)
    before=escrow.get_accounting()
    for fn,args in [
        (escrow.offer_settlement,[disputed,5000]),(escrow.cancel_offer,[disputed]),
        (escrow.refund_undelivered,[disputed]),(escrow.release_expired,[disputed]),
        (escrow.adjudicate,[disputed]),
    ]:
        with direct_vm.expect_revert():
            fn(*args)
    assert escrow.get_accounting()==before


def test_credit_does_not_grant_an_outsider_withdrawal_right(create,escrow,direct_vm,direct_bob,direct_charlie):
    eid=create()
    direct_vm.sender=direct_bob
    escrow.reject_escrow(eid)
    direct_vm.sender=direct_charlie
    before=escrow.get_accounting()
    with direct_vm.expect_revert("Insufficient withdrawal credit"):
        escrow.withdraw(1,direct_charlie.as_hex,"account")
    assert escrow.get_accounting()==before


def test_registry_cannot_be_its_own_withdrawal_destination(escrow,direct_vm,module):
    with direct_vm.expect_revert("Cannot withdraw to this registry"):
        escrow.withdraw(1,module.gl.message.contract_address.as_hex,"account")
