"""Real RPC transport with bounded recovery and no ambiguous mutation replay.

Read-only RPCs retry transient transport, gateway and decoding failures. Explicit
rate-limit rejections retry the identical request after the server's cooldown.
All other mutation failures propagate for transaction-journal reconciliation.
"""
import time

import requests
from genlayer_py.provider import GenLayerProvider
from genlayer_py.exceptions import GenLayerError

READ_ONLY={"eth_getTransactionByHash","eth_getTransactionReceipt","eth_getBalance",
    "eth_getTransactionCount","eth_chainId","eth_gasPrice","eth_estimateGas",
    "eth_blockNumber","gen_call","gen_getContractCode","gen_getContractSchema",
    "sim_getConsensusContract"}


class StudioProvider(GenLayerProvider):
    def make_request(self, method, params):
        deadline=time.monotonic()+3700
        while True:
            try:
                response=requests.post(self.url,
                    json={"jsonrpc":"2.0","id":int(time.time()*1000),"method":method,"params":params},
                    headers={"Content-Type":"application/json","User-Agent":"genlayer-escrow-verification"},
                    timeout=(6,90))
                if response.status_code>=500:
                    raise requests.exceptions.HTTPError(f"Studio gateway HTTP {response.status_code}")
                result=response.json()
            except (requests.exceptions.RequestException,ValueError):
                if method not in READ_ONLY or time.monotonic()+10>deadline:
                    raise
                print(f"Transient response failure reading {method}; retrying in 10s",flush=True)
                time.sleep(10)
                continue
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
