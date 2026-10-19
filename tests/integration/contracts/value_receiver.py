# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }
"""Real payable IC recipient used to verify finalized escrow withdrawals."""
from genlayer import *


class ValueReceiver(gl.Contract):
    received: u256

    def __init__(self):
        self.received = u256(0)

    @gl.public.write.payable
    def receive_escrow(self) -> None:
        self.received = u256(int(self.received) + int(gl.message.value))

    @gl.public.view
    def get_received(self) -> int:
        return int(self.received)

    @gl.public.view
    def get_balance(self) -> int:
        return int(self.balance)
