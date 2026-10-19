"""Isolated real-network failures and IC caller identity, never production fault hooks."""
import hashlib
import os
from pathlib import Path
import subprocess
import tempfile
import time

import pytest
from genlayer_escrow import EscrowClient,ExecutionFailed,RecipientExecutionFailed,transaction_status
from tests.integration.test_studio import Live,ROOT

pytestmark=[pytest.mark.integration,pytest.mark.skipif(not os.environ.get('GENLAYER_PRIVATE_KEY'),reason='Requires Studio signing key')]


def lint_source(source):
    with tempfile.NamedTemporaryFile(suffix='.py') as file:
        file.write(source);file.flush()
        subprocess.run(['genvm-lint','check',file.name],check=True)


def retarget(live,address):
    live.address=address;live.bindings={r:EscrowClient(getattr(live,r),address) for r in live.bindings}
    live.report['contract_address']=address;live.save()


def child_receipts(live,parent,*,success=True):
    deadline=time.monotonic()+600
    while time.monotonic()<deadline:
        ids=live.payer.get_triggered_transaction_ids(transaction_hash=parent)
        if ids:break
        time.sleep(8)
    assert ids,'No emitted child transaction observed'
    receipts=[]
    for child in ids:
        try:receipt=live.bindings['payer'].wait(child,retries=300,interval=8000);assert success,receipt
        except ExecutionFailed as failed:receipt=failed.receipt;assert not success,receipt
        assert transaction_status(receipt)=='FINALIZED'
        receipts.append({'transaction_hash':child,'success':success,'decision':receipt.get('result_name',receipt.get('result')),
                         'value':receipt.get('value'),'recipient':receipt.get('to_address')})
    live.report.setdefault('child_transactions',[]).extend(receipts);live.save();return receipts


def latest_id(live):return live.report['transactions'][-1]['transaction_hash']


def test_majority_rejected_deposit_has_permissionless_owner_recovery():
    live=Live('rejected-consensus-recovery.json')
    source=(ROOT/'contracts/dispute_escrow.py').read_bytes()+b'''
    @gl.public.write.payable
    def reject_funded_consensus(self) -> None:
        # Deliberate isolated fault injection: every real validator must disagree.
        def lead():
            return "deliberately rejected"
        def reject(result: gl.vm.Result) -> bool:
            return False
        gl.vm.run_nondet_unsafe(lead, reject)
'''
    lint_source(source);address=live.deploy(source,[live.payer.local_account.address],key='deploy-rejected-deposit-harness');retarget(live,address)
    before=live.balance(address);assert before==0
    # A majority rejection is intentionally not a VM error. Inspect authoritative result.
    try:live.tx('payer','reject_funded_consensus',value=17,finalized=True,key='funded-rejection')
    except AssertionError:
        entry=next(e for e in live.report['transactions'] if e['operation']=='funded-rejection')
        receipt=live.payer.get_transaction(transaction_hash=entry['transaction_hash'])
        assert transaction_status(receipt)=='FINALIZED' and str(receipt['result'])=='7',receipt
        assert sum(str(v).lower()=='disagree' for v in receipt['consensus_data']['votes'].values())>=3
        entry.update(expected='revert',state='FINALIZED',execution='CONSENSUS_REJECTED');live.save()
    else:raise AssertionError('Fault harness unexpectedly reached agreement')
    assert live.balance(address)==17
    assert live.read('credit_of',[live.payer.local_account.address])==0
    assert live.read('get_accounting')['unreconciled_deposits']==17
    live.tx('outsider','reconcile_deposits',finalized=True,key='reconcile-failed-consensus')
    assert live.read('credit_of',[live.outsider.local_account.address])==0
    assert live.read('credit_of',[live.payer.local_account.address])==17
    live.tx('payer','withdraw',[17,live.payer.local_account.address,'account','recovered'],finalized=True)
    live.finalize_journal();a=live.check_accounting();assert a['accounted_balance']==0
    live.report.update(complete=True,source_sha256=hashlib.sha256(source).hexdigest(),production_source_sha256=live.deployment['source_sha256'],
                       harness='production source plus deliberate all-validator rejection method',final_accounting=a);live.save()


def test_failed_recipient_and_preflight_preserve_recoverable_custody():
    live=Live('recipient-failure-verification.json');payer=live.payer.local_account.address
    address=live.deploy((ROOT/'contracts/dispute_escrow.py').read_bytes(),[payer],key='deploy-recipient-book');retarget(live,address)
    source=(ROOT/'contracts/payout_inbox.py').read_text()
    rejecting=source.replace('        # Custody deliberately relies on the native balance, not a callback counter.',
        '        raise gl.vm.UserError("[EXPECTED] Deliberate receiver failure")').encode()
    declining=source.replace('return _address(sender) == self.escrow_account and type(amount) is int and amount > 0','return False').encode()
    lint_source(rejecting);lint_source(declining)
    rejector=live.deploy(rejecting,[payer,address],key='deploy-rejector');decliner=live.deploy(declining,[payer,address],key='deploy-decliner')
    live.tx('payer','deposit',value=43,key='receiver-deposit',finalized=True)
    before=live.check_accounting()
    live.tx('payer','withdraw',[1,decliner,'contract','declined'],error='has not accepted',finalized=True)
    assert live.check_accounting()==before and live.balance(decliner)==0
    with pytest.raises(ValueError,match='published'):live.bindings['payer'].withdraw(13,rejector,recipient_kind='contract')
    # Deliberately bypass the SDK source guard to exercise a real failed child.
    live.tx('payer','withdraw',[13,rejector,'contract','negative-recipient'],finalized=True)
    parent=latest_id(live)
    with pytest.raises(RecipientExecutionFailed) as failed:
        live.bindings['payer'].wait_withdrawal(parent,recipient=rejector,amount=13,before_balance=0,retries=120,interval=8000)
    live.report['expected_failed_children']=[failed.value.child_receipt['hash']];live.save()
    assert live.balance(rejector)==13
    live.tx('payer','withdraw_to_account',[13,payer],address=rejector,finalized=True)
    live.tx('payer','withdraw',[30,payer,'account','remaining'],finalized=True)
    deadline=time.monotonic()+300
    while live.balance(rejector)!=0 and time.monotonic()<deadline:time.sleep(8)
    assert live.balance(rejector)==0
    live.finalize_journal();a=live.check_accounting();assert a['accounted_balance']==0
    live.report.update(complete=True,rejector=rejector,decliner=decliner,parent_with_failed_child=parent,
        rejecting_source_sha256=hashlib.sha256(rejecting).hexdigest(),declining_source_sha256=hashlib.sha256(declining).hexdigest(),final_accounting=a);live.save()


def test_real_intelligent_contract_payer_identity_and_full_lifecycle():
    live=Live('contract-party-verification.json');payer=live.payer.local_account.address
    actor=live.deploy((ROOT/'tests/integration/contracts/party_account.py').read_bytes(),[payer],key='deploy-party')
    book=live.deploy((ROOT/'contracts/dispute_escrow.py').read_bytes(),[actor],key='deploy-party-book');retarget(live,book)
    live.tx('payer','configure',[book],address=actor,finalized=True)
    # A gift is intentionally allocated to the immutable IC funding owner.
    live.tx('payer','deposit',value=10018,finalized=True,key='party-deposit')
    assert live.read('credit_of',[actor])==10018 and live.read('credit_of',[payer])==0
    doc=live.doc('terms.md');reference=live.run+':ic-party'
    live.tx('outsider','create',[reference,live.payee.local_account.address,doc.url,doc.sha256,10001],address=actor,error='Only party owner')
    live.tx('payer','create',[reference,live.payee.local_account.address,doc.url,doc.sha256,10001],address=actor,finalized=True)
    child_receipts(live,latest_id(live))
    eid=live.bindings['payer'].find_escrow(actor,reference,finalized=True);assert eid
    r=live.read('get_escrow',[eid]);assert r['payer'].lower()==actor.lower()
    live.tx('payer','accept_delivery',[eid],error='Only payer')
    live.deliver(eid);live.tx('payer','accept_delivery',[eid],address=actor,finalized=True);child_receipts(live,latest_id(live))
    assert live.read('get_escrow',[eid])['payee_credit']==10001
    live.tx('payer','withdraw',[17,payer,'party-credit'],address=actor,finalized=True);child_receipts(live,latest_id(live))
    live.tx('payee','withdraw',[10001,live.payee.local_account.address,'account','party-payee-credit'],finalized=True)
    live.finalize_journal();a=live.check_accounting();assert a['accounted_balance']==0
    live.report.update(complete=True,actor_address=actor,escrow_id=eid,final_accounting=a);live.save()
