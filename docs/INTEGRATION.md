# Builder integration

## Deploy a payer's book

Install the package from the repository as described in the README. Keep signing keys in your application's secret manager or environment, outside Git. The contract accepts EOA or Intelligent Contract payer addresses.

```python
import os
from pathlib import Path
from genlayer_py import create_account, create_client
from genlayer_py.chains import studionet
from genlayer_escrow import EscrowClient

account = create_account(os.environ['GENLAYER_PRIVATE_KEY'])
chain = create_client(chain=studionet, account=account)
source = Path('contracts/dispute_escrow.py').read_bytes()
tx_id = chain.deploy_contract(code=source, args=[account.address], leader_only=False)
# Persist tx_id before polling. Resume this ID after an interruption.
receipt = EscrowClient(chain, account.address).wait(tx_id)
book_address = receipt.get('contract_address') or receipt['to_address']
escrow = EscrowClient(chain, book_address)
assert escrow.get_config()['funding_owner'].lower() == account.address.lower()
```

The constructor sets custody ownership permanently. Every native receipt at that book belongs to that payer. A marketplace must create a book for each payer rather than pool independent payers in one deployment. Payee credits are tracked separately within each book.

For an IC payer, deploy with the IC's address, fund the book intentionally, and have that IC emit the nonpayable creation, dispute and payer actions. Authorization uses the immediate contract caller. The real `PartyAccount` integration fixture demonstrates this flow, including owner-restricted forwarding. An EOA controlling that IC cannot call payer methods directly on its behalf.

## Fund and commit an engagement

Fetch the terms through the hardened SDK transport. Use exact plain UTF-8 documents with stable public HTTPS URLs. The payee must be able to inspect the terms, all periods and the fallback allocation before accepting.

```python
from genlayer_escrow import Document

terms = Document.fetch(os.environ['ESCROW_TERMS_URL'])
principal = 10_000
bond_rate = 1000
bond = (principal * bond_rate + 9999) // 10000

# Value enters only through this deterministic deposit operation.
deposit_id = escrow.deposit(principal + bond)
escrow.wait(deposit_id)

create_id = escrow.create(
    reference=os.environ['ESCROW_REFERENCE'],
    payee=os.environ['ESCROW_PAYEE_ADDRESS'],
    terms=terms,
    principal=principal,
    delivery_period=7 * 86400,
    review_period=86400,
    bond_bps=bond_rate,
    response_period=86400,
    adjudication_period=7 * 86400,
    fallback_payee_bps=5000,
)
escrow.wait(create_id)
escrow_id = escrow.find_escrow(account.address, os.environ['ESCROW_REFERENCE'])
record = escrow.get_escrow(escrow_id)
assert record['principal'] == principal
```

The 5000-basis-point fallback in this example is an explicit 50% deadline allocation, not a prediction about a future ruling. Select a split appropriate to the actual engagement and display it clearly to both parties.

`deposit` refuses a locally signed deposit for a different funding owner. Lower-level direct gifts remain permitted by the contract and benefit its configured owner. A failed deposit on Studio may retain value before state commits. Inspect `get_accounting()['unreconciled_deposits']`, then call nonpayable `reconcile_deposits` after pending withdrawals finalize. That operation always credits the configured owner, never its caller.

## Payee acceptance and delivery

Use a separate signed client for each party. All reads default to finalized state.

```python
payee_chain = create_client(
    chain=studionet,
    account=create_account(os.environ['GENLAYER_PAYEE_PRIVATE_KEY']),
)
payee = EscrowClient(payee_chain, book_address)
payee.wait(payee.accept_engagement(escrow_id))
delivery = Document.fetch(os.environ['ESCROW_DELIVERY_URL'])
payee.wait(payee.claim_delivery(escrow_id, delivery))
```

The payer can accept delivery with `escrow.wait(escrow.accept_delivery(escrow_id))`. If delivery is not claimed before its deadline, anyone can call `refund_undelivered`. Once the review period expires without a dispute, anyone can call `release_expired`. Applications should run a permissionless keeper for these actions and the dispute fallback. Contract timestamps and eligibility checks remain authoritative.

## Dispute and response

```python
record = escrow.get_escrow(escrow_id)
dispute_evidence = Document.fetch(os.environ['ESCROW_DISPUTE_URL'])
escrow.wait(escrow.dispute(
    escrow_id, dispute_evidence, bond=record['bond_required'],
))

rebuttal = Document.fetch(os.environ['ESCROW_PAYEE_REBUTTAL_URL'])
payee.wait(payee.submit_evidence(escrow_id, rebuttal))

# Both parties independently choose when their own submissions are complete.
escrow.wait(escrow.finish_evidence(escrow_id))
payee.wait(payee.finish_evidence(escrow_id))
judgment_id = escrow.adjudicate(escrow_id)
# Persist judgment_id, then choose finality or appeal handling below.
```

A dispute requires sufficient existing credit. Its bond is an argument, not attached value. Applications can top up through `deposit` beforehand. The minimum bond rate is 10% of principal, rounded up to the next wei.

The response window closes at its deadline or when both parties finish. Each party may submit three supplements before declaring readiness, within its independent 32768-byte evidence allowance. Terms are capped at 16384 bytes to reserve payer dispute space. Record authorship is authenticated by the transaction sender. Opponent quotes, signatures asserted in text and external claims are not authenticated just because a party submits them.

An inconclusive judgment leaves the case `DISPUTED`. Before the resolution deadline, the same committed case can be reassessed. Matching `offer_settlement` calls from the two parties settle an agreed split; `cancel_offer` cancels only the caller's proposal. At or after the resolution deadline, `resolve_expired_dispute` applies the previously accepted fallback and returns the bond. A keeper may submit any eligible permissionless action.

## Durable polling and protocol appeals

The default `wait` requires finality, majority agreement and successful VM execution. `finalized=False` returns a provisional accepted result that an appeal can change. Never release an off-chain asset based on that preview. Lifecycle names alone do not prove success.

For ordinary settlement, call `escrow.wait(judgment_id)` and then refresh with `escrow.get_escrow(escrow_id)`. To appeal, use the following path while the judgment is still provisional. A transaction that has already finalized cannot be appealed.

```python
import json
from dataclasses import asdict
from pathlib import Path
from genlayer_escrow import AppealTicket, PollingTimeout, ExecutionFailed

# Only decided transactions still within the protocol's appeal opportunity qualify.
escrow.wait(judgment_id, finalized=False)
ticket = escrow.appeal(escrow_id, judgment_id)
Path('appeal-ticket.json').write_text(json.dumps(asdict(ticket)))

# A new process can resume without submitting another appeal.
stored = AppealTicket(**json.loads(Path('appeal-ticket.json').read_text()))
outcome = escrow.wait_appeal(stored)
assert outcome['state'] != 'APPEAL_PENDING'
record = outcome['escrow']
```

The ticket stores the original intelligent transaction ID, appeal submission ID, case ID, prior round markers and pre-appeal source hash. On Studio, the pinned SDK returns the original ID for appeal submission. Polling follows that ID through appeal processing, verifies unchanged deployed source, and refreshes the case from finalized contract storage. It does not reuse a cached pre-appeal ruling. `APPEAL_NOT_OBSERVED` means finality was seen without evidence that the requested appeal ran; do not report it as a completed appeal.

`ContractIntegrityError` means deployed source is missing or differs from the ticket's commitment. Stop funding and inspect the network state. A historical finalized case view can survive loss of executable accepted-state code. See the [live Studio blocker](STUDIO_APPEAL_BLOCKER.md). Tickets created before the source-commitment field require a verified pre-appeal source record; do not invent a commitment from whatever code is present afterward.

Appeals can uphold a ruling, replace it, or leave the case unresolved. `transaction_succeeded` reports the resulting operation independently of the refreshed case status. A `PollingTimeout` retains the same transaction ID and last receipt so callers can resume. `ExecutionFailed` retains the failed receipt. Neither exception authorizes automatic write resubmission.

## Withdraw to an account

Use an owner-scoped idempotency reference and persist the submitted ID before polling.

```python
amount = escrow.credit_of(account.address)
recipient = account.address
before = chain.get_balance(recipient)
withdrawal_id = escrow.withdraw(amount, recipient, reference='invoice-42-final')
# Persist withdrawal_id, amount, recipient and before before continuing.
transfer = escrow.wait_withdrawal(
    withdrawal_id, recipient=recipient, amount=amount, before_balance=before,
)
```

The contract returns `EMITTED` when it has spent credit and scheduled a finalized transfer. This is not a receipt from the recipient. For account transfers, the SDK follows the exact type-0 child from the book, requires finalized status and its authoritative native-credit flag, and checks destination and amount. Native transfers have no validator decision; Intelligent Contract children and acknowledgement messages must independently reach successful consensus. Serialize withdrawal tracking and retain its parameters.

## Withdraw to an Intelligent Contract

Deploy the provided inbox with the credit owner's address and the book address. The SDK requires the exact published source hash and matching owner/book configuration before contract-mode submission.

```python
inbox_id = chain.deploy_contract(
    code=Path('contracts/payout_inbox.py').read_bytes(),
    args=[account.address, book_address],
    leader_only=False,
)
inbox_receipt = escrow.wait(inbox_id)
inbox_address = inbox_receipt.get('contract_address') or inbox_receipt['to_address']
amount = escrow.credit_of(account.address)
before = chain.get_balance(inbox_address)
withdrawal_id = escrow.withdraw(
    amount, inbox_address, recipient_kind='contract', reference='invoice-42-inbox',
)
transfer = escrow.wait_withdrawal(
    withdrawal_id, recipient=inbox_address, amount=amount, before_balance=before,
)
assert transfer['children']
```

The owner can later call `withdraw_to_account(amount, recipient)` on the inbox using its signed chain client. Follow that transfer through finality and actual delivery before issuing another inbox withdrawal. Its recovery uses the native balance, including value retained after a rejected callback.

A preflight view cannot guarantee arbitrary custom receiver execution. The lower-level book supports that interface for advanced integrations, but the default SDK rejects unknown receiver source. `RecipientExecutionFailed` includes both parent and failed child receipts. Do not repeat the parent withdrawal: its credit has already been spent and the recipient may already hold the value. Inspect and recover through the recipient's own custody interface.

## Version 1 migration

Version 2 is a fresh deployment with a breaking API. The earlier published book `0xA9BAc09D9813c890292Cb862323130D4508E7f30` was audited with zero native balance and zero liabilities; no user funds were migrated. Historic transactions remain at that address and in Git history.

Existing applications must deploy a payer-bound v2 book, change payable creation/dispute calls to prepaid nonpayable calls, add explicit payee acceptance, display the deadline fallback, and track finality plus recipient delivery. Do not treat old verification artifacts as evidence for a new source hash or continue funding a superseded address.
