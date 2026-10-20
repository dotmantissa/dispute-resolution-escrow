# Audit remediation

The audit of version 1 identified two high-severity issues, a URL policy defect, incomplete live qualification and contradictory documentation. It did not identify a payout tolerance or precedent defect in the original exact-equality validator. Version 2 retains exact economic agreement and changes custody and lifecycle behavior.

Subsequent live qualification found a new release blocker: source became unavailable after a successful validator appeal while native test funds remained in the account. The SDK now rejects that source-integrity failure, but the hosted network's restoration behavior remains unresolved. See [Studio appeal integrity blocker](STUDIO_APPEAL_BLOCKER.md). This is not a completed release.

| Finding | Correction | Verification |
| --- | --- | --- |
| Successful live appeal was followed by loss of executable book source while native value remained | SDK commits source across appeals and checks it before deposits; hosted state restoration remains a release blocker | Real affected-book and control-book evidence; installed SDK rejects stale settlement and further funding |
| Provisional outgoing value could be mistaken for a fresh deposit during remediation | Require authenticated finalized self-acknowledgements before reconciliation; inbox also serializes outgoing transfers until acknowledgement | Real isolated reproduction, corrected-source provisional reconciliation rejection and post-finality idempotence |
| Leader success was treated as consensus success, including finalized majority disagreement | SDK requires authoritative majority agreement and returning execution in an accepted/finalized lifecycle | Receipt matrix, contradictory-result cases and real all-validator rejection harness |
| Studio retained native value when funded evidence consensus rejected its state | Separate deterministic deposits from nonpayable evidence calls; immutable funding owner and balance reconciliation | Direct custody invariants and actual funded majority-rejection recovery with permissionless reconciliation and owner withdrawal |
| Local/private hosts, numeric IP tricks and unsafe redirects were admitted by SDK fetching | Public DNS grammar, global-address checks, address pinning, verified TLS and redirect validation | Unsafe URL regressions and actual pinned-address HTTPS retrieval of the committed corpus |
| Protocol appeal lifecycle was not exercised | Persist original and submission IDs, observe appeal progression, verify source and refresh finalized case storage | Real stored-ID polling reached three rounds and exposed the source-loss blocker; unit traces also cover changed and rejected rulings |
| Arbitrary failed IC recipients and partial withdrawals lacked live qualification | Recoverable standalone inbox, exact-source SDK qualification, preflight and emitted child tracking | Parent/child SDK regressions, real rejecting/declining recipients, partial inbox withdrawal and subsequent recovery |
| Changed/deleted-source test observed provider API rather than the validator URLs | Controlled real public HTTPS evidence origin, no-store responses and request logs for exact URLs | Separate changed-only and deleted-404 cases assert snapshot use and multiple validator requests |
| Payee could not answer the dispute | Bounded authenticated-party supplements and a response window | Readiness, cutoff, duplicate, byte-budget and authorization tests, plus real payee rebuttal |
| Inconclusive cases could lock indefinitely | Mutually accepted fixed deadline fallback, alongside bilateral negotiation | Boundary tests and real permissionless fallback settlement |
| Payer could select an almost-zero dispute bond | Minimum 1000 basis points, explicitly accepted by payee | Bond floor, rounding and exact prepaid debit tests |
| Documentary opponent quotations could look like admissions | Include authenticated submitter and explicit prompt rules for opposing quotations, claimed signatures and repeated allegations | Decision prompt checks and real prompt-injection adjudication |
| Duplicate-reference description contradicted behavior | Rewrite documentation around the v2 nonpayable API and untouched prepaid credit on rejection | Real duplicate-reference rejection and accounting comparison |

Verification reports record their own contract address and source hash. Fault-injection methods and deliberately rejecting recipients exist only in isolated test deployments. They are never present in the production primitive. The published main deployment and every production-source test book must match the exact checked-in source bytes.

The security document preserves the remaining trust boundaries: public documentary truth, model interpretation, GenLayer consensus, protocol finality, sandbox networking and custom recipient design. No audit or test suite proves that every future external fact, network version or LLM decision is correct.
