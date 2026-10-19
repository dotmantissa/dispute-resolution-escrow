# Dispute Resolution Escrow

Native GEN escrow for transactions with a specific documented promise. A payer funds an engagement, the payee claims delivery, and a review period gives the payer time to dispute. GenLayer validators independently read the original terms and both parties' evidence before deciding how much of the payment the payee earned.

A successful dispute can refund all or part of the principal. A clearly bad-faith dispute transfers the payer's bond to the payee. An honest dispute returns the bond to the payer, including when the payee receives a full award. Every payout uses integer arithmetic and preserves every wei.

## Deployed contract

Studio contract: [`0xA9BAc09D9813c890292Cb862323130D4508E7f30`](https://explorer-studio.genlayer.com/address/0xA9BAc09D9813c890292Cb862323130D4508E7f30).

Deployment transaction: [`0xbfdd2029b19685f6574b81d41c5142c9a104659c23f6dc1b1ff38fa8e44d889e`](https://explorer-studio.genlayer.com/tx/0xbfdd2029b19685f6574b81d41c5142c9a104659c23f6dc1b1ff38fa8e44d889e).

The address, transaction, source hash and finalized execution result are recorded in [artifacts/deployment.json](artifacts/deployment.json). [artifacts/schema.json](artifacts/schema.json) contains the deployed interface. The explorer link is included in the manifest.

Studio uses database-backed balances and test GEN. It supports the native-value and consensus paths exercised here. This deployment is infrastructure for Studio builders, not evidence of mainnet readiness or an independent audit.

## What builders get

- A permissionless escrow registry with isolated records and payer-scoped references.
- A pinned GenVM contract with no administrator, upgrade mechanism or custody override.
- SHA-256 commitments to public UTF-8 terms, delivery and dispute evidence.
- Immutable snapshots that preserve the agreement if a public source changes or disappears.
- Independent validator assessment with exact agreement on the payout share and bad-faith finding.
- Delivery deadlines, review windows, voluntary acceptance, negotiated settlement and withdrawals.
- Explicit payable acceptance results and sender-owned credits for rejected payments.
- An installable Python binding that uses the real GenLayer SDK and defaults to finalized reads.

## Install

Python 3.12 or later is required for the contract testing tools.

```bash
git clone https://github.com/dotmantissa/dispute-resolution-escrow.git
cd dispute-resolution-escrow
git checkout implementation
python3 -m venv .venv
. .venv/bin/activate
pip install -e '.[test]'
```

To install the builder binding directly from the repository:

```bash
pip install 'git+https://github.com/dotmantissa/dispute-resolution-escrow.git@implementation'
```

The package is named `genlayer-dispute-escrow`. Installation from Git is supported; a PyPI publication is not required.

## Integration

```python
import json
import os
from pathlib import Path
from genlayer_py import create_account, create_client
from genlayer_py.chains import studionet
from genlayer_escrow import Document, EscrowClient

manifest = json.loads(Path('artifacts/deployment.json').read_text())
account = create_account(os.environ['GENLAYER_PRIVATE_KEY'])
client = create_client(chain=studionet, account=account)
escrow = EscrowClient(client, manifest['contract_address'])

# Publish the actual agreement at a stable public HTTPS URL before funding.
terms = Document.fetch(os.environ['TERMS_URL'])
tx_id = escrow.create(
    reference='marketplace-order-1842',
    payee=os.environ['PAYEE_ADDRESS'],
    terms=terms,
    principal=10**18,
    delivery_period=7 * 86400,
    review_period=86400,
    bond_bps=1000,
)
# Persist tx_id in the application's durable transaction journal before polling.
escrow.wait(tx_id)
escrow_id = escrow.find_escrow(account.address, 'marketplace-order-1842')
record = escrow.get_escrow(escrow_id)
assert record['status'] == 'FUNDED'
```

Supported payable calls return an explicit acceptance result. A rejected request creates a withdrawal credit for all attached value. The binding raises `PaymentRejected` after successful execution of that refund-credit path; inspect its `refund_credit` and withdraw normally.

The payer and payee use separate signed clients. [The integration guide](docs/INTEGRATION.md) covers the complete workflow, payable calls, contract recipients, retries, finality and cross-contract use. [The technical reference](docs/TECHNICAL.md) specifies every method and financial rule. [The architecture](docs/ARCHITECTURE.md) explains the consensus boundary and failure paths.

## Verify

```bash
genvm-lint check contracts/dispute_escrow.py
genvm-lint check tests/integration/contracts/value_receiver.py
pytest tests/direct -v
pytest tests/test_client.py -v
```

Direct-mode tests use the actual SDK's storage and calldata encoding. They fetch the public revision-pinned evidence documents over HTTPS, then cache those exact responses for deterministic checks. They do not call mock web or model APIs. Direct mode does not establish network custody or model consensus.

The Studio suite submits signed, funded transactions and checks execution results, account balances, contract balances and validator votes. It pipelines accepted intermediate actions, then rechecks every transaction at finalization before reporting completion. Withdrawals always wait for finalization. It exercises the actual models and public evidence without mocked responses or validators:

```bash
export GENLAYER_PRIVATE_KEY='your Studio signing key'
# Optional recovery location for generated payee and outsider keys, outside the repo:
export GENLAYER_TEST_KEYS_FILE='/secure/local/path/escrow-test-actors.json'
pytest tests/integration/test_studio.py -v -s -x
```

An additional test changes and deletes an actual public gist after the contract has committed its evidence, then verifies settlement from the original snapshots:

```bash
export GENLAYER_GITHUB_TOKEN='a GitHub token with gist permission'
pytest tests/integration/test_source_availability.py -v -s -x
```

The live helper respects the server's throttle cooldown and retries read-only transport failures. An interrupted write must be reconciled through its recorded transaction ID or payer reference before resubmission. Generated actor keys stay in the protected recovery file outside the repository. For a reconciled unfinished scenario, `GENLAYER_RESUME_RUN=1` reuses the existing run ID and journal; select only unfinished cases with pytest's `-k` option. Completed escrow references remain permanently used.

The suite uses Studio's native test-token faucet for accounts that need funding and reuses sufficiently funded recovery accounts. It produces a durable verification report in `artifacts/studio-verification.json` and leaves all test escrows settled. Payer withdrawal proceeds are sent to a real receiving contract to verify contract integration. Run the suite against an otherwise unused registry if another application's active balances would make its final zero-balance assertion inappropriate.

Deploy a separate registry with the same source when needed:

```bash
GENLAYER_PRIVATE_KEY='your Studio signing key' python tests/integration/deploy.py
```

The deployment helper resumes an existing transaction recorded in the manifest. To intentionally deploy another registry, archive that manifest outside the repository first. It never treats accepted or finalized status alone as successful execution.

## Operating limits

Evidence is public, must be UTF-8 text and is limited to 32 KiB per document. Images, inaccessible pages, authenticated content and private delivery cannot be inspected through this version's evidence path. Validators judge the committed text, not the truth of every assertion in it. Clear terms and independently verifiable evidence matter.

An inconclusive assessment preserves custody. Either party can seek another assessment, or both can approve a settlement split. There is no unilateral timeout that gives a disputed payment to either side. Model consensus can still be wrong. See [security and operational considerations](docs/SECURITY.md) before integrating custody.

Licensed under MIT.
