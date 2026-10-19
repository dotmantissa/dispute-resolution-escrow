# Escrow operating runbook

## Installation
Run `pip install -e .` in the builder's Python environment.

## Funding
The payer first calls payable `deposit`. Then nonpayable `create_escrow` locks the principal from that payer's prepaid credit.

## Dispute
The payer calls nonpayable `dispute` during the review window with exactly the escrow record's `bond_required` argument, locking that amount from prepaid credit. A successful call freezes release pending adjudication or bilateral settlement.

## Withdrawal
Settlement creates withdrawal credits. The credit owner calls `withdraw` to send their credit to a selected recipient. Transfers execute on finalization.
