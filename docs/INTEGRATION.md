# Builder integration guide

## Choose the agreement before accepting funds

Publish the original promise as a public UTF-8 document. It should identify the purchased deliverables, acceptance criteria, delivery method, exclusions and the relative value of separately payable milestones. If the transaction concerns a physical item or private work, provide independently checkable evidence; unsupported opposing statements can remain inconclusive.

The contract records one terms document at creation. It does not merge later private messages, fetch linked attachments or infer a new agreement from a party's demands. Put the relevant material directly in the committed text. Provide a digest of the exact raw response. Both parties should compare the on-chain snapshot with their agreement before work begins.

Choose a delivery period and a review period between one second and one year. The short minimum supports machine-driven integrations and testing, but a human marketplace should provide enough time for payment confirmation, delivery inspection, network delays and dispute submission. The payer chooses a bond rate between 1 and 10000 basis points. A marketplace that wants substantial deterrence should require its own minimum rate when presenting or accepting an engagement.

## Sign as the correct party

Each party uses its own account. The binding never holds keys or acts as a relay.

```python
import os
from genlayer_py import create_account, create_client
from genlayer_py.chains import studionet
from genlayer_escrow import EscrowClient

payer_client = create_client(
    chain=studionet,
    account=create_account(os.environ['PAYER_PRIVATE_KEY']),
)
payee_client = create_client(
    chain=studionet,
    account=create_account(os.environ['PAYEE_PRIVATE_KEY']),
)
address = os.environ['ESCROW_ADDRESS']
payer = EscrowClient(payer_client, address)
payee = EscrowClient(payee_client, address)
```

A contract acting as a party must initiate the message itself. The primitive checks the immediate sender, so a user's signature does not authorize a different intermediary contract automatically.

## Create a funded engagement

```python
from genlayer_escrow import Document

terms = Document.fetch(os.environ['TERMS_URL'])
reference = 'service-order-1842'
tx_id = payer.create(
    reference=reference,
    payee=payee_client.local_account.address,
    terms=terms,
    principal=10**18,
    delivery_period=604800,
    review_period=86400,
    bond_bps=1000,
)
# Save tx_id and reference durably in the application's own database now.
payer.wait(tx_id)
escrow_id = payer.find_escrow(payer_client.local_account.address, reference)
record = payer.get_escrow(escrow_id)
assert record['principal'] == 10**18
assert record['bond_required'] == 10**17
```

`Document.fetch` verifies that the off-chain response is bounded UTF-8 text and computes its digest. The contract then independently fetches and verifies the same bytes across validators. A changed document causes submission to fail. A caller that already has the exact published bytes can use `Document.from_bytes(url, content)` instead.

A timeout while waiting does not establish that submission failed. Follow the stored transaction ID first. After creation, use the payer-scoped reference lookup to recover the record. Do not replace an uncertain reference with a new reference and pay twice. After an actual execution failure, inspect the receipt and network value-refund behavior before resubmitting.

## Submit delivery

```python
delivery = Document.fetch(os.environ['DELIVERY_EVIDENCE_URL'])
tx_id = payee.claim_delivery(escrow_id, delivery)
payee.wait(tx_id)
record = payer.get_escrow(escrow_id)
assert record['status'] == 'DELIVERED'
review_deadline = record['review_deadline']
```

Delivery can be claimed once, strictly before the delivery deadline. It freezes the delivery evidence and opens the review clock. The payer can call `accept_delivery` to allocate the full principal immediately. If no dispute is submitted in time, anyone can call `release_expired` at or after the review deadline. An indexer or application must submit timeout actions; the contract does not wake itself up.

## Raise and resolve a dispute

```python
dispute_evidence = Document.fetch(os.environ['DISPUTE_EVIDENCE_URL'])
record = payer.get_escrow(escrow_id)
tx_id = payer.dispute(
    escrow_id,
    dispute_evidence,
    bond=record['bond_required'],
)
payer.wait(tx_id)
tx_id = payer.adjudicate(escrow_id)
payer.wait(tx_id)
record = payer.get_escrow(escrow_id)
assessment = record['last_assessment']
```

Only the payer may submit the dispute, and the transaction must attach the exact required bond before the review deadline. Adjudication is permissionless and does not require another deposit into the escrow. The submitting account remains responsible for any network fees.

If the assessment is conclusive, `payee_credit`, `payer_credit`, `payee_bps`, `payer_bad_faith` and `settlement_reason` show the allocation. The bond returns to the payer unless validators establish clear bad faith. If the result is inconclusive, the record remains `DISPUTED`, and no credits are created. The parties can retry adjudication or negotiate a split.

The escrow bond is independent of GenLayer's protocol appeal bonds. To challenge the validator result, follow the network's transaction appeal rules and track finality. The application should link to the adjudication transaction and its consensus receipts rather than presenting a local model preview as authoritative.

## Negotiate a split

```python
# Both approve 60% of principal for the payee; any bond returns to payer.
tx_id = payer.offer_settlement(escrow_id, 6000)
payer.wait(tx_id)
tx_id = payee.offer_settlement(escrow_id, 6000)
payee.wait(tx_id)
```

Offers settle only when both current offers match. Either party can replace or cancel its own offer while the escrow remains open. Delivery and dispute transitions clear previous offers. A builder should show the latest offer and escrow state before requesting consent. Settlement cannot be repeated after either terminal state.

## Withdraw

```python
credit = payee.credit_of(payee_client.local_account.address)
if credit:
    tx_id = payee.withdraw(
        credit,
        payee_client.local_account.address,
        recipient_kind='account',
    )
    payee.wait(tx_id)
```

Credits accumulate across escrows. Partial withdrawals are supported. Only the credit owner may spend them, although the owner may choose a different destination. Recipient kind `account` uses a native transfer through GenVM's EVM recipient interface. A rejecting EVM contract is not a safe substitute for an EOA.

For an Intelligent Contract recipient, pass `recipient_kind='contract'`. The receiver must implement `@gl.public.write.payable def receive_escrow(self) -> None`. The real receiver used in network verification is in [tests/integration/contracts/value_receiver.py](../tests/integration/contracts/value_receiver.py). It records `gl.message.value` and exposes its native balance. A production receiver should also check its expected sender and account for the incoming funds under its own application rules.

The outgoing value is held by an asynchronous finalized message. A finalized withdrawal parent does not by itself prove a child recipient successfully executed. Follow the triggered transaction IDs and verify the receiving state or EOA balance. Failed child execution may permanently lose the value; the primitive does not credit it back automatically.

## Use the contract directly from another IC

Read the schema in `artifacts/schema.json` for parameter types and payable flags. Calls from another Intelligent Contract use the standard SDK:

```python
registry = gl.get_contract_at(Address(registry_address))
registry.emit(value=u256(principal), on='finalized').create_escrow(
    reference, payee_address, terms_url, terms_sha256,
    delivery_period, review_period, bond_bps,
)
```

The asynchronous create call has no synchronous return value. Once it finalizes, the calling contract's address is the payer:

```python
registry = gl.get_contract_at(Address(registry_address))
escrow_id = registry.view().find_escrow(gl.message.contract_address.as_hex, reference)
record = registry.view().get_escrow(escrow_id)
```

Keep settlement authority in the calling contract's own access control. A generic public forwarding function would let any user act as that contract's payer or payee. For incoming withdrawals, implement the payable receiver method described above. Use finalized messages for custody transitions and follow child execution rather than assuming that emission means success.

## Application state and transaction receipts

The Python binding defaults its views to `latest-final`. Use `finalized=False` only for pending UI previews. Its write methods return a transaction ID without retrying submission. `wait()` requests finalization, checks actual execution success and raises `ExecutionFailed` with the receipt attached if execution failed. You can request an accepted preview with `wait(tx_id, finalized=False)`, but it remains appealable.

The core SDK and RPC remain available for inspection, appeal submission and fee handling. This binding targets the pinned SDK and tested Studio deployment. Before using it on a fee-charging network, qualify that network's current transaction fee API, balances, native transfer behavior and receipt semantics.

A useful application journal records the escrow reference, contract address, chain, operation, transaction ID, expected value, lifecycle status and execution result. Evidence documents and escrow records are public, so do not place credentials, personal secrets or private keys in them.
