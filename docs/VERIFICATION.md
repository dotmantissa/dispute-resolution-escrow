# Verification record

The deployed contract is `0xA9BAc09D9813c890292Cb862323130D4508E7f30` on GenLayer Studio. Its finalized deployment, source hash and validator votes are in [the deployment manifest](../artifacts/deployment.json). The deployed source matches `contracts/dispute_escrow.py`, SHA-256 `5bfd2f5f39ca81af72f6d2a0162e402382b918a19aab25fedc9b7ec5415ed7e5`.

## Local verification

[The local verification record](../artifacts/local-verification.json) records the tool versions and commands. All 148 cases passed: 118 direct-mode contract cases and 30 client cases. Both the escrow and receiving contract passed GenVM lint. The builder package was built as a wheel, installed into a separate environment and checked through its public API.

The direct suite covers lifecycle authorization, deadline boundaries, integer rounding, conservation, evidence digests, decision parsing, offer cancellation, replay rejection, payable rejection credits and client receipt formats. It uses the actual SDK's storage and calldata codec. Network custody and model consensus are verified separately on Studio.

## Studio verification

[The main transaction journal](../artifacts/studio-verification.json) contains 58 finalized transactions. All 11 collected main-suite cases were validated, including the five parameterized adjudication cases. The run resumed after Studio quota cooldowns and transient transport failures. The timeout and rejection case was reconciled against its existing transactions before continuing; the final two cases passed in a fresh pytest invocation. The journal preserves transaction identities across those continuations.

| Scenario | Verified result |
| --- | --- |
| Deployment and schema | Exact source match, configured limits and 16 public methods; only creation and dispute are payable. |
| Funded creation and acceptance | Native value held by the registry, unauthorized acceptance rejected, full payee credit after payer acceptance. |
| Partial delivery | 50% of principal to the payee, remainder and bond to the payer. |
| No delivery | Full principal and bond returned to the payer. |
| Clearly bad-faith dispute | Full principal and dispute bond credited to the payee. |
| Honest unsuccessful dispute | Full principal to the payee, bond returned to the payer. |
| Embedded prompt injection | Instructions inside evidence did not override the documented promise; full payer refund. |
| Inconclusive evidence | Funds stayed locked; canceled offers did not settle; matching 30% offers settled and returned the bond. |
| Deadlines and rejection | Undelivered escrow refunded, undisputed delivery released, payee rejection refunded. |
| Rejected payable requests | Wrong bond, unauthorized dispute, duplicate reference and wrong digest preserved incoming value as sender-owned credit. The client raised `PaymentRejected` for the finalized rejection result. |
| Native withdrawals | Unauthorized and repeated withdrawals rejected. Account balances increased by the exact credit; a separately deployed intelligent contract received and accounted for its finalized transfer. |

The main run withdrew 59,006 wei to the payee account, 68,029 wei to the receiving contract and 1,001 wei to the outsider account as its rejected-payment refund. Total deposits and withdrawals were both 128,036 wei. Actual registry balance, locked principal, locked bonds and outstanding credits were all zero at completion.

[The source availability journal](../artifacts/source-availability-verification.json) contains six additional finalized transactions. That test published genuine public evidence, committed its hashes and contents, changed the source documents, deleted the origin and confirmed its removal through GitHub. Studio validators then awarded 50% from the original snapshots. Both parties withdrew successfully. Cumulative registry deposits and withdrawals reached 139,038 wei, with zero actual balance and zero remaining liabilities.

Every recorded transaction reached finalization with its expected execution result. Model assessments and validator votes are retained in the reports. These results establish the exercised Studio behavior. They do not establish that model judgments are infallible or that an incompatible recipient can receive a transfer. See [the security considerations](SECURITY.md) for those integration boundaries.
