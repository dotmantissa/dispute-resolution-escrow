"""Balance-based recipient custody, including value retained without a callback."""
from pathlib import Path
import hashlib
import pytest
from genlayer_escrow.receivers import PAYOUT_INBOX_SOURCE_SHA256

ROOT=Path(__file__).resolve().parents[2]

@pytest.fixture
def inbox(direct_deploy,direct_alice,direct_bob):
    return direct_deploy(str(ROOT/'contracts/payout_inbox.py'),direct_alice.as_hex,direct_bob.as_hex)


def test_published_recipient_source_hash_matches_package():
    assert hashlib.sha256((ROOT/'contracts/payout_inbox.py').read_bytes()).hexdigest()==PAYOUT_INBOX_SOURCE_SHA256


def test_preflight_requires_configured_book_and_positive_integer(inbox,direct_alice,direct_bob):
    assert inbox.can_receive_escrow(direct_bob.as_hex,17)
    assert not inbox.can_receive_escrow(direct_alice.as_hex,17)
    for amount in (0,-1,True):assert not inbox.can_receive_escrow(direct_bob.as_hex,amount)


def test_receive_auth_and_owner_recovery_of_raw_balance(inbox,direct_vm,direct_alice,direct_bob,direct_charlie):
    direct_vm.sender=direct_charlie
    with direct_vm.expect_revert('Only configured'):inbox.receive_escrow()
    direct_vm.sender=direct_bob
    inbox.receive_escrow()
    # Studio may credit native value although the receiving callback was rejected.
    # Recovery must not depend on a callback-managed received counter.
    address=direct_vm._contract_address
    direct_vm.deal(address,71)
    assert inbox.get_config()['native_balance']==71
    direct_vm.sender=direct_charlie
    with direct_vm.expect_revert('Only inbox owner'):inbox.withdraw_to_account(71,direct_charlie.as_hex)
    direct_vm.sender=direct_alice
    for amount in (0,-1,True,72):
        with direct_vm.expect_revert('Amount'):inbox.withdraw_to_account(amount,direct_alice.as_hex)
    inbox.withdraw_to_account(29,direct_alice.as_hex)
    # Direct mode records outbound messages. Real delivery is asserted on Studio.
    assert inbox.get_config()["native_balance"]==71
    # Native transfers are delivered by the host, outside the direct-mode VM.


def test_inbox_serializes_outgoing_native_reservations(inbox,direct_vm,direct_alice,direct_bob):
    address=direct_vm._contract_address
    direct_vm.deal(address,100)
    direct_vm.sender=direct_alice
    inbox.withdraw_to_account(25,direct_bob.as_hex)
    assert inbox.get_config()['withdrawal_pending']
    with direct_vm.expect_revert('Await finalized inbox'):
        inbox.withdraw_to_account(25,direct_bob.as_hex)
    with direct_vm.expect_revert('Only finalized inbox'):
        inbox.acknowledge_withdrawal()
    direct_vm.deal(address,75)
    direct_vm.sender=address
    inbox.acknowledge_withdrawal()
    assert not inbox.get_config()['withdrawal_pending']
    with direct_vm.expect_revert('No pending inbox'):
        inbox.acknowledge_withdrawal()
    direct_vm.sender=direct_alice
    inbox.withdraw_to_account(75,direct_bob.as_hex)
