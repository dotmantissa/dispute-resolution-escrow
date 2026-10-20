"""A fundless release gate for Studio's successful appeal restoration path."""
import base64
import hashlib
import json
import os
from pathlib import Path
import time
from urllib.request import urlopen

import pytest
from genlayer_py import create_account, create_client
from genlayer_py.chains import studionet
from genlayer_escrow import EscrowClient, execution_succeeded, return_value, transaction_status
from tests.integration.transport import attach_transport
from tests.integration.test_source_availability import PublicOrigin, FreshTunnel

ROOT = Path(__file__).resolve().parents[2]
pytestmark = [pytest.mark.integration, pytest.mark.skipif(
    not os.environ.get('GENLAYER_PRIVATE_KEY') or not os.environ.get('GENLAYER_APPEAL_PROBE'),
    reason='Requires explicit fundless Studio appeal probe and signing key')]


def test_successful_appeal_preserves_source_and_reexecutes_prior_state():
    path = ROOT / 'artifacts/appeal-snapshot-probe.json'
    if path.exists():
        raise RuntimeError('Existing probe journal: inspect/archive it before a fresh fundless run')
    source = (ROOT / 'tests/integration/contracts/appeal_snapshot_probe.py').read_bytes()
    client = attach_transport(create_client(chain=studionet,
        account=create_account(os.environ['GENLAYER_PRIVATE_KEY'])))
    report = {'network': 'studionet', 'source_sha256': hashlib.sha256(source).hexdigest(),
              'complete': False, 'release_qualified': False, 'attached_value': 0,
              'transactions': [], 'started_at': int(time.time())}

    def save():
        temporary = path.with_suffix('.tmp')
        temporary.write_text(json.dumps(report, indent=2, default=str) + '\n')
        temporary.replace(path)

    origin = PublicOrigin()
    tunnel = None
    try:
        tunnel = FreshTunnel()
        endpoint = '/appeal-snapshot-' + str(time.time_ns())
        origin.documents[endpoint] = b'1\n'
        url = tunnel.url + endpoint
        report['origin'] = url
        save()
        with urlopen(url, timeout=45) as response:
            assert response.read() == b'1\n'
        deployment = client.deploy_contract(code=source, args=[url], leader_only=False)
        report['transactions'].append({'method': 'deploy', 'transaction_hash': deployment})
        save()
        # Receipt polling works independently of this fixture's application schema.
        poller = EscrowClient(client, client.local_account.address)
        deployed = poller.wait(deployment, retries=300, interval=6000)
        address = deployed.get('contract_address') or deployed.get('to_address')
        assert address, 'Finalized deployment receipt has no contract address'
        report['contract_address'] = address
        save()
        assert base64.b64decode(client.provider.make_request('gen_getContractCode', [address])['result']) == source
        txid = client.write_contract(address=address, function_name='observe', args=[], value=0, leader_only=False)
        report['transactions'].append({'method': 'observe', 'transaction_hash': txid})
        save()
        accepted = poller.wait(txid, finalized=False, retries=300, interval=3000)
        assert return_value(accepted) == 1 and transaction_status(accepted) == 'ACCEPTED'
        previous_round = EscrowClient._round_count(accepted)
        # All initial validators have completed. Keep 2 stable for every appeal
        # validator and the new proposal. There is no HTTP mutation endpoint.
        with origin.lock:
            origin.phase = 'after-acceptance'
            origin.documents[endpoint] = b'2\n'
        with urlopen(url, timeout=45) as response:
            assert response.read() == b'2\n'
        submission = client.appeal_transaction(transaction_id=txid)
        report['appeal_submission'] = submission
        report['appealed_transaction'] = txid
        save()
        observed = False
        for _ in range(300):
            current = client.get_transaction(transaction_hash=txid)
            observed = observed or bool(current.get('appealed')) or EscrowClient._round_count(current) > previous_round
            if transaction_status(current) == 'FINALIZED':
                break
            time.sleep(6)
        else:
            raise AssertionError('Appeal did not finalize; preserve its stored transaction ID')
        report.update(appeal_observed=observed, final_status=transaction_status(current),
                      final_rounds=EscrowClient._round_count(current),
                      final_execution_success=execution_succeeded(current),
                      native_balance=client.get_balance(address))
        try:
            returned = base64.b64decode(client.provider.make_request('gen_getContractCode', [address])['result'])
        except Exception as error:
            report['post_appeal_source_error'] = str(error)
            save()
            raise AssertionError('Successful appeal lost executable source on the fundless probe') from error
        report['post_appeal_source_sha256'] = hashlib.sha256(returned).hexdigest()
        assert returned == source and observed and execution_succeeded(current), report
        value = EscrowClient(client, address)._read('get_observation', finalized=True)
        report['final_observation'] = value
        assert value == 2 and report['native_balance'] == 0, report
        report.update(complete=True, successful_overturn_qualified=True, finished_at=int(time.time()))
        save()
    finally:
        report['origin_requests'] = origin.requests
        origin.close()
        if tunnel is not None:
            tunnel.close()
        report['public_origin_stopped'] = True
        save()
