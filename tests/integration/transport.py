"""Real RPC transport with bounded retries for explicit server throttling only.

A timeout or connection failure is propagated, never silently resubmitted. An
explicit rate-limit rejection can safely retry the identical request after the
server's advertised cooldown. This transport does not replace RPC responses.
"""
import time

import requests
from genlayer_py.provider import GenLayerProvider
from genlayer_py.exceptions import GenLayerError


class StudioProvider(GenLayerProvider):
    def make_request(self, method, params):
        deadline=time.monotonic()+3700
        while True:
            response=requests.post(self.url,
                json={"jsonrpc":"2.0","id":int(time.time()*1000),"method":method,"params":params},
                headers={"Content-Type":"application/json","User-Agent":"genlayer-escrow-verification"},
                timeout=90)
            result=response.json()
            error=result.get("error") or {}
            if response.status_code==429 or error.get("code") in (-32029,-32429):
                data=error.get("data") or {}
                delay=int(data.get("retry_after_seconds") or response.headers.get("retry-after") or 60)+2
                if time.monotonic()+delay>deadline:
                    raise GenLayerError("Studio RPC throttle exceeded the bounded recovery window")
                print(f"Studio rejected {method} due to rate limits; retrying identical request in {delay}s",flush=True)
                stop=time.monotonic()+delay
                while time.monotonic()<stop:
                    time.sleep(min(60,max(0,stop-time.monotonic())))
                continue
            self._raise_on_error(result,method)
            return result


def attach_transport(client):
    provider=StudioProvider(client.provider.url)
    client.provider=provider
    client.w3.provider=provider
    return client
