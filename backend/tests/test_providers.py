import httpx
import pytest

from app.domain.models import FeeMethod
from app.providers.errors import (
    ProviderNotFound,
    ProviderRateLimited,
    ProviderUnavailable,
)
from app.providers.esplora import EsploraProvider
from app.providers.http import ProviderHttpClient
from app.providers.mempool_space import MempoolSpaceProvider
from tests.conftest import (
    ADDR,
    ADDRESS_PAYLOAD,
    BLOCKSTREAM,
    MEMPOOL,
    MEMPOOL_PAYLOAD,
    TXID,
    FakeUpstream,
    block_payload,
    coinbase_payload,
    tx_payload,
)


def make(upstream: FakeUpstream, host: str = BLOCKSTREAM, retries: int = 1) -> ProviderHttpClient:
    client = httpx.AsyncClient(transport=upstream.transport)
    return ProviderHttpClient(client, "p", f"https://{host}/api", retries, backoff_base_s=0)


# ---- parsing ---------------------------------------------------------------


def test_parse_transaction_amounts_and_fee_rate() -> None:
    tx = EsploraProvider.parse_tx(tx_payload())
    assert tx.vsize == 166  # ceil(661 / 4)
    assert tx.fee_rate == round(1000 / 166, 2)
    assert tx.total_input_sat == 150_000_000
    assert tx.total_output_sat == 149_999_000
    assert tx.total_input_sat - tx.total_output_sat == tx.fee_sat
    assert tx.outputs[2].address is None  # OP_RETURN has no address
    assert tx.status.confirmed and tx.status.block_height == 800_000


def test_parse_coinbase_has_unknown_input_total() -> None:
    tx = EsploraProvider.parse_tx(coinbase_payload())
    assert tx.inputs[0].is_coinbase
    assert tx.inputs[0].prev_txid is None
    assert tx.total_input_sat is None  # newly minted, not "zero"


def test_parse_address_balance() -> None:
    info = EsploraProvider.parse_address(ADDRESS_PAYLOAD)
    assert info.confirmed_balance_sat == 150_000_000
    assert info.unconfirmed_delta_sat == 10_000


def test_address_tx_net_effect() -> None:
    atx = EsploraProvider.parse_address_tx(ADDR, tx_payload())
    assert atx.sent_sat == 150_000_000
    assert atx.received_sat == 49_999_000
    assert atx.net_sat == -100_001_000


def test_mempool_block_extras() -> None:
    block = MempoolSpaceProvider.parse_block_with_extras(block_payload(10, extras=True))
    assert block.total_fees_sat == 2_500_000
    assert block.median_fee_rate == 2.5
    plain = EsploraProvider.parse_block(block_payload(10))
    assert plain.total_fees_sat is None  # unknown, never defaulted to 0


async def test_esplora_fee_estimates_derived_from_targets(upstream: FakeUpstream) -> None:
    upstream.json(
        BLOCKSTREAM, "/api/fee-estimates", {"1": 20.0, "3": 10.0, "6": 5.0, "144": 2.0, "1008": 1.0}
    )
    fees = await EsploraProvider(make(upstream), "blockstream", "b").get_fee_estimates()
    assert (fees.fastest, fees.half_hour, fees.hour, fees.economy, fees.minimum) == (
        20,
        10,
        5,
        2,
        1,
    )
    assert fees.method == FeeMethod.TARGET_ESTIMATES


async def test_mempool_stats_and_difficulty(upstream: FakeUpstream) -> None:
    upstream.json(MEMPOOL, "/api/mempool", MEMPOOL_PAYLOAD)
    upstream.json(
        MEMPOOL,
        "/api/v1/difficulty-adjustment",
        {
            "progressPercent": 50.0,
            "difficultyChange": -2.5,
            "estimatedRetargetDate": 1_800_000_000_000,
            "remainingBlocks": 1000,
            "nextRetargetHeight": 977_000,
            "previousRetarget": 1.2,
        },
    )
    p = MempoolSpaceProvider(make(upstream, MEMPOOL), "mempool", "m")
    stats = await p.get_mempool_stats()
    assert stats.total_fee_sat == 1_234_567 and stats.fee_histogram[0] == (10.5, 50_000)
    diff = await p.get_difficulty_adjustment()
    assert diff.estimated_retarget_date.year == 2027  # ms -> s conversion
    assert diff.difficulty_change_percent == -2.5


async def test_malformed_payload_is_provider_unavailable(upstream: FakeUpstream) -> None:
    upstream.json(BLOCKSTREAM, f"/api/tx/{TXID}", {"unexpected": True})
    with pytest.raises(ProviderUnavailable, match="unexpected response format"):
        await EsploraProvider(make(upstream), "blockstream", "b").get_transaction(TXID)


# ---- HTTP error classification ------------------------------------------------


async def test_http_404_and_400_are_not_found(upstream: FakeUpstream) -> None:
    upstream.status(BLOCKSTREAM, "/api/x", 400)
    with pytest.raises(ProviderNotFound):
        await make(upstream).get_json("/x")
    with pytest.raises(ProviderNotFound):
        await make(upstream).get_json("/missing")


async def test_http_429_is_rate_limited_with_retry_after(upstream: FakeUpstream) -> None:
    upstream.status(BLOCKSTREAM, "/api/x", 429, {"Retry-After": "12"})
    with pytest.raises(ProviderRateLimited) as exc:
        await make(upstream).get_json("/x")
    assert exc.value.retry_after_s == 12
    assert upstream.count(BLOCKSTREAM, "/api/x") == 1  # no hammering after 429


async def test_http_5xx_is_retried_then_unavailable(upstream: FakeUpstream) -> None:
    upstream.status(BLOCKSTREAM, "/api/x", 503)
    with pytest.raises(ProviderUnavailable):
        await make(upstream, retries=2).get_json("/x")
    assert upstream.count(BLOCKSTREAM, "/api/x") == 3


async def test_http_retry_recovers(upstream: FakeUpstream) -> None:
    attempts = {"n": 0}

    def flaky(_req: httpx.Request) -> httpx.Response:
        attempts["n"] += 1
        return httpx.Response(500) if attempts["n"] == 1 else httpx.Response(200, json={"ok": 1})

    upstream.handler(BLOCKSTREAM, "/api/x", flaky)
    assert await make(upstream).get_json("/x") == {"ok": 1}


async def test_http_timeout_is_unavailable(upstream: FakeUpstream) -> None:
    def boom(req: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=req)

    upstream.handler(BLOCKSTREAM, "/api/x", boom)
    with pytest.raises(ProviderUnavailable, match="timeout"):
        await make(upstream).get_json("/x")


async def test_block_summary_skips_coinbase_and_rounds_fractional_vsize(
    upstream: FakeUpstream,
) -> None:
    upstream.json(
        MEMPOOL,
        "/api/v1/block/abc/summary",
        [
            {"txid": "c" * 64, "fee": 0, "vsize": 200, "value": 315_000_000},
            {"txid": "d" * 64, "fee": 500, "vsize": 140.25, "value": 10_000},
        ],
    )
    p = MempoolSpaceProvider(make(upstream, MEMPOOL), "mempool", "m")
    txs = await p.get_block_summary("abc")
    assert [t.txid for t in txs] == ["d" * 64]
    assert txs[0].vsize == 141
