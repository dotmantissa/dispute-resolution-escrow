# Verification

The release pins `genlayer-py==0.16.3`, `genlayer-test==0.29.2` and `genvm-linter==0.11.0`. Both production contracts use the concrete GenVM runner hash declared in their first line. Python 3.14.4 was used for the recorded local run.

## Local checks

Release qualification is blocked by the [live appeal integrity failure](STUDIO_APPEAL_BLOCKER.md). Completed component checks below do not establish a usable post-appeal deployment.

The reviewed contracts passed both GenVM lint/semantic checks. The current local suite passed 296 tests, covering:

- Creation and custody accounting, principal/bond capacity, exact bond rounding and replay rejection.
- Immutable owner reconciliation and preservation of other parties' liabilities.
- Time-boundary exclusivity, consent, response readiness, supplements and independent evidence budgets.
- All 103 valid economic decisions against every other decision, with exact payout agreement for compatible pairs.
- Inconclusive results, matching settlement offers, cancellation and the pre-agreed deadline fallback.
- Strict receipt acceptance, majority rejection, contradictory status fields, timeouts and durable appeal polling with refreshed finalized state.
- Source commitments in appeal tickets and rejection of missing, empty or changed deployed code before returning a stale finalized case.
- Public evidence URL policy, exact response hashes and actual pinned-address HTTPS fetching.
- Inbox source/configuration qualification, parent/child withdrawal tracking and recipient-failure propagation.

Direct mode uses official SDK storage and calldata handling. Its verified public evidence cache avoids repeatedly downloading identical bytes. It does not establish actual validator consensus, native transfer delivery or protocol appeal behavior; those are separate live checks.

The current wheel was installed in an independent virtual environment. All 158 SDK tests passed there with Web3 8.0.0. The installed package also rejected the real affected deployment through its new source-integrity guard. `artifacts/package-verification.json` records this qualification and preserves the earlier SDK revision's successful signed reconciliation separately as historical evidence.

## Live qualification

The current deployment manifest identifies the exact source hash and finalized contract address. A deployment's success is not treated as an end-to-end test result. Each live report has its own source, contract, transactions and explicit completion flag. Pending reports are not completed verification evidence.

The Studio suite exercises actual independent validators, public HTTP requests, model calls, native custody and protocol appeals. Fault deployments add deliberate rejection only in isolated test sources. The production contract has no fault-injection entry point.

The source-availability suite runs a real public HTTPS origin exposing only in-memory test documents. It separately changes and deletes the exact committed URLs, observes them before adjudication, and records multiple evaluator requests plus the stored snapshot-use observations. No provider API or cached immutable URL substitutes for the tested origin.

## Completed isolated live checks

These reports reached successful completion on their own recorded books. All parent and emitted transactions finalized, including explicitly expected negative fixtures. Each book ended with zero native balance, zero liabilities and no pending withdrawals. The source and positive-payout suites passed together in 1117.67 seconds.

| Report | Parent transactions | Emitted transactions | Ending native balance |
| --- | ---: | ---: | ---: |
| [Rejected funded consensus and owner recovery](../artifacts/rejected-consensus-recovery.json) | 4 | 2 | 0 |
| [Declining/failed recipient and retained-value recovery](../artifacts/recipient-failure-verification.json) | 8 | 6 | 0 |
| [Actual Intelligent Contract payer lifecycle](../artifacts/contract-party-verification.json) | 12 | 7 | 0 |
| [Exact changed and deleted URLs with snapshot fallback](../artifacts/source-availability-verification.json) | 17 | 4 | 0 |
| [Partial production inbox transfer, owner recovery and account payouts](../artifacts/positive-payout-verification.json) | 12 | 8 | 0 |

The main suite established its earlier lifecycle and economic scenarios, but its successful validator appeal was followed by missing source and a failed payout. It remains incomplete. The current inventory contains 313 tests, including 17 integration items; 313 passing tests are not claimed. Source integrity and post-appeal payout safety must pass before a release is qualified.

The final [component verification](../artifacts/component-verification.json) re-read deployed source and accounting for four healthy books and the production inbox. Their current balances and liabilities were zero. The same check reconfirmed that the affected book's source was unavailable while its balance remained 300033 faucet test wei. The report explicitly withholds release qualification.

## Reproduction

Follow the README installation and test commands. Real tests require an external signing key and durable external actor-key file. The public main suite writes a transaction journal before polling and refuses to overwrite an existing run. Set `GENLAYER_RESUME_RUN=1` only after checking the existing case state and using the same deployment and keys.

`GENLAYER_TEST_DEPLOYMENT_FILE` can name an external deployment manifest for a separate matching-source qualification book. Each report records its actual address. This allows component checks to remain isolated from a failed appeal; it does not qualify the failed deployment or bypass the release gate.

Set `ESCROW_EVIDENCE_ORIGIN=auto` to create a fresh anonymous SSH tunnel per source case, or provide your own HTTPS reverse tunnel to the loopback server on port 18765. The automatic option requires the system SSH client and reads no user SSH configuration or identities. The origin must be reachable through public HTTPS by the Studio validators. The test exposes no filesystem or public state-changing endpoint. Stop the tunnel when verification finishes.

Native balances are faucet test balances. Results qualify the recorded Studio network and source, not future networks or runtime versions. Security assumptions and documentary limitations are specified separately in `SECURITY.md`.
