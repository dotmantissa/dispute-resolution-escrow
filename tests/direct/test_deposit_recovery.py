"""Native value is attributed by immutable ownership and actual balance."""
import pytest


def test_reconcile_retained_native_value_after_missing_state(escrow,direct_vm,direct_alice,direct_charlie,module):
    # Reproduce the post-state of Studio's independently verified rejected payable call.
    # The integration suite separately creates this condition on actual validators.
    address=module.gl.message.contract_address
    direct_vm.deal(address,17)
    assert escrow.get_accounting()['unreconciled_deposits']==17
    direct_vm.sender=direct_charlie
    assert escrow.reconcile_deposits()==17
    assert escrow.credit_of(direct_alice.as_hex)==17
    assert escrow.credit_of(direct_charlie.as_hex)==0
    assert escrow.reconcile_deposits()==0
    assert escrow.get_accounting()['conserved'] and escrow.get_accounting()['solvent']


def test_reconciliation_cannot_spend_or_reassign_other_parties_credits(delivered,escrow,direct_vm,direct_alice,direct_bob,direct_charlie,module):
    direct_vm.sender=direct_alice
    escrow.accept_delivery(delivered)
    direct_vm.deal(module.gl.message.contract_address,int(escrow.balance)+29)
    direct_vm.sender=direct_charlie
    assert escrow.reconcile_deposits()==29
    assert escrow.credit_of(direct_bob.as_hex)==10001
    assert escrow.credit_of(direct_alice.as_hex)==29
    assert escrow.credit_of(direct_charlie.as_hex)==0


def test_native_gifts_have_the_same_fixed_beneficiary(escrow,direct_vm,direct_alice,direct_charlie,module):
    direct_vm.sender=direct_charlie
    direct_vm.value=31
    direct_vm.deal(module.gl.message.contract_address,31)
    assert escrow.deposit()==31
    assert escrow.credit_of(direct_alice.as_hex)==31
    assert escrow.credit_of(direct_charlie.as_hex)==0


def test_failed_evidence_leaves_prepaid_money_recoverable(escrow,direct_vm,direct_alice,direct_bob,evidence,fund):
    fund(10001)
    before=escrow.get_accounting()
    with direct_vm.expect_revert('mismatch'):
        escrow.create_escrow('bad-hash',direct_bob.as_hex,evidence['terms.md']['url'],'0'*64,
                             10001,100,100,1000,60,600,5000)
    assert escrow.get_accounting()==before
    assert escrow.credit_of(direct_alice.as_hex)==10001
    assert escrow.find_escrow(direct_alice.as_hex,'bad-hash')==''


def test_wrong_bond_does_not_lock_or_spend_credit(delivered,escrow,direct_vm,direct_alice,evidence,fund):
    fund(1001)
    before=escrow.get_accounting()
    d=evidence['dispute-half.md']
    for amount in (0,1000,1002,True):
        with direct_vm.expect_revert('exact dispute bond'):
            escrow.dispute(delivered,d['url'],d['sha256'],amount)
        assert escrow.get_accounting()==before


def test_lifetime_audit_counters_can_exceed_uint256(escrow,fund):
    ceiling=(1<<256)-1
    escrow.total_deposited=str(ceiling)
    escrow.total_withdrawn=str(ceiling)
    fund(10)
    assert escrow.get_accounting()['total_deposited']==ceiling+10
    assert escrow.get_accounting()['conserved']


def test_pending_emission_cannot_be_recredited_before_authenticated_ack(escrow,direct_vm,direct_alice,direct_bob,direct_charlie,module,fund):
    fund(100)
    escrow.withdraw(25,direct_bob.as_hex,'account','pending-native')
    assert escrow.credit_of(direct_alice.as_hex)==75
    assert escrow.get_accounting()['pending_withdrawals']==1
    direct_vm.sender=direct_charlie
    with direct_vm.expect_revert('Await finalized withdrawal'):escrow.reconcile_deposits()
    with direct_vm.expect_revert('Only finalized self-message'):
        escrow.acknowledge_withdrawal(direct_alice.as_hex,'pending-native')
    # The host debits outgoing value at parent finality before dispatching its ack.
    address=module.gl.message.contract_address
    direct_vm.deal(address,75)
    direct_vm.sender=address
    escrow.acknowledge_withdrawal(direct_alice.as_hex,'pending-native')
    assert escrow.get_withdrawal(direct_alice.as_hex,'pending-native')['state']=='EMISSION_FINALIZED'
    assert escrow.get_accounting()['pending_withdrawals']==0
    with direct_vm.expect_revert('already acknowledged'):
        escrow.acknowledge_withdrawal(direct_alice.as_hex,'pending-native')
    direct_vm.sender=direct_charlie
    assert escrow.reconcile_deposits()==0
    assert escrow.credit_of(direct_alice.as_hex)==75
    fund(17)
    assert escrow.credit_of(direct_alice.as_hex)==92
