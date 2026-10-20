# Security and operating assumptions

Current Studio qualification is blocked by [source loss after a successful appeal](STUDIO_APPEAL_BLOCKER.md). Native custody and reconciliation require executable contract source. Ownership rules cannot reconstruct a ledger erased by the hosted network. The SDK checks source before deposits and binds source integrity across appeals. Code restoration and complete ledger recovery are separate operations; neither establishes that another appeal is safe.

## Exact economic agreement

Validators independently assess the original terms and committed evidence. They must exactly match the tuple that controls settlement: conclusiveness, earned basis points and bad faith. No tolerance can admit a different payout bucket. Integer arithmetic conserves principal and bond, including rounding. The exhaustive direct test compares all 103 valid economic states against one another, covering 10609 ordered pairs.

The leader's prose explanation is not binding case law. Explanations and fetch observations never enter a later case or determine money. Their wording is not claimed to have exact multi-validator agreement.

## Native custody

Studio can retain attached value after rejected execution or consensus. Prepaid custody addresses that behavior structurally: only deterministic deposits receive value, and every receipt belongs to one immutable owner. Evidence calls lock existing credit without receiving new value. Permissionless reconciliation credits only that owner after protecting all existing liabilities.

Never send a different payer's funds to someone else's book expecting sender-specific recovery. A direct gift or malformed funded call benefits the configured owner. There is no administrator sweep or receipt oracle. Confirm ownership in the SDK before funding.

Native transfers execute asynchronously. The contract rejects reconciliation while authenticated finalized self-acknowledgements remain pending. Finalize earlier withdrawals before reconciling or funding further activity. Follow both parent and child outcomes. Book withdrawal references prevent replay of a previously emitted withdrawal; a failed arbitrary recipient is not an automatic refund to the book.

The guard depends on the network debiting outgoing value before executing finalized self-messages. The recorded Studio guard test checks provisional rejection and post-acknowledgement accounting. Repeat that qualification before adopting another network or runtime; a self-message alone is not an independent balance-debit proof.

The supported inbox uses actual native balance as its recovery authority. Only its owner can withdraw. The SDK verifies exact source plus owner/book configuration. A custom receiver may falsely accept preflight, reject its callback or offer no recovery interface; raw low-level integrations assume that risk. Do not mix unrelated beneficiaries in one inbox.

## Documentary truth and confidentiality

Hashes establish byte integrity, not truth, legal identity, physical receipt or authorship of third-party statements. A transaction authenticates the submitting address. It does not authenticate opponent quotations, a purported signature pasted into text, an attachment's origin or private delivery. Applications requiring those facts must provide independently verifiable evidence and explain how it relates to the original promise.

Terms, evidence URLs, snapshots and rulings are public. Private documents, customer secrets, credentials and unredacted personal information should not be submitted. The contract does not retrieve authenticated content or use an application server's private assertions as an oracle.

The prompt treats evidence as untrusted data, rejects instructions embedded in it, limits bad faith to affirmative evidence of knowing abuse, and refuses to count repetition as corroboration. These controls reduce manipulation; they cannot prove that an LLM never makes a factual or interpretive mistake. GenLayer consensus and appeals remain the adjudication trust mechanism.

## Source availability and network isolation

Creation commits exact nonempty UTF-8 bytes through strict equality. Later assessment independently re-fetches every URL, verifies the digest, and uses a reverified stored snapshot when an origin changes or fails. A page that disappears before its first snapshot cannot be admitted. The source-availability tests separately change and delete the actual public URLs and observe validator requests at the origin.

The SDK rejects private DNS answers, explicit ports, numeric address tricks, local names and unsafe redirects, pins a public address per connection and verifies TLS/SNI against the original hostname. It does not consult proxy environment variables. Contract URL syntax matches the structural policy, but validator-side DNS resolution and redirects are delegated to GenVM's networking sandbox. A regex does not replace that sandbox.

Bodies and accumulated case data are bounded. A page larger than 32768 bytes, invalid UTF-8, whitespace-only content, NUL or a digest mismatch is rejected. The public fixture corpus is revision-pinned and independently hashed.

## Dispute liveness and consent

The payee explicitly accepts the engagement before claiming delivery. Each party gets a response opportunity; one cannot close it early alone. Supplements are bounded to three per party. Independent 32768-byte party allowances prevent either side from exhausting the opponent's capacity. The 16384-byte terms cap reserves space for the payer's initial dispute. Total case evidence is bounded to 65536 bytes. Both parties may declare readiness, or the response period expires.

Model consensus can fail or remain inconclusive. Matching bilateral offers provide a voluntary exit. After a fixed deadline, anyone can apply the fallback split explicitly recorded at creation and accepted by the payee. The fallback is a negotiated risk allocation and may differ from what a panel would have awarded. Applications must display it before acceptance rather than describing it as a guaranteed fair judicial result.

The bond floor is 10% and its actual rate is visible before acceptance. A bond deters abuse only to the extent that its cost exceeds the expected benefit of a bad-faith dispute. The contract cannot guarantee the economics of every external marketplace.

## Client and protocol boundaries

A successful leader is insufficient evidence of consensus. The SDK requires authoritative majority agreement, accepted/finalized lifecycle and successful execution. Unknown, contradictory, rejected or timed-out receipts fail closed. Default waits require finality; provisional reads and previews are explicitly marked.

Protocol appeals are separate from an additional contract-level court or administrator. The SDK persists appeal IDs, polls the original transaction, observes round progression and refreshes finalized case storage. An upheld appeal need not change the award. No application should promise that every appeal succeeds or changes a ruling.

Studio is a hosted development network with faucet balances, rate limits and asynchronous processing. Its tests establish behavior on that network and pinned runtime, not production economic security on every future network version. A new network or runner requires repeat qualification. Private signing keys and publication credentials never belong in the repository or transaction journals.

## Studio code replacement

The contract exposes no administrator, sweep or upgrade method. This does not remove privileges provided by its host. Studio's public source implements `sim_upgradeContractCode`, authorized on hosted deployments by an administrator key or a signature from the original deployer. The signature binds the address, contract transaction count and replacement source hash. The worker directly replaces the code slot in accepted and finalized storage without running GenVM consensus or consulting the contract's upgrader list.

Consequently, immutable ownership and owner-only inbox withdrawals describe the deployed contract's behavior while that source remains installed. They are not guarantees against a Studio administrator or deployer replacing that source. Preserve control of the deployment key, verify source commitments and requalify these privileges on another network. A deployer signature is not an administrative capability that this package gives to an unrelated builder.

Replacing a missing code slot does not restore the rest of accepted storage. A recovery must preserve authoritative liabilities, obtain agreement where a failed appeal leaves a disputed ruling, and verify actual payouts. Code availability alone cannot clear the current release gate.

Source: [Studio authorization and replacement worker at the inspected revision](https://github.com/genlayerlabs/genlayer-studio/blob/c94072951e483510329670aa427fba3fa6944f45/backend/consensus/worker.py#L1540), [endpoint authorization](https://github.com/genlayerlabs/genlayer-studio/blob/c94072951e483510329670aa427fba3fa6944f45/backend/protocol_rpc/endpoints.py#L769).
