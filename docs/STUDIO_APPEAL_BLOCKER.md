# Studio appeal integrity blocker

Release qualification remains blocked. The affected account is now retired, its controlled test funds have been recovered, and its installed code is a recovery fixture. The source-loss observations below describe the incident before that exit. Do not fund the retired address or describe recovery as a repaired appeal lifecycle.

## Observed on the live network

- Network: Studio, `https://studio.genlayer.com/api`.
- Book: `0x2A738Fb0EA7F055f5691B8c9d8a364D7d03F332F`.
- Expected source SHA-256: `ea4af6e7c194a176e33031a65ff7f2357e5c8854156209144a684bdb7dea1951`.
- Appealed adjudication: `0x366f02f6997b56543e227cf131434b16968879e6ec60c78c440f9670acc53138`, case 14.
- Subsequent withdrawal: `0xab4b7ae8044e45ff3f30b540569da63969b78e4408bb8a4d3f061cb18db38413`.
- Incident balance: 300033 faucet test wei. Those funds were subsequently recovered through the bilateral exit below; the current balance is zero.

The adjudication history contains an initial successful accepted execution, a successful validator appeal, and a later accepted execution error. Its round count increased from one to three. Both the final appealed execution and the subsequent withdrawal report `invalid_contract absent_runner_comment`.

Afterward, `gen_getContractCode` returns `Contract not deployed` for the appealed book. Two control books still return the exact expected source: `0x8bFe262CE35375b557F60aE28497B42F1552780a` and `0xA1c104eFB714D45F951E2bA55b8Cb9B78896eA65`. The payout inbox also returns its expected source. These observations distinguish this incident from a network-wide reset.

The old SDK followed the stored appeal ID and refreshed finalized case storage, but that view still reported `SETTLED`. It correctly reported the appealed execution as unsuccessful. The source loss shows why those two checks were insufficient to establish a usable post-appeal settlement.

## SDK correction

`AppealTicket` now includes the source SHA-256 retrieved before submission. Final appeal polling checks the currently deployed source against that commitment before returning a refreshed case. Missing, empty, malformed or changed source raises `ContractIntegrityError`. Its receipt and expected/observed digests remain available for diagnosis. Deposit preflight requires an exact match to the published escrow source hash before reading configuration or submitting value. Nonempty replacement code is insufficient. No automatic payment retry or replacement deposit follows an integrity error.

The new checks prevent a misleading settled result. They cannot recreate missing contract code, restore an authoritative pre-execution snapshot, or release native funds from an unexecutable account.

Diagnostic evidence is recorded in [studio-appeal-integrity-failure.json](../artifacts/studio-appeal-integrity-failure.json). The original transaction journal remains in [studio-verification.json](../artifacts/studio-verification.json), with completion withheld.

## Upstream investigation

The official Studio source has a matching failure path. In `process_validator_appeal`, a successful appeal restores the transaction's prior accepted state. When the transaction has no contract snapshot, that path selects an empty dictionary. `update_contract_state` replaces the accepted state with the supplied dictionary. Code extraction reads the code slot from accepted state.

Sources: [appeal processing](https://github.com/genlayerlabs/genlayer-studio/blob/main/backend/consensus/base.py), [state replacement](https://github.com/genlayerlabs/genlayer-studio/blob/main/backend/database_handler/contract_processor.py), and [code extraction](https://github.com/genlayerlabs/genlayer-studio/blob/main/backend/database_handler/contract_snapshot.py).

This path is consistent with the live observations. The hosted deployment's database snapshots and exact server revision are unavailable, so the specific server-side cause remains an inference. A server-side fix must preserve or hydrate the authoritative pre-execution snapshot and refuse a destructive empty-state restoration when that snapshot is unavailable.

Further inspection of official commit `c94072951e483510329670aa427fba3fa6944f45` identifies a concrete omission before that restoration path. `claim_next_appeal` includes neither `transactions.contract_snapshot` in SQL `RETURNING` nor `contract_snapshot` in its returned dictionary. `process_appeal` constructs `Transaction` directly from that dictionary. `Transaction.from_dict` reads the missing key through `input.get("contract_snapshot")`, producing `None`. The successful validator-appeal branch then selects empty accepted state for restoration. This is a reproducible source-level defect in that revision, rather than evidence that the hosted deployment runs the same revision.

The [source-path diagnostic record](../artifacts/studio-upstream-appeal-diagnosis.json) records the exact file digests and five static checks. A candidate upstream patch has only passed Python syntax checks; it is neither runtime-qualified nor applied to the hosted service.

Revision-pinned sources: [worker claim](https://github.com/genlayerlabs/genlayer-studio/blob/c94072951e483510329670aa427fba3fa6944f45/backend/consensus/worker.py#L344), [worker conversion](https://github.com/genlayerlabs/genlayer-studio/blob/c94072951e483510329670aa427fba3fa6944f45/backend/consensus/worker.py#L1776), [domain conversion](https://github.com/genlayerlabs/genlayer-studio/blob/c94072951e483510329670aa427fba3fa6944f45/backend/domain/types.py#L287), and [destructive restoration](https://github.com/genlayerlabs/genlayer-studio/blob/c94072951e483510329670aa427fba3fa6944f45/backend/consensus/base.py#L1195).

The upstream correction must carry the saved snapshot through the worker claim and independently reject absent, malformed or wrong-account snapshots before resetting newer transactions or replacing accepted state. For an existing contract call, its prior snapshot must contain deployed code. A deployment appeal has different prior-state semantics and needs separate coverage. Merely loading current accepted state after execution would not recover the transaction's pre-execution state.

Studio also provides a deployer-signed code replacement path. It replaces code while preserving other slots, so it may help recover this test account. It cannot reconstruct erased ledger slots or correct the appeal worker. That host privilege is documented in [security boundaries](SECURITY.md#studio-code-replacement).

## Completed custody exit

The deployer-signed replacement mechanism was first qualified on empty control `0xA1c104eFB714D45F951E2bA55b8Cb9B78896eA65`. Transaction `0xb83fa6c78aacf83d3abb7cc78666bb1a1c2d40b307c361499a3f0e1fcc9ca592` finalized, retained the exact source, and preserved accepted and finalized accounting.

Before changing the damaged account, a [complete finalized ledger snapshot](../artifacts/studio-finalized-ledger-before-recovery.json) captured all fourteen terminal cases, the earlier one-wei withdrawal and both credit balances. Locked principal, locked bonds and pending withdrawals were zero. The two balances summed to the native balance: 232695 for the payer and 67338 for the payee.

An account-specific [recovery fixture](../tests/integration/contracts/qualification_custody_exit.py) binds that snapshot and exact allocation. Both controlled test keys authorized the same plan in separate finalized transactions. This is a bilateral agreement to exit the test account, not an authoritative replacement for the failed appeal ruling. The fixture passed GenVM lint and seven direct authorization, balance and replay checks before installation.

- Recovery code installation: `0x17bb6725844f58fa6ad98d122e9ba386fd962437c53ea8ca2147a5fb2c3e5d8a`.
- Payer authorization: `0xa020112973f2e3646f1bbc191161b05a14091f4b9df737c30f4f23b709fc7ea4`.
- Payee authorization: `0x293991322d3d87b550ffb403dc13d80c6ab87374ac2b349e99454380b2a8858d`.
- Payout emission: `0x88676a37e8b8ecc4dedbaa3decfdadf9abd51b46159535b6b285513652b686e9`.
- Payer native transfer: `0x910d8dea51e08033f853017dfff78c7747d519d8fd9d64e310e7a733200d9c79`, 232695 wei.
- Payee native transfer: `0x478f6679f972d0a795277d541db13668ee259da9b47841bd76104b80ea7976c5`, 67338 wei.

Both native children finalized with `value_credited=true`; exact beneficiary balance increases and zero ending book balance were verified. Together with the original one-wei withdrawal, native outflows equal all 300034 deposited test wei. The [recovery report](../artifacts/studio-custody-recovery.json) records these checks.

The retired account now contains recovery source SHA-256 `2541dd99ba503c0e5a5582b5dc792b86aaa021a10fd2399a5b6dcc1929f416e3`. It is not a production escrow endpoint and must never be funded again. Historical ledger liabilities must not be restored as unpaid balances after this completed asset exit. The current SDK refuses a deposit to this replacement source before submitting value.

## Fresh fundless reproduction

A later [standalone probe](../artifacts/appeal-snapshot-probe.json) reproduced source loss on a new account that never held native value. Its [contract](../tests/integration/contracts/appeal_snapshot_probe.py) records a controlled public HTTP observation once. After initial acceptance with value 1, the origin changes to 2 and remains stable for the appeal. Correct behavior requires restoring the original pre-execution state, rejecting the old observation, executing again with 2 and retaining identical source.

- Probe account: `0xCF8cCC825a6Cda684B38e09402982cd12E158eCA`.
- Deployment: `0xd500eb0fbe36c4fc6a489b1db8e7ba9651a5d446afcfc2f1a8eeea545d0ff106`.
- Appealed observation: `0xa8bae8d50e5433eb8a953f0d13046dc528f6906743c45ba4530292838cdd0342`.
- Observed result: three rounds, finalized execution failure, `gen_getContractCode` reporting `Contract not deployed`, native balance zero.

The live test failed its source-preservation assertion in 113.64 seconds. That failure is an unresolved release gate, not a passing negative fixture. Its controlled origin and anonymous tunnel were shut down. No model-generated adjudication, escrow allocation or native deposit is involved in this reproduction. The exact hosted server revision remains unverified; the current service behavior is independently observed.

To requalify after an operator fix, inspect and archive the old probe journal, set `GENLAYER_APPEAL_PROBE=1` with the normal external signing key, and run:

```sh
python -m pytest tests/integration/test_appeal_snapshot.py -v -s
```

Do not reuse the paid, retired escrow account for that qualification. A passing fundless probe is a prerequisite to repeating the complete matching-source escrow appeal and payout lifecycle.

## Required release gate

Studio operators must repair and qualify appeal snapshot restoration. Then qualify a fresh matching-source escrow deployment through a successful appeal, unchanged source, refreshed ruling and actual payouts, with zero residual liabilities and native balance. The affected account has already been retired and paid out; it must not be revived as unpaid escrow. A fresh deployment alone does not establish that another appeal is safe. Publication as a completed primitive remains withheld until this gate passes.

## Reviewer note

This revision cannot be accepted as fully qualified on Studio. A real successful validator appeal was followed by loss of retrievable contract source while native funds remained in the account, and a subsequent withdrawal failed. Both controlled test parties subsequently authorized recovery of all funds and retirement of the damaged account. The SDK previously returned a historical finalized `SETTLED` case despite the failed appealed execution and missing executable source. The SDK now rejects missing or changed source, including nonempty replacement source before funding. Studio also exposes deployer/admin code replacement outside the primitive API. Recovery does not establish appeal safety; the hosted restoration path still requires correction and full qualification. Exact payout consensus does not repair this lifecycle failure.
