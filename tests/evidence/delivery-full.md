# Escrow operating runbook

## Installation
Run `pip install genlayer-dispute-escrow` in the builder's Python environment.

## Funding
`create_escrow` is payable. Its attached native GEN value is the escrow principal held for the engagement.

## Dispute
The payer calls `dispute` during the review window and attaches exactly the escrow record's `bond_required` amount. A successful call freezes release pending adjudication or bilateral settlement.

## Withdrawal
Settlement creates withdrawal credits. The credit owner calls `withdraw` to send their credit to a selected recipient. Transfers execute on finalization.
