# Verification

The release pins `genlayer-py==0.16.3`, `genlayer-test==0.29.2` and `genvm-linter==0.11.0`. Both production contracts use the concrete GenVM runner hash declared in their first line. Python 3.14.4 was used for the recorded local run.

## Local checks

The reviewed source passed both GenVM lint/semantic checks. The local suite passed 291 tests, covering:

- Creation and custody accounting, principal/bond capacity, exact bond rounding and replay rejection.
- Immutable owner reconciliation and preservation of other parties' liabilities.
- Time-boundary exclusivity, consent, response readiness, supplements and independent evidence budgets.
- All 103 valid economic decisions against every other decision, with exact payout agreement for compatible pairs.
- Inconclusive results, matching settlement offers, cancellation and the pre-agreed deadline fallback.
- Strict receipt acceptance, majority rejection, contradictory status fields, timeouts and durable appeal polling with refreshed finalized state.
- Public evidence URL policy, exact response hashes and actual pinned-address HTTPS fetching.
- Inbox source/configuration qualification, parent/child withdrawal tracking and recipient-failure propagation.

Direct mode uses official SDK storage and calldata handling. Its verified public evidence cache avoids repeatedly downloading identical bytes. It does not establish actual validator consensus, native transfer delivery or protocol appeal behavior; those are separate live checks.

## Live qualification

The current deployment manifest identifies the exact source hash and finalized contract address. A deployment's success is not treated as an end-to-end test result. Each live report has its own source, contract, transactions and explicit completion flag. Pending reports are not completed verification evidence.

The Studio suite exercises actual independent validators, public HTTP requests, model calls, native custody and protocol appeals. Fault deployments add deliberate rejection only in isolated test sources. The production contract has no fault-injection entry point.

The source-availability suite runs a real public HTTPS origin exposing only in-memory test documents. It separately changes and deletes the exact committed URLs, observes them before adjudication, and records multiple evaluator requests plus the stored snapshot-use observations. No provider API or cached immutable URL substitutes for the tested origin.

## Reproduction

Follow the README installation and test commands. Real tests require an external signing key and durable external actor-key file. The public main suite writes a transaction journal before polling and refuses to overwrite an existing run. Set `GENLAYER_RESUME_RUN=1` only after checking the existing case state and using the same deployment and keys.

The test-only source tunnel can be established with an SSH reverse tunnel to the loopback server on port 18765. The origin must be reachable through public HTTPS by the Studio validators. The test exposes no filesystem or public state-changing endpoint. Stop the tunnel when verification finishes.

Native balances are faucet test balances. Results qualify the recorded Studio network and source, not future networks or runtime versions. Security assumptions and documentary limitations are specified separately in `SECURITY.md`.
