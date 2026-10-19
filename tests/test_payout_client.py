"""Withdrawal completion requires the parent and actual child execution."""
import base64
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from genlayer_escrow import EscrowClient,RecipientExecutionFailed,PollingTimeout
from tests.test_client import receipt

BOOK='0x'+'12'*20
OWNER='0x'+'34'*20
INBOX='0x'+'56'*20


def returning(value,**extra):
    data=receipt(**extra)
    data['consensus_data']['leader_receipt'][0]['result']={'payload':{'readable':json.dumps(value)}}
    return data


class PayoutTrace:
    def __init__(self,*,child_ok=True,children=True):
        self.local_account=SimpleNamespace(address=OWNER);self.provider=self
        self.code=(Path(__file__).parents[1]/'contracts/payout_inbox.py').read_bytes()
        self.config={'owner':OWNER,'escrow_account':BOOK,'custody':'native-balance'}
        self.parent=returning({'state':'EMITTED','amount':17,'recipient':INBOX,'recipient_kind':'contract'})
        self.child=receipt(decision=6 if child_ok else 7,to_address=INBOX,value=17)
        self.children=['child-stored-id'] if children else [];self.polled=[]
    def make_request(self,method,args):
        assert method=='gen_getContractCode' and args==[INBOX]
        return {'result':base64.b64encode(self.code).decode()}
    def read_contract(self,**kwargs):return self.config
    def get_transaction(self,transaction_hash):
        self.polled.append(transaction_hash)
        return self.parent if transaction_hash=='parent-stored-id' else self.child
    def get_triggered_transaction_ids(self,transaction_hash):
        assert transaction_hash=='parent-stored-id';return self.children
    def get_balance(self,address):assert address==INBOX;return 17


def test_safe_inbox_qualification_binds_source_owner_and_book():
    trace=PayoutTrace();client=EscrowClient(trace,BOOK)
    assert client.qualify_inbox(INBOX)==trace.config
    trace.code+=b'\n'
    with pytest.raises(ValueError,match='published'):client.qualify_inbox(INBOX)


@pytest.mark.parametrize('field,value',[('owner',BOOK),('escrow_account',OWNER),('custody','callback-counter')])
def test_inbox_configuration_mismatch_fails_closed(field,value):
    trace=PayoutTrace();trace.config[field]=value
    with pytest.raises(ValueError,match='does not match'):EscrowClient(trace,BOOK).qualify_inbox(INBOX)


def test_success_tracks_the_actual_child_id():
    trace=PayoutTrace();outcome=EscrowClient(trace,BOOK).wait_withdrawal('parent-stored-id',recipient=INBOX,amount=17,before_balance=0,retries=1,interval=0)
    assert outcome['children']==['child-stored-id'] and trace.polled==['parent-stored-id','child-stored-id']


def test_rejected_child_is_not_parent_success_even_when_native_value_arrived():
    trace=PayoutTrace(child_ok=False)
    with pytest.raises(RecipientExecutionFailed) as failed:
        EscrowClient(trace,BOOK).wait_withdrawal('parent-stored-id',recipient=INBOX,amount=17,before_balance=0,retries=1,interval=0)
    assert failed.value.parent_receipt is trace.parent and failed.value.child_receipt is trace.child


def test_missing_child_does_not_complete_contract_payout_on_balance_alone():
    trace=PayoutTrace(children=False)
    with pytest.raises(PollingTimeout):
        EscrowClient(trace,BOOK).wait_withdrawal('parent-stored-id',recipient=INBOX,amount=17,before_balance=0,retries=1,interval=0)


def test_parent_return_must_bind_expected_recipient_and_amount():
    trace=PayoutTrace()
    for recipient,amount in ((OWNER,17),(INBOX,18)):
        with pytest.raises(ValueError,match='does not match'):
            EscrowClient(trace,BOOK).wait_withdrawal('parent-stored-id',recipient=recipient,amount=amount,before_balance=0,retries=1,interval=0)
