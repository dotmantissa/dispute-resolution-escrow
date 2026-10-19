# Security and operating model

## Custody boundaries

The contract holds native GEN only. It does not accept ERC-20 claims, bridge receipts or an off-chain balance as payment. Each creation attaches a positive principal and each dispute attaches the exact bond. Nonpayable authorization and state errors revert before changing escrow state. Supported payable validation failures return an explicit rejection and credit the full incoming amount to its actual sender, including unauthorized dispute payments and duplicate funding attempts. They do not create or alter an escrow.

Settlement allocates the entire principal and bond once. It preserves integer value, updates the aggregate liability ledger and cannot be replayed. Withdrawals spend only the immediate sender's existing credit and debit it before emitting an asynchronous transfer. There is no administrator, pause key, upgrade path, forced dispute default or privileged withdrawal.

Rejected payment credits are deliberate application outcomes, not VM execution failures. This preserves value under the failed-payable-call behavior observed on Studio. Malformed ABI input, unsupported payable targets and unexpected VM failures remain subject to the network's own value-handling rules.

The accounting invariant is checked by tests across many independent escrows. The view itself is a record of liabilities, so operators should compare it with the native network balance. Value sent outside supported payable methods is not automatically assigned or recoverable.

## Evidence integrity and limits

A source URL does not prove authenticity, authorship, receipt or completeness. A malicious party can publish a false statement. Validators must evaluate the evidence rather than assume submitted statements are facts. Public acknowledgments, independently signed records and verifiable deliverables are stronger than unsupported claims.

The exact original terms, delivery and dispute snapshots are committed by SHA-256 and agreed at submission. Adjudicators re-fetch the sources independently and verify their commitments. If a source changes or becomes unavailable they retain the earlier committed snapshot. This blocks later replacement and availability-based custody attacks. It does not prove that a signed statement is authentic unless the text and verification context support that conclusion.

The supported evidence format is public bounded UTF-8 text. Documents are not rendered, linked pages are not recursively fetched, images are not interpreted, and authenticated systems are not accessed. A document must include the facts required to evaluate the promise. Secrets cannot be removed from public on-chain history after publication.

HTTPS hostname filtering rejects several unsafe forms. DNS rebinding, public names resolving to private addresses and redirects remain the network's responsibility. Do not treat this syntax filter as a complete SSRF boundary. Network sandboxing and request limits must protect validator infrastructure.

## Model and consensus risk

The prompt treats evidence as untrusted data and directs evaluators to disregard embedded role changes or payout instructions. Validator code independently repeats the substantive task and compares every field controlling money. It does not accept a leader's answer merely because its JSON is valid. The public test evidence includes a direct prompt-injection attempt.

Consensus reduces reliance on one evaluator. It cannot guarantee factual correctness, independence of model training or immunity to persuasive malicious evidence. A majority can agree on the wrong conclusion. The displayed reason is the leader's explanation and need not match each validator's wording. Exact payout agreement can also reduce liveness for ambiguous cases. No tolerance silently alters a fractional award.

Bad faith requires affirmative evidence of knowing abuse plus a conclusive full-delivery finding. Losing a dispute alone does not forfeit the bond. A determined dishonest payer may still avoid a penalty if intent cannot be established. A bond deters abuse only to the extent its chosen amount, available evidence and expected penalty justify that economic claim. The registry does not promise that every frivolous dispute becomes economically irrational.

## Deadlines and liveness

The payer commits funds before the payee accepts the work. The payer can recover a never-claimed engagement at its delivery deadline; the payee may reject it earlier. Once delivery is claimed, the payer must submit a dispute before its review deadline. Network processing delays and document fetch failures matter, so human review periods should include operating margin.

No unilateral timeout decides a disputed payment. If consensus is persistently inconclusive, unavailable or unable to agree, funds remain locked until a conclusive retry or matching settlement offers. This protects against an arbitrary forced refund or payout but makes disputed liveness conditional. Integrators must disclose that tradeoff to their users.

Time-based transitions require an explicit transaction. Anyone can submit them, but the network does not run background work for the escrow. A keeper or application process should monitor deadlines and submit the appropriate call.

## Transfers, appeals and recipient failures

Settlement credits are separate from payout. Native transfers execute on finalization. Builders should wait for finalized evidence and settlement before initiating dependent financial actions, and track protocol appeals through the normal network lifecycle. The contract relies on GenLayer's ordering, rollback and finalization rules; it does not implement a second independent finality protocol.

An account withdrawal uses the EVM interface. An IC withdrawal calls `receive_escrow()` with native value. Emission is asynchronous, and a failed child transaction may not refund the parent. An incorrect or rejecting recipient can lose its funds. Test recipient compatibility, select the correct recipient kind and follow any child transaction to completion. No operator can mint replacement credits after a failed finalized withdrawal.

Studio balances are test balances managed by its database. Studio coverage does not validate real-network ghost-contract execution, fee estimation, EVM fallback behavior or gas consumption. Those properties require qualification on the intended fee-charging network before handling funds there.

## Verification and reporting

The checked-in tests cover deterministic validation, storage, deadlines, replay protection and conservation, as well as real Studio custody, HTTP evidence, model judgments, validator votes and recipient balances. Evidence and transaction hashes are included in the artifacts. Successful tests establish the observed cases, not a formal proof or an independent security audit.

Report vulnerabilities through the repository's private security reporting feature if available, or contact the repository owner without publishing exploit instructions against active escrow funds.
