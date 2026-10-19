"""Official direct-mode SDK and a durable cache of verified public evidence bytes."""
import hashlib
import json
from pathlib import Path
import sys

import pytest
from genlayer_escrow import Document

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = json.loads((ROOT / 'tests/evidence/manifest.json').read_text())


@pytest.fixture(scope='session')
def evidence():
    return MANIFEST['documents']


@pytest.fixture(scope='session')
def live_documents(evidence):
    cache = {}
    directory = ROOT / '.gltest_cache/evidence'
    directory.mkdir(parents=True, exist_ok=True)
    for name, doc in evidence.items():
        body = (ROOT / 'tests/evidence' / name).read_bytes()
        assert hashlib.sha256(body).hexdigest() == doc['sha256']
        saved = directory / doc['sha256']
        if saved.exists():
            assert saved.read_bytes() == body
        else:
            assert Document.fetch(doc['url'], timeout=45).sha256 == doc['sha256']
            saved.write_bytes(body)
        cache[doc['url']] = {'status': 200, 'headers': {}, 'body': body}
    return cache


class TestAddress(bytes):
    __test__ = False
    @property
    def as_hex(self):
        return '0x' + self.hex()


@pytest.fixture
def direct_alice():
    return TestAddress(hashlib.sha256(b'escrow-payer').digest()[:20])


@pytest.fixture
def direct_bob():
    return TestAddress(hashlib.sha256(b'escrow-payee').digest()[:20])


@pytest.fixture
def direct_charlie():
    return TestAddress(hashlib.sha256(b'escrow-outsider').digest()[:20])


@pytest.fixture
def escrow(direct_vm, direct_deploy, direct_alice, live_documents):
    direct_vm.warp('2026-10-19T12:00:00Z')
    direct_vm.sender = direct_alice
    direct_vm._live_web_handler = lambda request: {'ok': {'response': live_documents[request['url']]}}
    return direct_deploy(str(ROOT / 'contracts/dispute_escrow.py'), direct_alice.as_hex)


@pytest.fixture
def module(escrow):
    return sys.modules['_contract_dispute_escrow']


@pytest.fixture
def fund(escrow, direct_vm, direct_alice, module):
    def top_up(amount):
        direct_vm.sender = direct_alice
        address = module.gl.message.contract_address
        direct_vm.deal(address, int(escrow.balance) + amount)
        direct_vm.value = amount
        received = escrow.deposit()
        direct_vm.value = 0
        assert received == amount
    return top_up


@pytest.fixture
def create(escrow, direct_vm, direct_alice, direct_bob, evidence, fund):
    sequence = 0
    def new(*, principal=10001, reference=None, payee=None, delivery_period=3600,
            review_period=600, bond_bps=1000, response_period=60, adjudication_period=600,
            fallback_payee_bps=5000, terms='terms.md', prepay=True):
        nonlocal sequence
        sequence += 1
        direct_vm.sender = direct_alice
        if prepay and type(principal) is int and principal > 0:
            fund(principal)
        doc = evidence[terms]
        return escrow.create_escrow(reference or f'order-{sequence}', payee or direct_bob.as_hex,
            doc['url'], doc['sha256'], principal, delivery_period, review_period, bond_bps,
            response_period, adjudication_period, fallback_payee_bps)
    return new


@pytest.fixture
def delivered(create, escrow, direct_vm, direct_bob, evidence):
    eid = create()
    direct_vm.sender = direct_bob
    escrow.accept_engagement(eid)
    doc = evidence['delivery-full.md']
    escrow.claim_delivery(eid, doc['url'], doc['sha256'])
    return eid


@pytest.fixture
def disputed(delivered, escrow, direct_vm, direct_alice, evidence, fund):
    doc = evidence['dispute-good-faith.md']
    bond = escrow.get_escrow(delivered)['bond_required']
    fund(bond)
    direct_vm.sender = direct_alice
    escrow.dispute(delivered, doc['url'], doc['sha256'], bond)
    return delivered
