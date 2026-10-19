"""Signed SDK bindings with decision-aware polling, appeals and payout tracking."""
import base64
import hashlib
from dataclasses import dataclass
import json
import time
from uuid import uuid4

from genlayer_py.types import TransactionHashVariant
from genlayer_py.abi import calldata
from web3 import Web3

from .evidence import Document
from .receivers import PAYOUT_INBOX_SOURCE_SHA256

_STATUS = {'0': 'UNINITIALIZED', '1': 'PENDING', '2': 'PROPOSING', '3': 'COMMITTING',
           '4': 'REVEALING', '5': 'ACCEPTED', '6': 'UNDETERMINED', '7': 'FINALIZED',
           '8': 'CANCELED', '9': 'APPEAL_REVEALING', '10': 'APPEAL_COMMITTING',
           '11': 'READY_TO_FINALIZE', '12': 'VALIDATORS_TIMEOUT', '13': 'LEADER_TIMEOUT'}
_REJECTED = {'UNDETERMINED', 'CANCELED', 'VALIDATORS_TIMEOUT', 'LEADER_TIMEOUT'}


def transaction_status(receipt: dict) -> str:
    value = receipt.get('status')
    if isinstance(value, bool):
        return 'UNKNOWN'
    raw = str(getattr(value, 'value', value)).upper()
    status = _STATUS.get(raw, raw if raw in _STATUS.values() else 'UNKNOWN')
    named = receipt.get('status_name')
    if named is not None and str(getattr(named, 'value', named)).upper() != status:
        return 'UNKNOWN'
    return status


def consensus_accepted(receipt: dict) -> bool:
    if transaction_status(receipt) not in ('ACCEPTED', 'FINALIZED'):
        return False
    result = receipt.get('result')
    if isinstance(result, bool) or str(getattr(result, 'value', result)).upper() not in ('6', 'MAJORITY_AGREE'):
        return False
    named = receipt.get('result_name')
    return named is None or str(getattr(named, 'value', named)).upper() == 'MAJORITY_AGREE'


def _leader(receipt):
    rows = (receipt.get('consensus_data') or {}).get('leader_receipt') or []
    return rows[0] if isinstance(rows, list) and rows else rows if isinstance(rows, dict) else {}


def execution_succeeded(receipt: dict) -> bool:
    """An accepted decision and a returning execution are both required, including at finality."""
    if not consensus_accepted(receipt):
        return False
    result = receipt.get('tx_execution_result')
    if result is not None:
        return not isinstance(result, bool) and str(getattr(result, 'value', result)).upper() in (
            '1', 'FINISHED_WITH_RETURN')
    return str(_leader(receipt).get('execution_result', '')).upper() == 'SUCCESS'


def return_value(receipt):
    result = _leader(receipt).get('result') or {}
    if not isinstance(result, dict):
        raise ValueError('Receipt does not contain decoded return data')
    payload = result.get('payload')
    if isinstance(payload, dict) and isinstance(payload.get('raw'), list):
        return calldata.decode(bytes(payload['raw']))
    if isinstance(payload, dict) and isinstance(payload.get('readable'), str):
        return json.loads(payload['readable'])
    if isinstance(result.get('raw'), str):
        raw = base64.b64decode(result['raw'], validate=True)
        if not raw or raw[0] != 0:
            raise ValueError('Receipt is not a returning execution')
        return calldata.decode(raw[1:])
    raise ValueError('Receipt does not contain return data')


def payment_result(receipt):
    """Decode legacy v1 payment acknowledgments for receipt inspection only."""
    try:
        value = return_value(receipt)
    except (ValueError, TypeError, IndexError):
        return None
    if isinstance(value, dict) and type(value.get('accepted')) is bool and value.get('method') in ('create_escrow', 'dispute'):
        return value
    return None


class ExecutionFailed(RuntimeError):
    def __init__(self, receipt):
        self.receipt = receipt
        super().__init__(f'GenLayer operation did not succeed: status={transaction_status(receipt)}, decision={receipt.get("result_name", receipt.get("result"))}')


class PaymentRejected(RuntimeError):
    """Legacy v1 payment result. Version 2 allocates prepaid credit in nonpayable calls."""
    def __init__(self, receipt, result):
        super().__init__(result['error'])
        self.receipt, self.result, self.refund_credit = receipt, result, result['refund_credit']


class PollingTimeout(TimeoutError):
    def __init__(self, transaction_id, receipt):
        self.transaction_id, self.receipt = transaction_id, receipt
        super().__init__(f'Transaction {transaction_id} has not reached the requested outcome; resume polling this same ID')


class RecipientExecutionFailed(RuntimeError):
    def __init__(self, parent_receipt, child_receipt):
        self.parent_receipt, self.child_receipt = parent_receipt, child_receipt
        super().__init__('Payout recipient did not execute successfully; inspect its native balance and recovery interface before retrying')


@dataclass(frozen=True)
class AppealTicket:
    transaction_id: str
    submission_id: str
    escrow_id: str
    previous_round: int
    previous_appeal_seconds: float


class EscrowClient:
    """One immutable payer per deployment. Writes return IDs and never retry submission."""
    def __init__(self, client, address: str):
        self.client, self.address = client, Web3.to_checksum_address(address)

    def _read(self, method, args=None, *, finalized=True):
        return self.client.read_contract(address=self.address, function_name=method, args=args or [],
            transaction_hash_variant=TransactionHashVariant.LATEST_FINAL if finalized else TransactionHashVariant.LATEST_NONFINAL)

    def _write(self, method, args=None, value=0):
        return self.client.write_contract(address=self.address, function_name=method, args=args or [], value=value, leader_only=False)

    def wait(self, transaction_id, *, finalized=True, retries=120, interval=6000):
        last = {}
        for attempt in range(retries):
            last = self.client.get_transaction(transaction_hash=transaction_id)
            if last:
                status = transaction_status(last)
                if status == 'FINALIZED' or status == 'CANCELED' or not finalized and status in (_REJECTED | {'ACCEPTED'}):
                    if not execution_succeeded(last):
                        raise ExecutionFailed(last)
                    return last
            if attempt + 1 < retries:
                time.sleep(interval / 1000)
        raise PollingTimeout(transaction_id, last)

    def deposit(self, amount: int):
        if type(amount) is not int or amount <= 0:
            raise ValueError('Deposit must be a positive integer in wei')
        owner = self.get_config()['funding_owner']
        if self.client.local_account.address.lower() != owner.lower():
            raise ValueError('This deposit would benefit a different funding owner')
        return self._write('deposit', value=amount)

    def reconcile_deposits(self):
        return self._write('reconcile_deposits')

    def create(self, reference: str, payee: str, terms: Document, principal: int,
               delivery_period: int = 604800, review_period: int = 86400, bond_bps: int = 1000,
               *, response_period: int = 86400, adjudication_period: int = 604800,
               fallback_payee_bps: int):
        if type(principal) is not int or principal <= 0:
            raise ValueError('Principal must be a positive integer in wei')
        return self._write('create_escrow', [reference, payee, terms.url, terms.sha256, principal,
            delivery_period, review_period, bond_bps, response_period, adjudication_period, fallback_payee_bps])

    def accept_engagement(self, escrow_id):
        return self._write('accept_engagement', [escrow_id])

    def claim_delivery(self, escrow_id, document):
        return self._write('claim_delivery', [escrow_id, document.url, document.sha256])

    def dispute(self, escrow_id, document, *, bond: int):
        if type(bond) is not int or bond <= 0:
            raise ValueError('Bond must be the exact positive bond_required amount in wei')
        return self._write('dispute', [escrow_id, document.url, document.sha256, bond])

    def submit_evidence(self, escrow_id, document):
        return self._write('submit_evidence', [escrow_id, document.url, document.sha256])

    def finish_evidence(self, escrow_id):
        return self._write('finish_evidence', [escrow_id])

    def accept_delivery(self, escrow_id):
        return self._write('accept_delivery', [escrow_id])

    def adjudicate(self, escrow_id):
        return self._write('adjudicate', [escrow_id])

    def resolve_expired_dispute(self, escrow_id):
        return self._write('resolve_expired_dispute', [escrow_id])

    def release_expired(self, escrow_id):
        return self._write('release_expired', [escrow_id])

    def refund_undelivered(self, escrow_id):
        return self._write('refund_undelivered', [escrow_id])

    def reject_escrow(self, escrow_id):
        return self._write('reject_escrow', [escrow_id])

    def offer_settlement(self, escrow_id, payee_bps):
        return self._write('offer_settlement', [escrow_id, payee_bps])

    def cancel_offer(self, escrow_id):
        return self._write('cancel_offer', [escrow_id])

    def qualify_inbox(self, recipient: str) -> dict:
        encoded = self.client.provider.make_request('gen_getContractCode', [recipient])['result']
        if not isinstance(encoded, str) or hashlib.sha256(base64.b64decode(encoded, validate=True)).hexdigest() != PAYOUT_INBOX_SOURCE_SHA256:
            raise ValueError('Contract withdrawals require the published recoverable PayoutInbox source')
        config = self.client.read_contract(address=recipient, function_name='get_config', args=[],
            transaction_hash_variant=TransactionHashVariant.LATEST_FINAL)
        if config['escrow_account'].lower() != self.address.lower() or config['owner'].lower() != self.client.local_account.address.lower() or config['custody'] != 'native-balance':
            raise ValueError('Payout inbox owner or escrow account does not match this withdrawal')
        return config

    def withdraw(self, amount, recipient, *, recipient_kind='account', reference=None):
        if recipient_kind == 'contract':
            self.qualify_inbox(recipient)
        return self._write('withdraw', [amount, recipient, recipient_kind, reference or uuid4().hex])

    def wait_withdrawal(self, transaction_id, *, recipient: str, amount: int, before_balance: int,
                        retries=120, interval=6000):
        parent = self.wait(transaction_id, retries=retries, interval=interval)
        record = return_value(parent)
        if not isinstance(record, dict) or record.get('state') != 'EMITTED' or record.get('amount') != amount or str(record.get('recipient', '')).lower() != recipient.lower():
            raise ValueError('Transaction return data does not match the expected withdrawal')
        for attempt in range(retries):
            children = self.client.get_triggered_transaction_ids(transaction_hash=transaction_id)
            matched = []
            for child in children:
                try:
                    result = self.wait(child, retries=retries, interval=interval)
                except ExecutionFailed as error:
                    raise RecipientExecutionFailed(parent, error.receipt) from error
                destination = result.get('to_address') or result.get('recipient') or result.get('contract_address')
                if str(destination).lower() == recipient.lower() and int(result.get('value') or 0) == amount:
                    matched.append(child)
            balance = self.client.get_balance(recipient)
            if record['recipient_kind'] == 'contract' and matched:
                return {'parent': parent, 'children': matched, 'recipient_balance': balance}
            if record['recipient_kind'] == 'account' and balance >= before_balance + amount:
                return {'parent': parent, 'children': children, 'recipient_balance': balance}
            if attempt + 1 < retries:
                time.sleep(interval / 1000)
        raise PollingTimeout(transaction_id, parent)

    @staticmethod
    def _round_count(receipt):
        history = receipt.get('consensus_history') or {}
        rounds = history.get('consensus_results') or []
        return max(int(receipt.get('num_of_rounds') or 0), len(rounds))

    def appeal(self, escrow_id: str, transaction_id: str, *, value: int = 0) -> AppealTicket:
        previous = self.client.get_transaction(transaction_hash=transaction_id)
        if transaction_status(previous) not in ('ACCEPTED', 'UNDETERMINED', 'VALIDATORS_TIMEOUT', 'LEADER_TIMEOUT'):
            raise ValueError('Transaction is not in an appealable decided state')
        # The pinned Studio SDK returns the original transaction ID for submitAppeal.
        # Persist the returned submission ID and original ID before polling again.
        submission = self.client.appeal_transaction(transaction_id=transaction_id, value=value)
        return AppealTicket(transaction_id, submission, escrow_id, self._round_count(previous),
                            float(previous.get('appeal_processing_time') or 0))

    def poll_appeal(self, ticket: AppealTicket) -> dict:
        if ticket.submission_id != ticket.transaction_id:
            submitted = self.client.w3.eth.get_transaction_receipt(ticket.submission_id)
            if submitted is None:
                return {'state': 'APPEAL_PENDING', 'ticket': ticket}
            if int(submitted['status']) != 1:
                raise ExecutionFailed(dict(submitted))
        receipt = self.client.get_transaction(transaction_hash=ticket.transaction_id)
        status = transaction_status(receipt)
        observed = (self._round_count(receipt) > ticket.previous_round or
                    float(receipt.get('appeal_processing_time') or 0) > ticket.previous_appeal_seconds or
                    status.startswith('APPEAL_') or bool(receipt.get('appealed')))
        if status != 'FINALIZED':
            return {'state': 'APPEAL_PENDING', 'appeal_observed': observed, 'receipt': receipt}
        # Always refresh finalized contract storage. A cached pre-appeal ruling is unsafe.
        record = self.get_escrow(ticket.escrow_id, finalized=True)
        return {'state': record['status'] if observed else 'APPEAL_NOT_OBSERVED',
                'appeal_observed': observed, 'transaction_succeeded': execution_succeeded(receipt),
                'receipt': receipt, 'escrow': record}

    def wait_appeal(self, ticket: AppealTicket, *, retries=120, interval=6000) -> dict:
        last = {}
        observed = False
        for attempt in range(retries):
            last = self.poll_appeal(ticket)
            observed = observed or last.get('appeal_observed', False)
            if last['state'] != 'APPEAL_PENDING':
                if observed and last['state'] == 'APPEAL_NOT_OBSERVED':
                    last['state'] = last['escrow']['status']
                    last['appeal_observed'] = True
                return last
            if attempt + 1 < retries:
                time.sleep(interval / 1000)
        raise PollingTimeout(ticket.transaction_id, last.get('receipt', {}))

    def get_escrow(self, escrow_id, *, finalized=True):
        return self._read('get_escrow', [escrow_id], finalized=finalized)

    def find_escrow(self, payer, reference, *, finalized=True):
        return self._read('find_escrow', [payer, reference], finalized=finalized)

    def credit_of(self, owner, *, finalized=True):
        return self._read('credit_of', [owner], finalized=finalized)

    def get_accounting(self, *, finalized=True):
        return self._read('get_accounting', finalized=finalized)

    def get_config(self, *, finalized=True):
        return self._read('get_config', finalized=finalized)

    def get_withdrawal(self, owner, reference, *, finalized=True):
        return self._read('get_withdrawal', [owner, reference], finalized=finalized)
