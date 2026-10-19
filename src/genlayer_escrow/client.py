"""Small typed bindings over the real genlayer-py client, without custody or relaying."""

import base64
from dataclasses import dataclass
import hashlib
import re
import urllib.request

from genlayer_py.types import TransactionHashVariant, TransactionStatus
from genlayer_py.abi import calldata
from web3 import Web3


class ExecutionFailed(RuntimeError):
    """A decided transaction executed unsuccessfully. Inspect its receipt before retrying."""

    def __init__(self, receipt):
        super().__init__("GenLayer contract execution failed; inspect exception.receipt")
        self.receipt = receipt


class PaymentRejected(RuntimeError):
    """The supported payable call rejected its request and credited the incoming value."""

    def __init__(self, receipt, result):
        super().__init__(result["error"])
        self.receipt = receipt
        self.result = result
        self.refund_credit = result["refund_credit"]


def payment_result(receipt: dict):
    rows = (receipt.get("consensus_data") or {}).get("leader_receipt") or []
    leader = rows[0] if isinstance(rows, list) and rows else rows if isinstance(rows, dict) else {}
    result = leader.get("result") or {}
    if not isinstance(result, dict):
        return None
    payload = result.get("payload")
    try:
        if isinstance(payload, dict) and isinstance(payload.get("raw"), list):
            value = calldata.decode(bytes(payload["raw"]))
        elif isinstance(result.get("raw"), str):
            raw = base64.b64decode(result["raw"])
            if not raw or raw[0] != 0:
                return None
            value = calldata.decode(raw[1:])
        else:
            return None
    except (ValueError, TypeError, IndexError):
        return None
    if isinstance(value, dict) and type(value.get("accepted")) is bool and value.get("method") in ("create_escrow", "dispute"):
        return value
    return None


def execution_succeeded(receipt: dict) -> bool:
    """Lifecycle acceptance alone does not prove execution success."""
    consensus = receipt.get("consensus_data") or {}
    leader = consensus.get("leader_receipt") or []
    if isinstance(leader, dict):
        leader = [leader]
    if leader:
        return str(leader[0].get("execution_result", "")).upper() == "SUCCESS"
    # Non-Studio SDK receipts expose the protocol execution result directly.
    result = receipt.get("tx_execution_result")
    return str(result).upper() == "SUCCESS" or type(result) is int and result == 1


@dataclass(frozen=True)
class Document:
    """Public HTTPS location and commitment to its exact raw UTF-8 response bytes."""

    url: str
    sha256: str

    def __post_init__(self):
        if not self.url.startswith("https://") or len(self.url) > 2048:
            raise ValueError("Document URL must use HTTPS and fit within 2048 characters")
        if not re.fullmatch(r"[0-9a-f]{64}", self.sha256):
            raise ValueError("SHA-256 must be 64 lowercase hexadecimal characters")

    @classmethod
    def from_bytes(cls, url: str, content: bytes):
        if not 0 < len(content) <= 32768:
            raise ValueError("Document must contain 1..32768 bytes")
        text = content.decode("utf-8")
        if not text.strip() or "\x00" in text:
            raise ValueError("Document must be nonempty UTF-8 text without NUL")
        return cls(url, hashlib.sha256(content).hexdigest())

    @classmethod
    def fetch(cls, url: str, timeout: int = 30):
        if not url.startswith("https://"):
            raise ValueError("Document URL must use HTTPS")
        request = urllib.request.Request(url, headers={"User-Agent": "genlayer-dispute-escrow/1.0"})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            if response.status != 200 or not response.url.startswith("https://"):
                raise ValueError("Document must return HTTP 200 over HTTPS")
            return cls.from_bytes(url, response.read(32769))


class EscrowClient:
    """Use an existing signed GenLayer client. All write methods return a transaction ID.

    No method silently retries transaction submission. Persist each returned transaction
    ID before waiting. Resolve an uncertain creation using find_escrow(payer, reference).
    Reads default to finalized state; pass finalized=False only for pending UI previews.
    """

    def __init__(self, client, address: str):
        self.client = client
        self.address = Web3.to_checksum_address(address)

    def _read(self, method, args=None, *, finalized=True):
        return self.client.read_contract(
            address=self.address, function_name=method, args=args or [],
            transaction_hash_variant=(TransactionHashVariant.LATEST_FINAL
                                      if finalized else TransactionHashVariant.LATEST_NONFINAL))

    def _write(self, method, args, value=0):
        return self.client.write_contract(address=self.address, function_name=method,
                                          args=args, value=value)

    def wait(self, transaction_id, *, finalized=True, retries=120, interval=6000):
        receipt = self.client.wait_for_transaction_receipt(
            transaction_hash=transaction_id,
            status=TransactionStatus.FINALIZED if finalized else TransactionStatus.ACCEPTED,
            retries=retries, interval=interval)
        if not execution_succeeded(receipt):
            raise ExecutionFailed(receipt)
        outcome = payment_result(receipt)
        if outcome is not None and not outcome["accepted"]:
            raise PaymentRejected(receipt, outcome)
        return receipt

    def create(self, reference: str, payee: str, terms: Document, principal: int,
               delivery_period: int = 604800, review_period: int = 86400, bond_bps: int = 1000):
        if type(principal) is not int or principal <= 0:
            raise ValueError("Principal must be a positive integer in wei")
        return self._write("create_escrow", [reference, payee, terms.url, terms.sha256,
                                            delivery_period, review_period, bond_bps], principal)

    def claim_delivery(self, escrow_id: str, document: Document):
        return self._write("claim_delivery", [escrow_id, document.url, document.sha256])

    def dispute(self, escrow_id: str, document: Document, *, bond: int):
        if type(bond) is not int or bond <= 0:
            raise ValueError("Bond must be the exact positive bond_required amount in wei")
        return self._write("dispute", [escrow_id, document.url, document.sha256], bond)

    def accept_delivery(self, escrow_id: str):
        return self._write("accept_delivery", [escrow_id])

    def adjudicate(self, escrow_id: str):
        return self._write("adjudicate", [escrow_id])

    def release_expired(self, escrow_id: str):
        return self._write("release_expired", [escrow_id])

    def refund_undelivered(self, escrow_id: str):
        return self._write("refund_undelivered", [escrow_id])

    def reject_escrow(self, escrow_id: str):
        return self._write("reject_escrow", [escrow_id])

    def offer_settlement(self, escrow_id: str, payee_bps: int):
        return self._write("offer_settlement", [escrow_id, payee_bps])

    def cancel_offer(self, escrow_id: str):
        return self._write("cancel_offer", [escrow_id])

    def withdraw(self, amount: int, recipient: str, *, recipient_kind: str = "account"):
        return self._write("withdraw", [amount, recipient, recipient_kind])

    def get_escrow(self, escrow_id: str, *, finalized=True):
        return self._read("get_escrow", [escrow_id], finalized=finalized)

    def find_escrow(self, payer: str, reference: str, *, finalized=True):
        return self._read("find_escrow", [payer, reference], finalized=finalized)

    def credit_of(self, owner: str, *, finalized=True):
        return self._read("credit_of", [owner], finalized=finalized)

    def get_accounting(self, *, finalized=True):
        return self._read("get_accounting", finalized=finalized)

    def get_config(self, *, finalized=True):
        return self._read("get_config", finalized=finalized)
