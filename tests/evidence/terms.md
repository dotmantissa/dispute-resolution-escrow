# Commission: GenLayer escrow operating runbook

This agreement commissions a written operating runbook for builders integrating a GenLayer escrow registry. The sole deliverable is the written text at the delivery evidence URL. This is a self-contained documentation service, with no software execution or private delivery required.

There are four independently priced sections. Each complete section earns exactly 25% of the principal. Missing sections earn nothing. A section must give the concrete instruction specified below. Quality beyond those instructions is not a separate condition.

1. Installation: give the command `pip install -e .`.
2. Funding: state that the payer calls payable `deposit`, then nonpayable `create_escrow` locks prepaid principal.
3. Dispute: state that the payer calls nonpayable `dispute` during the review window with the exact `bond_required` argument, locking that amount from prepaid credit.
4. Withdrawal: state that settlement creates credits, that the credit owner calls `withdraw`, and that transfers execute on finalization.

No interface, deployment, software package publication, ongoing support, audits, or uptime guarantee is purchased under this agreement. The document itself is the complete evidence of the commissioned written work.
