"""Qualify supported payouts independently of protocol appeal restoration."""
import os

import pytest

from tests.integration.test_studio import Live, ROOT, PRINCIPAL
from tests.integration.test_studio import test_08_partial_account_and_safe_contract_withdrawals as verify_payouts
from tests.integration.test_custody_faults import retarget

pytestmark = [pytest.mark.integration, pytest.mark.skipif(
    not os.environ.get('GENLAYER_PRIVATE_KEY'), reason='Requires Studio signing key')]


def test_standalone_safe_inbox_and_account_payouts():
    live = Live('positive-payout-verification.json')
    book = live.deploy((ROOT/'contracts/dispute_escrow.py').read_bytes(),
                       [live.payer.local_account.address], key='deploy-positive-payout-book')
    retarget(live, book)
    live.deployment = dict(live.deployment, contract_address=book)
    live.tx('payer', 'deposit', value=PRINCIPAL+43, key='positive-payout-deposit', finalized=True)
    eid = live.create('positive-payout')
    live.deliver(eid)
    live.tx('payer', 'accept_delivery', [eid], finalized=True)
    verify_payouts(live)
