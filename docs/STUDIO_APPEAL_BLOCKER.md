# Studio appeal integrity blocker

Release qualification is blocked. The appealed escrow book no longer returns deployed source, while its native balance remains present. Do not fund this qualification address or treat its historical finalized case view as proof that it can execute a payout.

## Observed on the live network

- Network: Studio, `https://studio.genlayer.com/api`.
- Book: `0x2A738Fb0EA7F055f5691B8c9d8a364D7d03F332F`.
- Expected source SHA-256: `ea4af6e7c194a176e33031a65ff7f2357e5c8854156209144a684bdb7dea1951`.
- Appealed adjudication: `0x366f02f6997b56543e227cf131434b16968879e6ec60c78c440f9670acc53138`, case 14.
- Subsequent withdrawal: `0xab4b7ae8044e45ff3f30b540569da63969b78e4408bb8a4d3f061cb18db38413`.
- Retained native balance: 300033 faucet test wei. The diagnostic calls submit no further value.

The adjudication history contains an initial successful accepted execution, a successful validator appeal, and a later accepted execution error. Its round count increased from one to three. Both the final appealed execution and the subsequent withdrawal report `invalid_contract absent_runner_comment`.

Afterward, `gen_getContractCode` returns `Contract not deployed` for the appealed book. Two control books still return the exact expected source: `0x8bFe262CE35375b557F60aE28497B42F1552780a` and `0xA1c104eFB714D45F951E2bA55b8Cb9B78896eA65`. The payout inbox also returns its expected source. These observations distinguish this incident from a network-wide reset.

The old SDK followed the stored appeal ID and refreshed finalized case storage, but that view still reported `SETTLED`. It correctly reported the appealed execution as unsuccessful. The source loss shows why those two checks were insufficient to establish a usable post-appeal settlement.

## SDK correction

`AppealTicket` now includes the source SHA-256 retrieved before submission. Final appeal polling checks the currently deployed source against that commitment before returning a refreshed case. Missing, empty, malformed or changed source raises `ContractIntegrityError`. Its receipt and expected/observed digests remain available for diagnosis. Deposit preflight also requires retrievable deployed source before reading configuration or submitting value. No automatic payment retry or replacement deposit follows an integrity error.

The new checks prevent a misleading settled result. They cannot recreate missing contract code, restore an authoritative pre-execution snapshot, or release native funds from an unexecutable account.

Diagnostic evidence is recorded in [studio-appeal-integrity-failure.json](../artifacts/studio-appeal-integrity-failure.json). The original transaction journal remains in [studio-verification.json](../artifacts/studio-verification.json), with completion withheld.

## Upstream investigation

The official Studio source has a matching failure path. In `process_validator_appeal`, a successful appeal restores the transaction's prior accepted state. When the transaction has no contract snapshot, that path selects an empty dictionary. `update_contract_state` replaces the accepted state with the supplied dictionary. Code extraction reads the code slot from accepted state.

Sources: [appeal processing](https://github.com/genlayerlabs/genlayer-studio/blob/main/backend/consensus/base.py), [state replacement](https://github.com/genlayerlabs/genlayer-studio/blob/main/backend/database_handler/contract_processor.py), and [code extraction](https://github.com/genlayerlabs/genlayer-studio/blob/main/backend/database_handler/contract_snapshot.py).

This path is consistent with the live observations. The hosted deployment's database snapshots and exact server revision are unavailable, so the specific server-side cause remains an inference. A server-side fix must preserve or hydrate the authoritative pre-execution snapshot and refuse a destructive empty-state restoration when that snapshot is unavailable.

Further inspection of official commit `c94072951e483510329670aa427fba3fa6944f45` identifies a concrete omission before that restoration path. `claim_next_appeal` includes neither `transactions.contract_snapshot` in SQL `RETURNING` nor `contract_snapshot` in its returned dictionary. `process_appeal` constructs `Transaction` directly from that dictionary. `Transaction.from_dict` reads the missing key through `input.get("contract_snapshot")`, producing `None`. The successful validator-appeal branch then selects empty accepted state for restoration. This is a reproducible source-level defect in that revision, rather than evidence that the hosted deployment runs the same revision.

Revision-pinned sources: [worker claim](https://github.com/genlayerlabs/genlayer-studio/blob/c94072951e483510329670aa427fba3fa6944f45/backend/consensus/worker.py#L344), [worker conversion](https://github.com/genlayerlabs/genlayer-studio/blob/c94072951e483510329670aa427fba3fa6944f45/backend/consensus/worker.py#L1776), [domain conversion](https://github.com/genlayerlabs/genlayer-studio/blob/c94072951e483510329670aa427fba3fa6944f45/backend/domain/types.py#L287), and [destructive restoration](https://github.com/genlayerlabs/genlayer-studio/blob/c94072951e483510329670aa427fba3fa6944f45/backend/consensus/base.py#L1195).

The upstream correction must carry the saved snapshot through the worker claim and independently reject absent, malformed or wrong-account snapshots before resetting newer transactions or replacing accepted state. For an existing contract call, its prior snapshot must contain deployed code. A deployment appeal has different prior-state semantics and needs separate coverage. Merely loading current accepted state after execution would not recover the transaction's pre-execution state.

Studio also provides a deployer-signed code replacement path. It replaces code while preserving other slots, so it may help recover this test account. It cannot reconstruct erased ledger slots or correct the appeal worker. That host privilege is documented in [security boundaries](SECURITY.md#studio-code-replacement).

## Required release gate

Studio operators must diagnose and repair the affected account and appeal restoration behavior. Then repeat a successful appeal, verify unchanged deployed source, refresh the resulting ruling, execute actual payouts, and verify zero residual liabilities and native balance. A fresh deployment alone does not establish that another appeal is safe. Publication as a completed primitive remains withheld until this gate passes.

## Reviewer note

This revision cannot be accepted as fully qualified on Studio. A real successful validator appeal was followed by loss of retrievable contract source while native funds remained in the account, and a subsequent withdrawal failed. The SDK previously returned a historical finalized `SETTLED` case despite the failed appealed execution and missing executable source. The SDK now rejects that state, but custody safety still depends on correcting and requalifying Studio's appeal restoration behavior. Exact payout consensus does not repair this lifecycle failure.
