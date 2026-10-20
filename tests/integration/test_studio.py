"""Real Studio custody and independent consensus. No manufactured model results.

Set GENLAYER_PRIVATE_KEY and GENLAYER_TEST_KEYS_FILE. A durable operation journal
allows the same transaction IDs and case references to resume after interruption.
Use GENLAYER_RESUME_RUN=1 only with the same deployment and actor key file.
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
from genlayer_py import create_account,create_client
from genlayer_py.chains import studionet
from genlayer_escrow import (Document,EscrowClient,ExecutionFailed,PollingTimeout,
    AppealTicket,execution_succeeded,transaction_status)
from tests.integration.transport import attach_transport

ROOT=Path(__file__).resolve().parents[2]
PRINCIPAL=10001
pytestmark=[pytest.mark.integration,pytest.mark.skipif(not os.environ.get('GENLAYER_PRIVATE_KEY'),
    reason='Set GENLAYER_PRIVATE_KEY for real Studio consensus')]


def failure_text(receipt):
    rows=(receipt.get('consensus_data') or {}).get('leader_receipt') or []
    leader=rows[0] if isinstance(rows,list) and rows else rows if isinstance(rows,dict) else {}
    result=leader.get('result',{})
    payload=result.get('payload',{}) if isinstance(result,dict) else {}
    raw=payload.get('raw') if isinstance(payload,dict) else None
    raw=raw or result.get('raw') if isinstance(result,dict) else raw
    if isinstance(raw,str):
        try:return base64.b64decode(raw)[1:].decode(errors='replace')
        except ValueError:pass
    if isinstance(raw,list):return bytes(raw[1:]).decode(errors='replace')
    return json.dumps(result,default=str)


class Live:
    def __init__(self,report_name='studio-verification.json'):
        deployment_path=Path(os.environ.get('GENLAYER_TEST_DEPLOYMENT_FILE',ROOT/'artifacts/deployment.json'))
        self.deployment=json.loads(deployment_path.read_text())
        assert self.deployment['version']=='2.0.0'
        self.address=self.deployment['contract_address']
        self.payer=attach_transport(create_client(chain=studionet,account=create_account(os.environ['GENLAYER_PRIVATE_KEY'])))
        secret_path=os.environ.get('GENLAYER_TEST_KEYS_FILE')
        if not secret_path:
            fd,secret_path=tempfile.mkstemp(prefix='escrow-actors-',suffix='.json');os.close(fd)
        self.secret_path=Path(secret_path)
        self.secret_path.touch(mode=0o600,exist_ok=True);self.secret_path.chmod(0o600)
        if self.secret_path.stat().st_size:keys=json.loads(self.secret_path.read_text())
        else:
            keys={name:'0x'+secrets.token_hex(32) for name in ('payee','outsider')}
            self.secret_path.write_text(json.dumps(keys))
        for role in ('payee','outsider'):
            setattr(self,role,attach_transport(create_client(chain=studionet,account=create_account(keys[role]))))
        self.bindings={r:EscrowClient(getattr(self,r),self.address) for r in ('payer','payee','outsider')}
        self.manifest=json.loads((ROOT/'tests/evidence/manifest.json').read_text())['documents']
        self.path=ROOT/'artifacts'/report_name
        self.report={'version':'2.0.0','run_id':secrets.token_hex(6),'contract_address':self.address,
            'source_sha256':self.deployment['source_sha256'],'network':'studionet','started_at':int(time.time()),
            'actors':{r:getattr(self,r).local_account.address for r in self.bindings},'transactions':[], 'scenarios':[]}
        if self.path.exists():
            if not os.environ.get('GENLAYER_RESUME_RUN'):raise RuntimeError('Existing journal: inspect it and set GENLAYER_RESUME_RUN=1 to resume')
            self.report=json.loads(self.path.read_text());assert self.report['contract_address']==self.address
        self.run=self.report['run_id'];self.save()
        print('Actor recovery file:',self.secret_path,flush=True)
        for role in self.bindings:
            client=getattr(self,role)
            if client.get_balance(client.local_account.address)<10**12:
                self.payer.provider.make_request('sim_fundAccount',[client.local_account.address,10**18])

    def save(self):
        temp=self.path.with_suffix('.tmp');temp.write_text(json.dumps(self.report,indent=2,default=str)+'\n');temp.replace(self.path)

    def doc(self,name):return Document(**self.manifest[name])
    def read(self,method,args=None,address=None,*,finalized=False):
        return EscrowClient(self.payer,address or self.address)._read(method,args,finalized=finalized)
    def balance(self,address):return self.payer.get_balance(address)

    def submit(self,client,destination,method,args,value,error):
        """Positive main-book flows exercise the published builder binding itself."""
        if destination.lower()==self.deployment['contract_address'].lower() and not error:
            api=EscrowClient(client,destination)
            values=args or []
            if method=='deposit':return api.deposit(value),'EscrowClient'
            if value==0:
                if method=='create_escrow':
                    return api.create(values[0],values[1],Document(values[2],values[3]),*values[4:8],
                        response_period=values[8],adjudication_period=values[9],fallback_payee_bps=values[10]),'EscrowClient'
                if method in ('claim_delivery','submit_evidence'):
                    return getattr(api,method)(values[0],Document(values[1],values[2])),'EscrowClient'
                if method=='dispute':
                    return api.dispute(values[0],Document(values[1],values[2]),bond=values[3]),'EscrowClient'
                if method=='withdraw':
                    return api.withdraw(values[0],values[1],recipient_kind=values[2],reference=values[3]),'EscrowClient'
                if method in ('reconcile_deposits','accept_engagement','accept_delivery','finish_evidence',
                    'adjudicate','resolve_expired_dispute','release_expired','refund_undelivered',
                    'reject_escrow','offer_settlement','cancel_offer'):
                    return getattr(api,method)(*values),'EscrowClient'
        return client.write_contract(address=destination,function_name=method,args=args or [],value=value,leader_only=False),'raw SDK'

    def tx(self,role,method,args=None,value=0,*,error=None,address=None,key=None,finalized=False):
        client=getattr(self,role);destination=address or self.address
        operation=key or hashlib.sha256(json.dumps([role,destination,method,args,value,bool(error)],sort_keys=True).encode()).hexdigest()
        entry=next((e for e in self.report['transactions'] if e['operation']==operation),None)
        if entry is None:
            time.sleep(1)
            txid,submitted_via=self.submit(client,destination,method,args,value,error)
            entry={'operation':operation,'method':method,'caller':client.local_account.address,'address':destination,
                'transaction_hash':txid,'value':value,'expected':'revert' if error else 'success','state':'SUBMITTED','submitted_via':submitted_via}
            self.report['transactions'].append(entry);self.save();print(method,txid,flush=True)
        txid=entry['transaction_hash']
        try:
            receipt=EscrowClient(client,destination).wait(txid,finalized=finalized,retries=600,interval=8000)
        except ExecutionFailed as failed:receipt=failed.receipt
        success=execution_succeeded(receipt)
        entry.update(state=transaction_status(receipt),execution='SUCCESS' if success else 'ERROR',
                     decision=receipt.get('result_name',receipt.get('result')),votes=(receipt.get('consensus_data') or {}).get('votes',{}))
        if error:
            assert not success,receipt
            entry['error']=failure_text(receipt)
            if isinstance(error,str):assert error in entry['error'],entry
        else:assert success,receipt
        self.save();return receipt

    def deploy(self,source,args,*,key):
        entry=next((e for e in self.report['transactions'] if e['operation']==key),None)
        if entry is None:
            txid=self.payer.deploy_contract(code=source,args=args,leader_only=False)
            entry={'operation':key,'method':'deploy','transaction_hash':txid,'source_sha256':hashlib.sha256(source).hexdigest(),
                   'state':'SUBMITTED','expected':'success'}
            self.report['transactions'].append(entry);self.save();print('deploy',txid,flush=True)
        receipt=self.bindings['payer'].wait(entry['transaction_hash'],retries=600,interval=8000)
        address=receipt.get('contract_address') or receipt.get('to_address')
        assert address;entry.update(state='FINALIZED',execution='SUCCESS',contract_address=address);self.save();return address

    def create(self,label,*,terms='terms.md',delivery_period=86400,review_period=86400,response_period=3600,
               adjudication_period=86400,fallback_payee_bps=5000):
        reference=self.run+':'+label
        eid=self.bindings['payer'].find_escrow(self.payer.local_account.address,reference,finalized=False)
        if eid:return eid
        d=self.doc(terms)
        self.tx('payer','create_escrow',[reference,self.payee.local_account.address,d.url,d.sha256,PRINCIPAL,
            delivery_period,review_period,1000,response_period,adjudication_period,fallback_payee_bps],key='create:'+label)
        eid=self.bindings['payer'].find_escrow(self.payer.local_account.address,reference,finalized=False);assert eid;return eid

    def deliver(self,eid,name='delivery-full.md'):
        r=self.read('get_escrow',[eid])
        if r['delivery'] is not None:return
        if not r['engagement_accepted']:self.tx('payee','accept_engagement',[eid])
        d=self.doc(name);self.tx('payee','claim_delivery',[eid,d.url,d.sha256])

    def dispute(self,eid,name='dispute-good-faith.md',*,close=True):
        r=self.read('get_escrow',[eid]);d=self.doc(name)
        if r['dispute'] is None:self.tx('payer','dispute',[eid,d.url,d.sha256,r['bond_required']])
        if close:
            r=self.read('get_escrow',[eid])
            if not r['evidence_closed']:
                for role in ('payer','payee'):
                    if not r[role+'_ready']:self.tx(role,'finish_evidence',[eid])
        return r['bond_required']

    def scenario(self,name,**data):
        self.report['scenarios']=[s for s in self.report['scenarios'] if s['case']!=name]
        self.report['scenarios'].append({'case':name,'verified':True,**data});self.save()

    def check_accounting(self):
        a=self.read('get_accounting');assert a['conserved'] and a['solvent'],a
        assert self.balance(self.address)==a['native_balance']==a['accounted_balance'],a
        return a

    def finalize_journal(self):
        for entry in self.report['transactions']:
            receipt=self.payer.get_transaction(transaction_hash=entry['transaction_hash'])
            if transaction_status(receipt)!='FINALIZED':
                try:receipt=self.bindings['payer'].wait(entry['transaction_hash'],retries=600,interval=12000)
                except ExecutionFailed as failed:receipt=failed.receipt
            assert transaction_status(receipt)=='FINALIZED',receipt
            assert execution_succeeded(receipt)==(entry['expected']=='success'),receipt
            entry['state']='FINALIZED';self.save()
        discovered=[]
        queue=[e['transaction_hash'] for e in self.report['transactions']]
        seen=set(queue)
        while queue:
            parent=queue.pop(0)
            for child in self.payer.get_triggered_transaction_ids(transaction_hash=parent):
                if child in seen:continue
                seen.add(child);queue.append(child)
                receipt=self.payer.get_transaction(transaction_hash=child)
                expected_failure=child in self.report.get('expected_failed_children',[])
                if str(receipt.get('type'))=='0':
                    source=receipt['from_address']
                    receipt=EscrowClient(self.payer,source)._wait_native_transfer(child,receipt['to_address'],int(receipt['value']),retries=300,interval=8000)
                    assert not expected_failure
                else:
                    try:
                        receipt=self.bindings['payer'].wait(child,retries=300,interval=8000)
                        assert not expected_failure,receipt
                    except ExecutionFailed as failed:
                        receipt=failed.receipt;assert expected_failure,receipt
                discovered.append({'transaction_hash':child,'triggered_by':parent,'state':transaction_status(receipt),
                    'type':receipt.get('type'),'recipient':receipt.get('to_address'),'value':receipt.get('value'),
                    'expected':'failure' if expected_failure else 'success'})
        self.report['emitted_transactions']=discovered
        self.report['all_transactions_finalized']=True;self.save()


@pytest.fixture(scope='module')
def live():return Live()


def test_01_deployed_source_schema_and_deposit(live):
    assert base64.b64decode(live.payer.provider.make_request('gen_getContractCode',[live.address])['result'])==(ROOT/'contracts/dispute_escrow.py').read_bytes()
    assert live.read('get_config')['funding_owner'].lower()==live.payer.local_account.address.lower()
    live.tx('payer','deposit',value=300000,key='initial-deposit',finalized=True)
    payer=live.payer.local_account.address
    payer_before=live.balance(payer)
    pending=live.tx('payer','withdraw',[1,payer,'account','finality-guard-probe'])
    live.report['provisional_withdrawal_accounting']=live.read('get_accounting');live.save()
    live.tx('outsider','reconcile_deposits',error='Await finalized withdrawal',key='reconcile-while-provisional')
    live.bindings['payer'].wait_withdrawal(pending['hash'],recipient=payer,amount=1,before_balance=payer_before,retries=600,interval=8000)
    live.tx('outsider','reconcile_deposits',key='reconcile-after-finality',finalized=True)
    live.tx('payer','deposit',value=17,key='deposit-after-withdrawal-finality',finalized=True)
    live.check_accounting();live.scenario('source_schema_deposit_and_finality_guard')


def test_02_prepaid_failure_auth_and_acceptance(live):
    eid=live.create('accept');d=live.doc('delivery-full.md')
    live.tx('outsider','claim_delivery',[eid,d.url,d.sha256],error='Only payee')
    live.tx('payee','claim_delivery',[eid,d.url,d.sha256],error='accept engagement')
    live.tx('payee','accept_engagement',[eid])
    before=live.check_accounting()
    live.tx('payee','claim_delivery',[eid,d.url,'0'*64],error='SHA-256 mismatch')
    assert live.check_accounting()==before
    live.deliver(eid);live.tx('outsider','accept_delivery',[eid],error='Only payer')
    live.tx('payer','accept_delivery',[eid]);r=live.read('get_escrow',[eid]);assert r['payee_credit']==PRINCIPAL
    live.tx('payer','accept_delivery',[eid],error='DELIVERED')
    live.scenario('prepaid_failure_auth_acceptance',escrow_id=eid)


@pytest.mark.parametrize('label,delivery,dispute,share,bad',[
    ('partial','delivery-half.md','dispute-half.md',5000,False),
    ('no-delivery','delivery-none.md','dispute-none.md',0,False),
    ('bad-faith','delivery-full.md','dispute-bad-faith.md',10000,True),
    ('honest-dispute','delivery-full.md','dispute-good-faith.md',10000,False),
    ('prompt-injection','delivery-injection.md','dispute-none.md',0,False),
])
def test_03_real_validator_adjudication(live,label,delivery,dispute,share,bad):
    eid=live.create(label);live.deliver(eid,delivery);bond=live.dispute(eid,dispute)
    receipt=live.tx('outsider','adjudicate',[eid])
    votes=receipt.get('consensus_data',{}).get('votes',{})
    assert sum(str(v).lower()=='agree' for v in votes.values())>=3,votes
    r=live.read('get_escrow',[eid]);assert r['last_assessment']['conclusive'],r
    assert r['payee_bps']==share and r['payer_bad_faith'] is bad,r
    earned=PRINCIPAL*share//10000+(bond if bad else 0)
    assert r['payee_credit']==earned and r['payer_credit']==PRINCIPAL+bond-earned
    live.check_accounting();live.scenario(label,escrow_id=eid,assessment=r['last_assessment'],payee_credit=earned,payer_credit=r['payer_credit'])


def test_04_inconclusive_bilateral_and_deadline_fallback(live):
    eid=live.create('inconclusive',terms='terms-inconclusive.md');live.deliver(eid,'delivery-inconclusive.md');bond=live.dispute(eid,'dispute-inconclusive.md')
    before=live.check_accounting();live.tx('outsider','adjudicate',[eid]);r=live.read('get_escrow',[eid])
    assert r['status']=='DISPUTED' and not r['last_assessment']['conclusive'];assert live.check_accounting()==before
    live.tx('payer','offer_settlement',[eid,3000]);live.tx('payer','cancel_offer',[eid])
    live.tx('payee','offer_settlement',[eid,3000])
    live.tx('payer','offer_settlement',[eid,3000],key='renew-offer-after-cancellation:'+eid)
    assert live.read('get_escrow',[eid])['payer_credit']==PRINCIPAL+bond-3000
    eid2=live.create('fallback',response_period=1,adjudication_period=1,fallback_payee_bps=3333)
    live.deliver(eid2);live.dispute(eid2,close=False);live.tx('outsider','resolve_expired_dispute',[eid2])
    r=live.read('get_escrow',[eid2]);assert r['payee_credit']==PRINCIPAL*3333//10000 and not r['payer_bad_faith']
    live.scenario('inconclusive_bilateral_deadline_fallback',escrow_ids=[eid,eid2]);live.check_accounting()


def test_05_timeouts_and_rejection(live):
    eid=live.create('undelivered',delivery_period=1);live.tx('outsider','refund_undelivered',[eid])
    assert live.read('get_escrow',[eid])['payer_credit']==PRINCIPAL
    eid2=live.create('unreviewed',review_period=1);live.deliver(eid2);live.tx('outsider','release_expired',[eid2])
    assert live.read('get_escrow',[eid2])['payee_credit']==PRINCIPAL
    eid3=live.create('rejected');live.tx('payee','reject_escrow',[eid3]);assert live.read('get_escrow',[eid3])['status']=='REFUNDED'
    live.scenario('timeouts_rejection',escrow_ids=[eid,eid2,eid3])


def verify_retained_value_recovery(live,eid):
    # Unknown-method failures can have only a generic VM exit code. Bind failed
    # execution and actual custody rather than depending on diagnostic wording.
    live.tx('outsider','not_a_method',[],value=17,error=True,key='retained-value',finalized=True)
    if not any(e['operation']=='recover-retained-value' for e in live.report['transactions']):
        assert live.read('get_accounting')['unreconciled_deposits']==17
    live.tx('outsider','reconcile_deposits',key='recover-retained-value',finalized=True)
    live.check_accounting();live.scenario('rebuttal_prepaid_replay_retained_value_recovery',escrow_id=eid,recovered=17)


def test_06_rebuttal_wrong_bond_replay_and_recovery(live):
    eid=live.create('rebuttal')
    if any(e['operation']=='retained-value' for e in live.report['transactions']):
        # This operation is journaled only after all rebuttal, bond and replay
        # assertions below passed. Resume its original funded ID after a stop.
        r=live.read('get_escrow',[eid],finalized=True)
        assert r['payee_bps']==5000 and not r['payer_bad_faith'] and r['payee_credit']==5000,r
        assert r['supplements'][0]['submitted_by'].lower()==live.payee.local_account.address.lower()
        verify_retained_value_recovery(live,eid);return
    live.deliver(eid,'delivery-half.md');d=live.doc('dispute-none.md');r=live.read('get_escrow',[eid])
    before=live.check_accounting();live.tx('payer','dispute',[eid,d.url,d.sha256,r['bond_required']-1],error='exact dispute bond')
    assert live.check_accounting()==before
    live.dispute(eid,'dispute-none.md',close=False)
    live.tx('outsider','adjudicate',[eid],error='Response window still open')
    rebuttal=live.doc('payee-rebuttal.md');live.tx('payee','submit_evidence',[eid,rebuttal.url,rebuttal.sha256])
    for role in ('payer','payee'):live.tx(role,'finish_evidence',[eid])
    live.tx('outsider','adjudicate',[eid]);r=live.read('get_escrow',[eid]);assert r['payee_bps']==5000 and not r['payer_bad_faith'],r
    assert r['supplements'][0]['submitted_by'].lower()==live.payee.local_account.address.lower()
    # Failed nonpayable evidence calls never introduce additional value.
    terms=live.doc('terms.md');before=live.check_accounting()
    live.tx('payer','create_escrow',[r['reference'],r['payee'],terms.url,terms.sha256,PRINCIPAL,100,100,1000,100,100,5000],error='Reference already used')
    assert live.check_accounting()==before
    # Genuine retained-value failure on this deployment, recovered into its fixed owner.
    verify_retained_value_recovery(live,eid)


def test_07_real_protocol_appeal(live):
    if 'appeal_ticket' not in live.report:
        expired=live.report.setdefault('expired_appeal_opportunities',[])
        for attempt in range(3):
            label='appeal' if attempt==0 else 'appeal-retry-'+str(attempt)
            if any(e['label']==label for e in expired):continue
            eid=live.create(label);live.deliver(eid,'delivery-half.md');live.dispute(eid,'dispute-half.md')
            receipt=live.tx('outsider','adjudicate',[eid]);txid=receipt['hash']
            if transaction_status(receipt)!='FINALIZED':
                try:ticket=live.bindings['payer'].appeal(eid,txid)
                except ValueError:
                    receipt=live.payer.get_transaction(transaction_hash=txid)
                    if transaction_status(receipt)!='FINALIZED':raise
                else:
                    live.report['appeal_ticket']=ticket.__dict__;live.save()
                    print('appeal submitted',ticket.transaction_id,flush=True);break
            # Gateway downtime can hide the entire provisional appeal window.
            # Preserve its original result; never pretend a late appeal succeeded.
            expired.append({'label':label,'escrow_id':eid,'transaction_hash':txid,'observed_state':'FINALIZED'})
            live.save();print('Appeal opportunity expired before submission:',txid,flush=True)
            if live.read('get_escrow',[eid])['status']=='DISPUTED':
                live.tx('payer','offer_settlement',[eid,5000]);live.tx('payee','offer_settlement',[eid,5000])
        assert 'appeal_ticket' in live.report,'RPC prevented timely appeal submission in three distinct cases'
    ticket=AppealTicket(**live.report['appeal_ticket'])
    eid=ticket.escrow_id;txid=ticket.transaction_id
    outcome=live.bindings['payer'].wait_appeal(ticket,retries=600,interval=8000)
    assert outcome['appeal_observed'] and outcome['state'] in ('SETTLED','REFUNDED','DISPUTED'),outcome
    assert outcome['escrow']==live.bindings['payer'].get_escrow(eid,finalized=True)
    live.report['appeal_outcome']={k:v for k,v in outcome.items() if k!='receipt'}
    entry=next(e for e in live.report['transactions'] if e['transaction_hash']==txid)
    entry['expected']='success' if outcome['transaction_succeeded'] else 'revert'
    entry['appeal_final_state']=outcome['state'];live.save()
    if outcome['state']=='DISPUTED':
        live.tx('payer','offer_settlement',[eid,5000]);live.tx('payee','offer_settlement',[eid,5000])
    live.scenario('stored_protocol_appeal_refresh',escrow_id=eid,transaction_hash=txid,final_state=outcome['state'])


def test_08_partial_account_and_safe_contract_withdrawals(live):
    payer=live.payer.local_account.address;payee=live.payee.local_account.address
    inbox=live.deploy((ROOT/'contracts/payout_inbox.py').read_bytes(),[payer,live.address],key='deploy-payout-inbox')
    assert live.bindings['payer'].qualify_inbox(inbox)['owner'].lower()==payer.lower()
    if 'inbox_before' not in live.report:
        live.report['inbox_before']=live.balance(inbox);live.save()
    before=live.report['inbox_before']
    live.tx('payer','withdraw',[29,inbox,'contract','partial-inbox'],finalized=True)
    parent=live.report['transactions'][-1]['transaction_hash']
    transfer=live.bindings['payer'].wait_withdrawal(parent,recipient=inbox,amount=29,before_balance=before,retries=120,interval=8000)
    assert transfer['children'] and live.balance(inbox)==before+29
    if 'inbox_recovery_before' not in live.report:
        live.report['inbox_recovery_before']=live.balance(payer);live.save()
    account_before=live.report['inbox_recovery_before']
    live.tx('payer','withdraw_to_account',[29,payer],address=inbox,finalized=True)
    deadline=time.monotonic()+240
    while live.balance(payer)<account_before+29 and time.monotonic()<deadline:time.sleep(8)
    assert live.balance(payer)>=account_before+29
    live.tx('payer','withdraw',[1,payer,'account','partial-inbox'],error='reference already used')
    if 'remaining_withdrawal_plan' not in live.report:
        live.report['remaining_withdrawal_plan']={}
        for role in ('payer','payee'):
            owner=getattr(live,role).local_account.address
            live.report['remaining_withdrawal_plan'][role]={'amount':live.read('credit_of',[owner]),'before':live.balance(owner)}
        live.save()
    for role in ('payer','payee'):
        owner=getattr(live,role).local_account.address
        plan=live.report['remaining_withdrawal_plan'][role];credit=plan['amount'];before=plan['before']
        receipt=live.tx(role,'withdraw',[credit,owner,'account','remaining-'+role],finalized=True)
        txid=next(e['transaction_hash'] for e in reversed(live.report['transactions']) if e['method']=='withdraw' and e['caller'].lower()==owner.lower())
        live.bindings[role].wait_withdrawal(txid,recipient=owner,amount=credit,before_balance=before,retries=120,interval=8000)
    live.finalize_journal();a=live.check_accounting();assert a['accounted_balance']==0,a
    live.report.update(complete=True,final_accounting=a,payout_inbox=inbox,finished_at=int(time.time()));live.save()
    live.scenario('partial_withdrawal_safe_inbox_eoa',inbox=inbox)
