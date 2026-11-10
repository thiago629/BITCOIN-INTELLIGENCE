"""Test fixtures.

Upstream APIs are replaced by an in-memory fake (``FakeUpstream``) plugged in
via ``httpx.MockTransport``. Payloads mirror the real Esplora/mempool.space
formats (trimmed). These fixtures exist only in tests; the application never
serves fabricated data.
"""

from collections.abc import Callable, Iterator
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app

MEMPOOL = "mempool.test"
BLOCKSTREAM = "blockstream.test"

TXID = "a" * 64
COINBASE_TXID = "c" * 64
BLOCK_HASH = "0" * 20 + "b" * 44
ADDR = "bc1qar0srrr7xfkvy5l643lydnw9re59gtzzwf5mdq"
OTHER_ADDR = "1BoatSLRHtKNngkdXEeobR76b53LETtpyT"


def block_payload(height: int, extras: bool = False, hash_: str | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": hash_ or f"{height:064x}",
        "height": height,
        "version": 536870912,
        "timestamp": 1_700_000_000 + height * 600,
        "tx_count": 2000 + height % 100,
        "size": 1_500_000,
        "weight": 3_990_000,
        "merkle_root": "f" * 64,
        "previousblockhash": f"{height - 1:064x}",
        "mediantime": 1_700_000_000 + height * 600 - 3000,
        "nonce": 1,
        "bits": 386000300,
        "difficulty": 1.5e14,
    }
    if extras:
        payload["extras"] = {
            "totalFees": 2_500_000,
            "reward": 315_000_000,
            "medianFee": 2.5,
            "avgFeeRate": 3.0,
        }
    return payload


def tx_payload(confirmed: bool = True) -> dict[str, Any]:
    return {
        "txid": TXID,
        "version": 2,
        "locktime": 0,
        "size": 250,
        "weight": 661,
        "fee": 1_000,
        "vin": [
            {
                "txid": "d" * 64,
                "vout": 1,
                "is_coinbase": False,
                "prevout": {
                    "scriptpubkey_address": ADDR,
                    "scriptpubkey_type": "v0_p2wpkh",
                    "value": 150_000_000,
                },
            }
        ],
        "vout": [
            {
                "scriptpubkey_address": OTHER_ADDR,
                "scriptpubkey_type": "p2pkh",
                "value": 100_000_000,
            },
            {"scriptpubkey_address": ADDR, "scriptpubkey_type": "v0_p2wpkh", "value": 49_999_000},
            {"scriptpubkey_type": "op_return", "value": 0},
        ],
        "status": (
            {
                "confirmed": True,
                "block_height": 800_000,
                "block_hash": BLOCK_HASH,
                "block_time": 1_690_000_000,
            }
            if confirmed
            else {"confirmed": False}
        ),
    }


def coinbase_payload() -> dict[str, Any]:
    return {
        "txid": COINBASE_TXID,
        "version": 1,
        "locktime": 0,
        "size": 200,
        "weight": 800,
        "fee": 0,
        "vin": [{"is_coinbase": True, "prevout": None, "txid": "0" * 64, "vout": 4294967295}],
        "vout": [
            {
                "scriptpubkey_address": OTHER_ADDR,
                "scriptpubkey_type": "p2pkh",
                "value": 5_000_000_000,
            }
        ],
        "status": {
            "confirmed": True,
            "block_height": 0,
            "block_hash": BLOCK_HASH,
            "block_time": 1231006505,
        },
    }


ADDRESS_PAYLOAD = {
    "address": ADDR,
    "chain_stats": {
        "funded_txo_count": 3,
        "funded_txo_sum": 300_000_000,
        "spent_txo_count": 1,
        "spent_txo_sum": 150_000_000,
        "tx_count": 3,
    },
    "mempool_stats": {
        "funded_txo_count": 1,
        "funded_txo_sum": 10_000,
        "spent_txo_count": 0,
        "spent_txo_sum": 0,
        "tx_count": 1,
    },
}

MEMPOOL_PAYLOAD = {
    "count": 1000,
    "vsize": 500_000,
    "total_fee_sat": 0,
    "total_fee": 1_234_567,
    "fee_histogram": [[10.5, 50_000], [5.0, 100_000]],
}

Handler = Callable[[httpx.Request], httpx.Response]


class FakeUpstream:
    """Routes ``(host, path)`` to canned responses and records every call."""

    def __init__(self) -> None:
        self.routes: dict[tuple[str, str], Handler] = {}
        self.calls: list[tuple[str, str]] = []

    def json(self, host: str, path: str, body: Any, status: int = 200) -> None:
        self.routes[(host, path)] = lambda _r: httpx.Response(status, json=body)

    def text(self, host: str, path: str, body: str, status: int = 200) -> None:
        self.routes[(host, path)] = lambda _r: httpx.Response(status, text=body)

    def status(
        self, host: str, path: str, status: int, headers: dict[str, str] | None = None
    ) -> None:
        self.routes[(host, path)] = lambda _r: httpx.Response(status, text="err", headers=headers)

    def handler(self, host: str, path: str, fn: Handler) -> None:
        self.routes[(host, path)] = fn

    def count(self, host: str, path: str) -> int:
        return self.calls.count((host, path))

    def __call__(self, request: httpx.Request) -> httpx.Response:
        key = (request.url.host, request.url.path)
        self.calls.append(key)
        fn = self.routes.get(key)
        if fn is None:
            return httpx.Response(404, text="not found")
        return fn(request)

    @property
    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self)


@pytest.fixture
def upstream() -> FakeUpstream:
    return FakeUpstream()


@pytest.fixture
def settings(tmp_path: Any) -> Settings:
    return Settings(
        database_url=f"sqlite+aiosqlite:///{(tmp_path / 'test.db').as_posix()}",
        mempool_base_url=f"https://{MEMPOOL}/api",
        blockstream_base_url=f"https://{BLOCKSTREAM}/api",
        ingestion_enabled=False,
        http_max_retries=1,
        rate_limit_per_minute=0,
        log_level="WARNING",
    )


@pytest.fixture
def client(settings: Settings, upstream: FakeUpstream) -> Iterator[TestClient]:
    app = create_app(settings, http_transport=upstream.transport)
    with TestClient(app) as c:
        yield c
