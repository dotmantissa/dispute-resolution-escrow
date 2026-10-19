from datetime import datetime, timezone
import random

import pytest


def warp(vm, stamp):
    vm.warp(datetime.fromtimestamp(stamp, timezone.utc).isoformat())


def test_creation_commits_terms_and_value(create, escrow, direct_alice, direct_bob, evidence):
    eid = create()
    r = escrow.get_escrow(eid)
    assert r["payer"].lower() == direct_alice.as_hex.lower()
    assert r["payee"].lower() == direct_bob.as_hex.lower()
    assert r["principal"] == 10001 and r["bond_required"] == 1001
    assert r["status"] == "FUNDED" and r["terms"]["sha256"] == evidence["terms.md"]["sha256"]
    assert escrow.find_escrow(direct_alice.as_hex, "order-1") == eid
    assert escrow.find_escrow(direct_alice.as_hex, "missing") == ""
    assert escrow.get_accounting()["locked_principal"] == 10001
    assert escrow.get_accounting()["conserved"]


@pytest.mark.parametrize("principal,rate,expected", [(1,1000,1),(9999,1000,1000),(10000,1000,1000),(10001,1000,1001),(101,10000,101)])
def test_bond_rounds_up(create, escrow, principal, rate, expected):
    eid = create(principal=principal,bond_bps=rate)
    assert escrow.get_escrow(eid)["bond_required"] == expected


@pytest.mark.parametrize("kwargs,error", [
    ({"principal":0},"positive integer"),
    ({"delivery_period":0},"Period"),({"delivery_period":31536001},"Period"),
    ({"review_period":0},"Period"),({"review_period":31536001},"Period"),
    ({"bond_bps":0},"Bond rate"),({"bond_bps":10001},"Bond rate"),
    ({"reference":" bad"},"Reference"),({"reference":"x"*129},"Reference"),
    ({"payee":"0x"+"00"*20},"Zero address"),({"payee":"junk"},"Invalid address"),
])
def test_invalid_creation_is_atomic(create, escrow, direct_vm, kwargs, error):
    before = escrow.get_accounting()
    with direct_vm.expect_revert(error):
        create(**kwargs,prepay=False)
    assert escrow.get_accounting() == before


def test_same_party_and_registry_payee_rejected(create, direct_vm, direct_alice):
    with direct_vm.expect_revert("different external party"):
        create(payee=direct_alice.as_hex,prepay=False)
    address = direct_vm._contract_address
    if isinstance(address, bytes):
        address = "0x" + address.hex()
    else:
        address = address.as_hex
    with direct_vm.expect_revert("different external party"):
        create(payee=address,prepay=False)


def test_reference_replay_prevents_duplicate_funding(create, escrow, direct_vm):
    create(reference="stable")
    before = escrow.get_accounting()
    with direct_vm.expect_revert("Reference already used"):
        create(reference="stable",prepay=False)
    assert escrow.get_accounting() == before


def test_only_payee_can_claim(create, escrow, direct_vm, direct_alice, evidence):
    eid = create()
    d = evidence["delivery-full.md"]
    direct_vm.sender = direct_alice
    with direct_vm.expect_revert("Only payee"):
        escrow.claim_delivery(eid,d["url"],d["sha256"])


def test_delivery_starts_review_and_cannot_be_replaced(delivered, escrow, direct_vm, direct_bob, evidence):
    r = escrow.get_escrow(delivered)
    assert r["status"] == "DELIVERED" and r["review_deadline"] == r["created_at"] + 600
    direct_vm.sender = direct_bob
    d = evidence["delivery-half.md"]
    with direct_vm.expect_revert("FUNDED"):
        escrow.claim_delivery(delivered,d["url"],d["sha256"])


def test_payer_acceptance_credits_payee_exactly(delivered, escrow, direct_vm, direct_alice, direct_bob):
    direct_vm.sender = direct_alice
    escrow.accept_delivery(delivered)
    assert escrow.credit_of(direct_bob.as_hex) == 10001
    assert escrow.credit_of(direct_alice.as_hex) == 0
    assert escrow.get_escrow(delivered)["status"] == "SETTLED"
    a = escrow.get_accounting()
    assert a["locked_principal"] == 0 and a["withdrawal_credits"] == 10001 and a["conserved"]
    with direct_vm.expect_revert("DELIVERED"):
        escrow.accept_delivery(delivered)


def test_only_payer_accepts(delivered, escrow, direct_vm, direct_bob):
    direct_vm.sender = direct_bob
    with direct_vm.expect_revert("Only payer"):
        escrow.accept_delivery(delivered)


def test_timeout_and_delivery_have_nonoverlapping_boundaries(create, escrow, direct_vm, direct_bob, direct_charlie, evidence):
    eid = create()
    direct_vm.sender = direct_bob
    escrow.accept_engagement(eid)
    r = escrow.get_escrow(eid)
    warp(direct_vm,r["delivery_deadline"]-1)
    direct_vm.sender = direct_charlie
    with direct_vm.expect_revert("still open"):
        escrow.refund_undelivered(eid)
    warp(direct_vm,r["delivery_deadline"])
    direct_vm.sender = direct_bob
    d = evidence["delivery-full.md"]
    with direct_vm.expect_revert("deadline reached"):
        escrow.claim_delivery(eid,d["url"],d["sha256"])
    direct_vm.sender = direct_charlie
    escrow.refund_undelivered(eid)
    assert escrow.get_escrow(eid)["status"] == "REFUNDED"
    assert escrow.get_accounting()["conserved"]


def test_dispute_and_release_have_nonoverlapping_boundaries(delivered, escrow, direct_vm, direct_alice, direct_charlie, evidence):
    r = escrow.get_escrow(delivered)
    warp(direct_vm,r["review_deadline"]-1)
    with direct_vm.expect_revert("still open"):
        escrow.release_expired(delivered)
    warp(direct_vm,r["review_deadline"])
    direct_vm.sender = direct_alice
    direct_vm.value = r["bond_required"]
    d = evidence["dispute-good-faith.md"]
    with direct_vm.expect_revert("window closed"):
        escrow.dispute(delivered,d["url"],d["sha256"],direct_vm.value)
    direct_vm.value = 0
    direct_vm.sender = direct_charlie
    escrow.release_expired(delivered)
    assert escrow.get_escrow(delivered)["payee_credit"] == 10001


@pytest.mark.parametrize("delta",[-1,1,-1001])
def test_dispute_requires_exact_bond(delivered, escrow, direct_vm, direct_alice, evidence, delta):
    direct_vm.sender = direct_alice
    r = escrow.get_escrow(delivered)
    direct_vm.value = r["bond_required"] + delta
    d = evidence["dispute-half.md"]
    before = escrow.get_accounting()
    with direct_vm.expect_revert("exact dispute bond"):
        escrow.dispute(delivered,d["url"],d["sha256"],direct_vm.value)
    assert escrow.get_accounting() == before
    assert escrow.get_escrow(delivered)["status"] == "DELIVERED"


def test_dispute_locks_bond_and_blocks_release(disputed, escrow, direct_vm, direct_charlie):
    r = escrow.get_escrow(disputed)
    assert r["bond_paid"] == 1001 and r["status"] == "DISPUTED"
    warp(direct_vm,r["review_deadline"]+100000)
    direct_vm.sender = direct_charlie
    for fn in (escrow.release_expired,escrow.refund_undelivered,escrow.reject_escrow,escrow.accept_delivery):
        with direct_vm.expect_revert():
            fn(disputed)
    a = escrow.get_accounting()
    assert a["locked_bonds"] == 1001 and a["total_deposited"] == 11002 and a["conserved"]


def test_payee_can_reject_before_delivery(create, escrow, direct_vm, direct_bob, direct_alice):
    eid = create()
    with direct_vm.expect_revert("Only payee"):
        escrow.reject_escrow(eid)
    direct_vm.sender = direct_bob
    escrow.reject_escrow(eid)
    assert escrow.credit_of(direct_alice.as_hex) == 10001


@pytest.mark.parametrize("share",[0,1,3333,5000,9999,10000])
def test_bilateral_split_conserves_all_wei_and_refunds_bond(disputed, escrow, direct_vm, direct_alice, direct_bob, share):
    direct_vm.sender = direct_alice
    escrow.offer_settlement(disputed,share)
    assert escrow.get_escrow(disputed)["status"] == "DISPUTED"
    direct_vm.sender = direct_bob
    escrow.offer_settlement(disputed,share)
    r = escrow.get_escrow(disputed)
    assert r["payee_credit"] == 10001*share//10000
    assert r["payer_credit"] == 11002-r["payee_credit"]
    assert not r["payer_bad_faith"]
    assert escrow.get_accounting()["conserved"]
    assert escrow.get_accounting()["locked_bonds"] == 0


def test_offers_must_match_and_can_be_cancelled(disputed, escrow, direct_vm, direct_alice, direct_bob, direct_charlie):
    direct_vm.sender = direct_alice
    escrow.offer_settlement(disputed,4000)
    escrow.cancel_offer(disputed)
    direct_vm.sender = direct_bob
    escrow.offer_settlement(disputed,4000)
    assert escrow.get_escrow(disputed)["status"] == "DISPUTED"
    direct_vm.sender = direct_alice
    escrow.offer_settlement(disputed,5000)
    direct_vm.sender = direct_charlie
    with direct_vm.expect_revert("Only escrow parties"):
        escrow.offer_settlement(disputed,4000)
    with direct_vm.expect_revert("Only escrow parties"):
        escrow.cancel_offer(disputed)
    direct_vm.sender = direct_bob
    escrow.offer_settlement(disputed,5000)
    with direct_vm.expect_revert("already settled"):
        escrow.cancel_offer(disputed)


def test_phase_transition_invalidates_old_offers(create, escrow, direct_vm, direct_alice, direct_bob, evidence, fund):
    eid = create()
    escrow.offer_settlement(eid,5000)
    direct_vm.sender = direct_bob
    d = evidence["delivery-full.md"]
    escrow.accept_engagement(eid)
    escrow.claim_delivery(eid,d["url"],d["sha256"])
    assert escrow.get_escrow(eid)["payer_offer"] == -1
    escrow.offer_settlement(eid,5000)
    direct_vm.sender = direct_alice
    bond = escrow.get_escrow(eid)["bond_required"]
    fund(bond)
    d = evidence["dispute-half.md"]
    escrow.dispute(eid,d["url"],d["sha256"],bond)
    assert escrow.get_escrow(eid)["payee_offer"] == -1


def test_many_escrows_are_isolated_with_exact_conservation(create, escrow, direct_vm, direct_alice, direct_bob):
    rng = random.Random(260019)
    total = 0
    for i in range(50):
        principal = rng.randrange(1,10**30)
        share = rng.randrange(10001)
        eid = create(principal=principal)
        escrow.offer_settlement(eid,share)
        direct_vm.sender = direct_bob
        escrow.offer_settlement(eid,share)
        total += principal
        a = escrow.get_accounting()
        assert a["conserved"] and a["withdrawal_credits"] == total
    assert escrow.credit_of(direct_alice.as_hex)+escrow.credit_of(direct_bob.as_hex) == total
    assert escrow.get_accounting()["escrow_count"] == 50


@pytest.mark.parametrize("amount,recipient,kind,error",[
    (0,"valid","account","positive"),(-1,"valid","account","positive"),
    (1,"valid","account","Insufficient"),(1,"valid","wrong","Recipient kind"),
    (1,"0x"+"00"*20,"account","Zero address"),
])
def test_invalid_withdrawals_preserve_accounting(escrow,direct_vm,direct_bob,amount,recipient,kind,error):
    before=escrow.get_accounting()
    with direct_vm.expect_revert(error):
        escrow.withdraw(amount,direct_bob.as_hex if recipient=="valid" else recipient,kind,"invalid")
    assert escrow.get_accounting()==before


def test_unknown_escrow_and_non_disputed_adjudication(create,escrow,direct_vm):
    with direct_vm.expect_revert("Unknown escrow"):
        escrow.get_escrow("missing")
    eid=create()
    with direct_vm.expect_revert("DISPUTED"):
        escrow.adjudicate(eid)
