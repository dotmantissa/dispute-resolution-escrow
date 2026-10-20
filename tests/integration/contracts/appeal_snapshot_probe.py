# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }
"""Fundless protocol regression: replay against the original pre-execution state.

A controlled public origin changes from 1 to 2 after initial acceptance. An appeal
must reject the old observation, restore the prior state and execute again with 2.
The once-only condition detects replay against post-execution storage. This test
fixture accepts no native funds and is not an escrow implementation.
"""
from genlayer import *


class AppealSnapshotProbe(gl.Contract):
    owner: Address
    origin: str
    observation: u256

    def __init__(self, origin: str):
        self.owner = gl.message.sender_address
        self.origin = origin
        self.observation = u256(0)

    @gl.public.write
    def observe(self) -> int:
        if gl.message.sender_address != self.owner or int(self.observation) != 0:
            raise gl.vm.UserError("Observation requires owner and pre-execution zero state")
        origin = str(self.origin)

        def fetch():
            response = gl.nondet.web.get(origin)
            if response.status != 200 or response.body not in (b"1\n", b"2\n"):
                raise gl.vm.UserError("Unexpected controlled origin response")
            return int(response.body.decode("utf-8").strip())

        value = gl.eq_principle.strict_eq(fetch)
        self.observation = u256(value)
        return value

    @gl.public.view
    def get_observation(self) -> int:
        return int(self.observation)
