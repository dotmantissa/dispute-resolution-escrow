# Contract reference

## Deployment and value

`DisputeEscrow(funding_owner: str)` stores one immutable nonzero payer address. The constructor takes no native payment. `deposit` is the only payable method. All other entry points are nonpayable.

`create_escrow` locks prepaid principal atomically after validating and snapshotting the terms. It returns the new decimal escrow ID. Reusing a payer reference reverts and leaves existing credit untouched. Failed evidence consensus leaves prepaid credit untouched. It does not perform a new native transfer.

All monetary values are native GEN wei, expressed as Python integers. No ERC-20 or cross-chain asset support is claimed. Individual liabilities fit `u256`; lifetime deposited and withdrawn totals are decimal strings in storage and integers in views, permitting turnover beyond `u256`.

## Write API

| Method | Authorization and behavior |
| --- | --- |
| `deposit()` | Payable. Reconciles unaccounted native balance into immutable owner credit. Any intentional third-party deposit benefits that owner. Returns newly credited amount. |
| `reconcile_deposits()` | Nonpayable, permissionless. Requires all finalized emission acknowledgements. Same balance reconciliation, including retained value from failed calls. Idempotent without new receipts. |
| `create_escrow(reference, payee, terms_url, terms_sha256, principal, delivery_period, review_period, bond_bps, response_period, adjudication_period, fallback_payee_bps)` | Funding owner only. Locks principal from credit, snapshots terms and creates `FUNDED`. |
| `accept_engagement(escrow_id)` | Payee only, once, before delivery deadline. Explicitly accepts the recorded engagement and fallback policy. |
| `claim_delivery(escrow_id, evidence_url, evidence_sha256)` | Accepted payee only, `FUNDED`, before delivery deadline. Snapshots delivery and starts review. |
| `accept_delivery(escrow_id)` | Payer only, `DELIVERED`. Awards full principal to payee. |
| `dispute(escrow_id, evidence_url, evidence_sha256, bond)` | Payer only, `DELIVERED`, before review deadline. Requires exact bond argument and sufficient prepaid credit. Snapshots dispute and locks bond. |
| `submit_evidence(escrow_id, evidence_url, evidence_sha256)` | Either party, `DISPUTED`, before evidence cutoff and before that party declares readiness. Appends authenticated-party evidence. |
| `finish_evidence(escrow_id)` | Either party during response window. When both finish, evidence closes early. |
| `adjudicate(escrow_id)` | Permissionless, `DISPUTED`, after evidence closes and before resolution deadline. Runs independent assessment; settles only a conclusive result. Returns assessment. |
| `resolve_expired_dispute(escrow_id)` | Permissionless, `DISPUTED`, at or after resolution deadline. Applies mutually accepted fallback and returns bond to payer. |
| `release_expired(escrow_id)` | Permissionless, `DELIVERED`, at or after review deadline. Full principal to payee. |
| `refund_undelivered(escrow_id)` | Permissionless, `FUNDED`, at or after delivery deadline. Full principal to payer. |
| `reject_escrow(escrow_id)` | Payee only, `FUNDED`. Full principal to payer. |
| `offer_settlement(escrow_id, payee_bps)` | Either party in any open state. Matching current offers settle; bond returns to payer. |
| `cancel_offer(escrow_id)` | Either party in any open state. Cancels only caller's offer. |
| `acknowledge_withdrawal(owner, reference)` | Only an authenticated self-message emitted at withdrawal parent finality. Marks emission finalized and clears its reservation. External callers cannot acknowledge. |
| `withdraw(amount, recipient, recipient_kind, reference)` | Credit owner. Spends positive available credit, records owner-scoped reference and emits finalized transfer. Kind is `account` or `contract`. Contract kind requires a successful recipient preflight view. Returns an `EMITTED` record. |

The contract has 18 write methods and six views. Periods must be integers from 1 through 31536000 seconds. `bond_bps` must be 1000 through 10000. Principal is positive and principal plus required bond must fit `u256`. Payer, payee and book cannot be the same address.

`reference` is 1 through 128 characters without surrounding whitespace. Withdrawal references are 1 through 128 characters and unique per owner. A reference cannot be reused after settlement or withdrawal.

## Time boundaries

Deadlines use the deterministic transaction timestamp in seconds, not the keeper's local clock.

- Delivery claims require `now < delivery_deadline`; undelivered refunds require `now >= delivery_deadline`.
- Disputes require `now < review_deadline`; automatic releases require `now >= review_deadline`.
- Supplements and readiness require `now < evidence_deadline` and evidence not already closed.
- Adjudication requires both readiness flags or `now >= evidence_deadline`, and `now < resolution_deadline`.
- Fallback requires `now >= resolution_deadline`.

`evidence_deadline = dispute_time + response_period`.
`resolution_deadline = evidence_deadline + adjudication_period`.

Evidence closes permanently after the first committed adjudication attempt, including an inconclusive result. A rejected consensus attempt commits no such change. Repeated inconclusive assessments can be retried before the deadline with the same committed record; bilateral agreement and fallback remain available.

## Evidence bounds

Each document must be 1 through 32768 bytes of nonempty UTF-8 text without NUL. Terms are capped at 16384 bytes. Each party has an independent 32768-byte budget: terms, dispute and payer supplements share the payer allowance; delivery and payee rebuttals share the payee allowance. This reserves at least 16384 bytes for a payer dispute and prevents either party from consuming the opponent's evidence capacity. A case can hold at most 65536 bytes total. Each party may add three supplements. Duplicate document hashes from the same submitter are rejected as supplements.

URLs have a 2048-character limit. Contract syntax requires HTTPS, a DNS hostname with an alphabetic suffix, and no explicit port, IP literal, userinfo, fragment or local hostname suffix. SDK fetching additionally checks all DNS answers for global routability, pins the selected address at connection time, verifies TLS against the original hostname and validates each redirect. GenVM's network sandbox remains responsible for validator-side DNS and redirect isolation; contract syntax alone cannot provide a network firewall.

The digest is 64 lowercase hexadecimal SHA-256 characters without `0x`. Hashes cover exact raw response bytes, including line endings. Each stored document includes role, URL, hash, text and the actual submitting address.

## Settlement arithmetic

```text
bond_required = (principal * bond_bps + 9999) // 10000
principal_to_payee = principal * payee_bps // 10000
principal_to_payer = principal - principal_to_payee
payee_credit = principal_to_payee + (bond_paid if payer_bad_faith else 0)
payer_credit = principal_to_payer + (0 if payer_bad_faith else bond_paid)
```

Model output shares are multiples of 100 basis points. Bilateral and fallback shares may use any integer basis point. Bad faith requires independently agreed conclusive full delivery. It is never inferred merely from an unsuccessful dispute, a timeout or a bilateral agreement.

The exact consensus tuple is `(conclusive, payee_bps, payer_bad_faith)`. Different payout-driving tuples cannot validate against one another. The prose reason and source observations do not drive settlement or future adjudication.

A zero share produces `REFUNDED`; a positive share produces `SETTLED`. These statuses describe the recorded allocation, including partial awards. Every settlement asserts `payer_credit + payee_credit == principal + bond_paid`.

## Views

| View | Return |
| --- | --- |
| `get_escrow(id)` | Complete record, committed evidence, readiness, deadlines, last assessment, offers and final credits |
| `find_escrow(payer, reference)` | ID for this book's payer and reference, or empty string |
| `credit_of(owner)` | Current withdrawable credit |
| `get_withdrawal(owner, reference)` | Stored withdrawal record (`EMITTED` or `EMISSION_FINALIZED`), or revert for an unknown reference |
| `get_accounting()` | Escrow count, locked principal/bonds, credits, lifetime totals, native/accounted balances, unreconciled deposits, solvency and conservation |
| `get_config()` | Version, funding owner, asset, limits, deposit/evidence policies and absence of administrator |

Accounting invariants:

```text
total_deposited = locked_principal + locked_bonds + withdrawal_credits + total_withdrawn
native_balance >= locked_principal + locked_bonds + withdrawal_credits
unreconciled_deposits = native_balance - accounted_balance
```

Native balance can temporarily exceed liabilities before reconciliation. While a withdrawal remains provisional, the apparent excess can include reserved outgoing value. Reconciliation waits for authenticated finalized self-acknowledgements and rejects that condition instead of crediting it. Native balance can also lag a provisional nonfinal withdrawal while its finalized transfer is pending. Assess native conservation after finality and completed emissions, as the live tests do.

## Payout inbox

Deploy `PayoutInbox(owner, escrow_account)` separately for each beneficiary/book pair. It has no administrator or upgrade mechanism.

- `can_receive_escrow(sender, amount)` accepts positive integer amounts for its configured book.
- Payable `receive_escrow()` accepts calls from that book. It deliberately does not maintain a fragile callback credit counter.
- `get_config()` returns owner, book, actual native balance, outgoing reservation and custody policy.
- `acknowledge_withdrawal()` accepts only the inbox's own finalized self-message, clearing its outgoing reservation.
- `withdraw_to_account(amount, recipient)` lets only the owner emit a native transfer within its actual balance.

Native receipts belong to the inbox owner even if an unexpected sender's callback fails. Serialize inbox withdrawals through finality and actual transfer delivery. A preflight view is not a guarantee that arbitrary recipient code will later execute; the SDK supports only the exact published inbox source and matching configuration.
