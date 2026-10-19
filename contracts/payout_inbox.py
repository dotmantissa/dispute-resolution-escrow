# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }
"""Recoverable native payout inbox owned by one EOA or Intelligent Contract.

The native balance is authoritative. A failed receive callback cannot erase the
beneficiary's ability to withdraw retained value in a later nonpayable transaction.
Use one inbox per beneficiary and escrow account. No administrator can redirect it.
"""
from genlayer import *
import re


@gl.evm.contract_interface
class _Account:
    class View:
        pass
    class Write:
        pass


def _address(text: str) -> Address:
    if re.fullmatch(r"0x[0-9a-fA-F]{40}", text) is None or int(text[2:], 16) == 0:
        raise gl.vm.UserError("[EXPECTED] Invalid nonzero address")
    return Address(text)


class PayoutInbox(gl.Contract):
    owner: Address
    escrow_account: Address
    total_emitted: str
    withdrawal_pending: bool

    def __init__(self, owner: str, escrow_account: str):
        self.owner = _address(owner)
        self.total_emitted = "0"
        self.withdrawal_pending = False
        self.escrow_account = _address(escrow_account)
        if self.owner == gl.message.contract_address:
            raise gl.vm.UserError("[EXPECTED] Inbox cannot own itself")

    @gl.public.view
    def can_receive_escrow(self, sender: str, amount: int) -> bool:
        return _address(sender) == self.escrow_account and type(amount) is int and amount > 0

    @gl.public.write.payable
    def receive_escrow(self) -> None:
        if gl.message.sender_address != self.escrow_account:
            raise gl.vm.UserError("[EXPECTED] Only configured escrow account")
        # Custody deliberately relies on the native balance, not a callback counter.

    @gl.public.view
    def get_config(self) -> dict:
        return {"version": "2.0.0", "owner": self.owner.as_hex,
                "escrow_account": self.escrow_account.as_hex,
                "custody": "native-balance", "native_balance": int(self.balance),
                "total_emitted": int(self.total_emitted), "withdrawal_pending": self.withdrawal_pending}

    @gl.public.write
    def withdraw_to_account(self, amount: int, recipient: str) -> None:
        if gl.message.sender_address != self.owner:
            raise gl.vm.UserError("[EXPECTED] Only inbox owner")
        destination = _address(recipient)
        if destination == gl.message.contract_address:
            raise gl.vm.UserError("[EXPECTED] Cannot withdraw to this inbox")
        if type(amount) is not int or not 0 < amount <= int(self.balance):
            raise gl.vm.UserError("[EXPECTED] Amount outside native balance")
        if self.withdrawal_pending:
            raise gl.vm.UserError("[EXPECTED] Await finalized inbox withdrawal acknowledgement")
        self.withdrawal_pending = True
        self.total_emitted = str(int(self.total_emitted) + amount)
        _Account(destination).emit_transfer(value=u256(amount))
        gl.get_contract_at(gl.message.contract_address).emit(on="finalized").acknowledge_withdrawal()

    @gl.public.write
    def acknowledge_withdrawal(self) -> None:
        if gl.message.sender_address != gl.message.contract_address:
            raise gl.vm.UserError("[EXPECTED] Only finalized inbox self-message")
        if not self.withdrawal_pending:
            raise gl.vm.UserError("[EXPECTED] No pending inbox withdrawal")
        self.withdrawal_pending = False
