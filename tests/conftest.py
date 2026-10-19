"""Real SDK direct-mode checks. HTTPS documents are fetched live, never stubbed.

Direct mode validates deterministic logic and storage. Only the integration suite
can establish actual custody, model behavior, serialization and validator consensus.
"""
import hashlib
import json
from pathlib import Path
import sys
import urllib.request

import pytest

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = json.loads((ROOT / "tests/evidence/manifest.json").read_text())


@pytest.fixture(scope="session")
def evidence():
    return MANIFEST["documents"]


@pytest.fixture(scope="session")
def live_documents(evidence):
    cache = {}
    # Cache real immutable responses across deterministic test cases, avoiding repeated IO.
    for name, document in evidence.items():
        request = urllib.request.Request(document["url"], headers={"User-Agent": "escrow-verification"})
        with urllib.request.urlopen(request, timeout=45) as response:
            body = response.read(32769)
            assert response.status == 200
            assert hashlib.sha256(body).hexdigest() == document["sha256"]
            assert body == (ROOT / "tests/evidence" / name).read_bytes()
            cache[document["url"]] = {"status": response.status, "headers": {}, "body": body}
    return cache


@pytest.fixture
def escrow(direct_vm, direct_deploy, direct_alice, direct_bob, direct_charlie, evidence, live_documents):
    direct_vm.warp("2026-10-19T12:00:00Z")
    direct_vm.sender = direct_alice
    direct_vm._live_web_handler = lambda request: {"ok": {"response": live_documents[request["url"]]}}
    contract = direct_deploy(str(ROOT / "contracts/dispute_escrow.py"))
    return contract


@pytest.fixture
def module(escrow):
    return sys.modules["_contract_dispute_escrow"]


@pytest.fixture
def create(escrow, direct_vm, direct_alice, direct_bob, evidence):
    sequence = 0

    def new(*, principal=10001, reference=None, payee=None, delivery_period=3600,
            review_period=600, bond_bps=1000, terms="terms.md"):
        nonlocal sequence
        sequence += 1
        direct_vm.sender = direct_alice
        direct_vm.value = principal
        doc = evidence[terms]
        result = escrow.create_escrow(reference or f"order-{sequence}",
                    payee or direct_bob.as_hex, doc["url"], doc["sha256"],
                    delivery_period, review_period, bond_bps)
        direct_vm.value = 0
        return result
    return new


@pytest.fixture
def delivered(create, escrow, direct_vm, direct_bob, evidence):
    escrow_id = create()
    doc = evidence["delivery-full.md"]
    direct_vm.sender = direct_bob
    escrow.claim_delivery(escrow_id, doc["url"], doc["sha256"])
    return escrow_id


@pytest.fixture
def disputed(delivered, escrow, direct_vm, direct_alice, evidence):
    doc = evidence["dispute-good-faith.md"]
    direct_vm.sender = direct_alice
    direct_vm.value = escrow.get_escrow(delivered)["bond_required"]
    escrow.dispute(delivered, doc["url"], doc["sha256"])
    direct_vm.value = 0
    return delivered


class TestAddress(bytes):
    """Address bytes usable before the direct runner has imported its SDK."""
    __test__ = False

    @property
    def as_hex(self):
        return "0x" + self.hex()


@pytest.fixture
def direct_alice():
    return TestAddress(hashlib.sha256(b"escrow-payer").digest()[:20])


@pytest.fixture
def direct_bob():
    return TestAddress(hashlib.sha256(b"escrow-payee").digest()[:20])


@pytest.fixture
def direct_charlie():
    return TestAddress(hashlib.sha256(b"escrow-outsider").digest()[:20])
