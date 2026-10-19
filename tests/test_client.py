"""Receipt classification and durable polling regressions, plus real HTTPS fetching."""
import hashlib
import json
from pathlib import Path

import pytest
from genlayer_escrow import (Document,EscrowClient,ExecutionFailed,PollingTimeout,
    AppealTicket,consensus_accepted,execution_succeeded,transaction_status)
from genlayer_py import create_account,create_client
from genlayer_py.chains import studionet


def receipt(status='FINALIZED',decision=6,execution='SUCCESS',**extra):
    return {'status':status,'result':decision,
            'consensus_data':{'leader_receipt':[{'execution_result':execution}]},**extra}


@pytest.mark.parametrize('content',[b'',b'x'*32769,b'\x00',b' \n',b'\xff'])
def test_invalid_document_bytes(content):
    with pytest.raises((ValueError,UnicodeDecodeError)):
        Document.from_bytes('https://evidence.example.com/doc',content)


def test_document_hashes_exact_bytes():
    a=Document.from_bytes('https://evidence.example.com/doc',b'terms\n')
    b=Document.from_bytes('https://evidence.example.com/doc',b'terms\r\n')
    assert a.sha256==hashlib.sha256(b'terms\n').hexdigest() and a.sha256!=b.sha256


@pytest.mark.parametrize('url',[
    'http://example.com/doc','https://localhost/doc','https://127.0.0.1/doc',
    'https://0x7f.0.0.1/doc','https://0177.0.0.1/doc','https://2130706433/doc',
    'https://127.1/doc','https://[::1]/doc','https://example.com:443/doc',
    'https://u:p@example.com/doc','https://example.com/doc#fragment',
    'https://host.local/doc','https://host.internal/doc','https://host.arpa/doc',
    'https://a-.example.com/doc','https://-a.example.com/doc',
])
def test_unsafe_url_rejected_before_fetch(url):
    with pytest.raises(ValueError):
        Document.fetch(url)


@pytest.mark.parametrize('url,digest',[
    ('https://example.com/doc','G'*64),('https://example.com/doc','0'*63)])
def test_invalid_document_metadata(url,digest):
    with pytest.raises(ValueError):Document(url,digest)


def test_real_pinned_ip_fetch_matches_committed_evidence():
    manifest=json.loads((Path(__file__).parent/'evidence/manifest.json').read_text())
    doc=Document(**manifest['documents']['terms.md'])
    assert Document.fetch(doc.url,timeout=45)==doc


@pytest.mark.parametrize('status',['PENDING','PROPOSING','APPEAL_COMMITTING','APPEAL_REVEALING',
    'UNDETERMINED','CANCELED','VALIDATORS_TIMEOUT','LEADER_TIMEOUT','UNKNOWN',True,None])
@pytest.mark.parametrize('decision',[6,7,5,0])
def test_leader_return_never_overrides_nonaccepted_lifecycle(status,decision):
    assert not execution_succeeded(receipt(status,decision))


@pytest.mark.parametrize('status',['ACCEPTED','FINALIZED','5','7',5,7])
@pytest.mark.parametrize('decision',[7,'7','MAJORITY_DISAGREE',5,0,None,True,6.0])
def test_finalized_rejected_or_unknown_decision_is_not_success(status,decision):
    assert not execution_succeeded(receipt(status,decision))


@pytest.mark.parametrize('status',['ACCEPTED','FINALIZED',5,7])
@pytest.mark.parametrize('decision',[6,'6','MAJORITY_AGREE'])
def test_accepted_returning_execution_succeeds(status,decision):
    assert execution_succeeded(receipt(status,decision))


def test_authoritative_execution_error_overrides_successful_leader():
    assert not execution_succeeded(receipt(tx_execution_result=2))
    assert not execution_succeeded(receipt(tx_execution_result=True))
    assert execution_succeeded(receipt(tx_execution_result=1))
    assert not execution_succeeded(receipt(result_name='MAJORITY_DISAGREE'))
    assert not execution_succeeded(receipt(status_name='UNDETERMINED'))
    assert not execution_succeeded(receipt(execution='ERROR'))


class LifecycleTrace:
    """Read adapter for explicit lifecycle inputs; live tests qualify the real network."""
    def __init__(self,transactions,record=None):
        self.transactions=list(transactions)
        self.record=record or {'status':'SETTLED','payee_bps':10000,'payer_bad_faith':False}
        self.polled=[];self.reads=[]
    def get_transaction(self,transaction_hash):
        self.polled.append(transaction_hash)
        return self.transactions.pop(0) if len(self.transactions)>1 else self.transactions[0]
    def read_contract(self,**kwargs):
        self.reads.append(kwargs)
        return self.record


def binding(trace):return EscrowClient(trace,'0x'+'12'*20)


def test_wait_rejects_real_audit_failure_shape_at_both_wait_targets():
    for finalized,state in [(False,'UNDETERMINED'),(True,'FINALIZED')]:
        data=receipt(state,7)
        data['consensus_data']['votes']={'a':'disagree','b':'disagree','c':'disagree'}
        trace=LifecycleTrace([data])
        with pytest.raises(ExecutionFailed) as error:
            binding(trace).wait('stored-tx',finalized=finalized,retries=1,interval=0)
        assert error.value.receipt is data and trace.polled==['stored-tx']


def test_wait_polls_same_stored_id_through_appeal_and_finalization():
    trace=LifecycleTrace([receipt('ACCEPTED'),receipt('APPEAL_COMMITTING'),
                          receipt('APPEAL_REVEALING'),receipt('FINALIZED')])
    assert execution_succeeded(binding(trace).wait('stored-id',retries=4,interval=0))
    assert trace.polled==['stored-id']*4


def test_timeout_retains_original_transaction_id_and_last_receipt():
    last=receipt('APPEAL_REVEALING')
    with pytest.raises(PollingTimeout) as error:
        binding(LifecycleTrace([last])).wait('keep-this-id',retries=2,interval=0)
    assert error.value.transaction_id=='keep-this-id' and error.value.receipt is last


def test_resumed_appeal_refreshes_finalized_ruling_and_leaves_pending_state():
    stale={'status':'SETTLED','payee_bps':10000,'payer_credit':0,'payee_credit':11002}
    refreshed={'status':'SETTLED','payee_bps':5000,'payer_credit':6002,'payee_credit':5000}
    trace=LifecycleTrace([
        receipt('APPEAL_COMMITTING',num_of_rounds=1),
        receipt('APPEAL_REVEALING',num_of_rounds=2),
        receipt('FINALIZED',num_of_rounds=2)],record=refreshed)
    ticket=AppealTicket('original-tx','original-tx','42',1,0)
    encoded=json.dumps(ticket.__dict__)
    outcome=binding(trace).wait_appeal(AppealTicket(**json.loads(encoded)),retries=3,interval=0)
    assert outcome['state']=='SETTLED' and outcome['appeal_observed']
    assert outcome['escrow']==refreshed and outcome['escrow']!=stale
    assert trace.polled==['original-tx']*3
    assert trace.reads[-1]['function_name']=='get_escrow'
    assert trace.reads[-1]['args']==['42']
    assert str(trace.reads[-1]['transaction_hash_variant'].value)=='latest-final'


def test_rejected_appeal_refreshes_unsettled_case_without_claiming_success():
    trace=LifecycleTrace([receipt('FINALIZED',7,num_of_rounds=2)],record={'status':'DISPUTED','last_assessment':None})
    outcome=binding(trace).wait_appeal(AppealTicket('tx','tx','8',1,0),retries=1,interval=0)
    assert outcome['state']=='DISPUTED' and not outcome['transaction_succeeded']
    assert outcome['escrow']['last_assessment'] is None


@pytest.mark.parametrize('principal',[0,-1,True,'100'])
def test_client_rejects_invalid_principal_before_submission(principal):
    sdk=create_client(chain=studionet,account=create_account())
    with pytest.raises(ValueError,match='Principal'):
        EscrowClient(sdk,'0x'+'12'*20).create('order','0x'+'34'*20,
            Document('https://evidence.example.com/terms','0'*64),principal,fallback_payee_bps=5000)


@pytest.mark.parametrize('bond',[0,-1,True,'100'])
def test_client_rejects_invalid_bond_before_submission(bond):
    sdk=create_client(chain=studionet,account=create_account())
    with pytest.raises(ValueError,match='Bond'):
        EscrowClient(sdk,'0x'+'12'*20).dispute('1',Document('https://evidence.example.com/dispute','0'*64),bond=bond)
