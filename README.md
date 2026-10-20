# Dispute Resolution Escrow

**Release qualification is blocked by a live Studio appeal integrity failure.** The appealed book no longer returns deployed source while native test funds remain present. See the [incident evidence and release gate](docs/STUDIO_APPEAL_BLOCKER.md). The address below is a qualification record, not a usable escrow endpoint.

Native GEN escrow for a specific documented promise. Builders deploy a prepaid escrow book for each payer, commit the original terms, and let independent GenLayer validators assess delivery. An exact consensus decision determines the earned share and whether clear payer bad faith forfeits the dispute bond.

Version 2 separates native deposits from evidence evaluation. Failed evidence consensus cannot debit newly attached principal or bond because those calls are nonpayable. An immutable funding owner can recover native value that Studio retains after a failed call through balance reconciliation.

- [Blocked Studio qualification address](https://explorer-studio.genlayer.com/address/0x2A738Fb0EA7F055f5691B8c9d8a364D7d03F332F)
- [Deployment and source hash](artifacts/deployment.json)
- [Builder integration](docs/INTEGRATION.md)
- [Contract API and accounting](docs/TECHNICAL.md)
- [Consensus and custody architecture](docs/ARCHITECTURE.md)
- [Security assumptions](docs/SECURITY.md)
- [Audit corrections](docs/AUDIT_REMEDIATION.md)
- [Verification evidence](docs/VERIFICATION.md)

## Components

| Component | Purpose |
| --- | --- |
| `contracts/dispute_escrow.py` | Immutable payer-bound escrow book, evidence snapshots, exact economic consensus, settlement credits and withdrawals |
| `contracts/payout_inbox.py` | Separately deployable beneficiary-owned recipient with recovery based on its actual native balance |
| `src/genlayer_escrow` | Signed Python bindings, public evidence fetching, decision-aware polling, durable appeal tickets and child withdrawal tracking |
| `tests` | Contract invariants, SDK regressions and real Studio lifecycle, failure and evidence-source tests |

There is no application server, hosted adjudication service, operator key, administrator, upgrade mechanism or custom token. Each deployment is standalone. The published book belongs to its recorded payer; deploy your own book for your payer rather than sending money to that address.

## Install

```bash
git clone --branch implementation https://github.com/dotmantissa/dispute-resolution-escrow.git
cd dispute-resolution-escrow
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[test]'
```

The package is installed from this repository. Publication to PyPI is not required or claimed. `genlayer-py==0.16.3` is pinned; both contracts pin a concrete GenVM runner hash.

## Payment lifecycle

1. Deploy `DisputeEscrow(payer_address)`. Call payable `deposit` to credit that immutable payer.
2. Call nonpayable `create_escrow` to lock principal from prepaid credit and commit SHA-256-pinned terms. Specify all periods, the bond rate and the fallback split.
3. The payee explicitly accepts the recorded engagement, including its deadline fallback, then commits delivery evidence before the delivery deadline.
4. The payer accepts delivery, or opens a dispute before the review deadline and locks the exact bond from prepaid credit. Without a timely dispute, anyone can release payment after review expires.
5. Both parties may append bounded evidence. After the response deadline, or once both finish submitting, anyone may request adjudication.
6. Validators independently fetch and assess the committed evidence. They must agree exactly on conclusiveness, earned basis points and bad faith. A conclusive decision creates credits; an inconclusive assessment preserves locked funds.
7. Either party can propose a matching bilateral split. After the resolution deadline, anyone can apply the fallback that both parties accepted. These exits return the bond to the payer.
8. Credit owners withdraw to accounts or recoverable payout inboxes. Track finality and emitted child execution before treating a transfer as complete.

The payee receives `principal * payee_bps // 10000`. The payer receives the remaining principal. Clear, independently agreed payer bad faith transfers the bond to the payee; an unsuccessful dispute alone does not establish bad faith. Rounding always favors the payer by the indivisible remainder.

## Verify locally

```bash
genvm-lint check contracts/dispute_escrow.py
genvm-lint check contracts/payout_inbox.py
python -m pytest tests/direct tests/test_client.py tests/test_payout_client.py -v -s
```

Direct mode uses the official storage/calldata machinery. Public evidence bytes are fetched and checked against the committed corpus before being cached. Direct tests inspect consensus comparison rules; actual multi-validator HTTP/model execution is covered by the opt-in Studio suite.

## Verify on Studio

Set `GENLAYER_PRIVATE_KEY` outside the repository. `GENLAYER_TEST_KEYS_FILE` should name a protected external file containing test actor keys; the runner creates it if necessary. The shipped artifacts describe the published qualification run. Before a fresh run, archive its deployment manifest, schema and live verification reports outside the checkout. Deploy with `python -m tests.integration.deploy`, then run:

```bash
python -m pytest tests/integration/test_studio.py -v -s -x
python -m pytest tests/integration/test_custody_faults.py -v -s -x
```

The source-availability suite additionally requires `ESCROW_EVIDENCE_ORIGIN`, a real public HTTPS tunnel to the test server on `127.0.0.1:18765`. Set it to `auto` to create a fresh anonymous SSH tunnel for each case. Its documentation explains the origin and request logging. No production component depends on this test tunnel.

Studio quotas can pause a run. Submitted IDs are journaled before polling. Resume an interrupted run with the same keys, deployment and `GENLAYER_RESUME_RUN=1`; inspect the journal and case state first. The deployment helper resumes its recorded transaction only for the same signer and source. Never blindly repeat a deposit or deployment after an ambiguous submission error. Run a fresh deployment for a new full test run; test journals reject accidental overwrite.

## Scope

This primitive evaluates public documentary evidence. It does not prove physical delivery, establish private facts or replace evidence authentication by an application. Hashes preserve bytes, not truth. Model consensus can be inconclusive or incorrect; the response process and mutually accepted deadline fallback provide defined exits. All terms and evidence snapshots are public. See the security document before integrating custody.
