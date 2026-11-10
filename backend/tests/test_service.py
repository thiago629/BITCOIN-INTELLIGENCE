import asyncio

import httpx
import pytest

from app.core.config import Settings
from app.providers.errors import AllProvidersFailed, ProviderNotFound
from app.providers.registry import build_providers
from app.services.blockchain import BlockchainService, TTLPolicy
from tests.conftest import BLOCKSTREAM, MEMPOOL, TXID, FakeUpstream, tx_payload


def service(upstream: FakeUpstream, settings: Settings, **kw: object) -> BlockchainService:
    client = httpx.AsyncClient(transport=upstream.transport)
    return BlockchainService(build_providers(settings, client), **kw)  # type: ignore[arg-type]


async def test_result_is_cached_with_provenance(upstream: FakeUpstream, settings: Settings) -> None:
    upstream.text(MEMPOOL, "/api/blocks/tip/height", "900000")
    svc = service(upstream, settings)
    first = await svc.get_tip_height()
    second = await svc.get_tip_height()
    assert first.data == second.data == 900000
    assert first.meta.source == "mempool.space" and not first.meta.cached
    assert second.meta.cached and second.meta.fetched_at == first.meta.fetched_at
    assert upstream.count(MEMPOOL, "/api/blocks/tip/height") == 1


async def test_concurrent_requests_hit_upstream_once(
    upstream: FakeUpstream, settings: Settings
) -> None:
    upstream.text(MEMPOOL, "/api/blocks/tip/height", "900000")
    svc = service(upstream, settings)
    results = await asyncio.gather(*(svc.get_tip_height() for _ in range(20)))
    assert {r.data for r in results} == {900000}
    assert upstream.count(MEMPOOL, "/api/blocks/tip/height") == 1


async def test_fallback_to_secondary_provider(upstream: FakeUpstream, settings: Settings) -> None:
    upstream.status(MEMPOOL, "/api/blocks/tip/height", 502)
    upstream.text(BLOCKSTREAM, "/api/blocks/tip/height", "900001")
    svc = service(upstream, settings)
    res = await svc.get_tip_height()
    assert res.data == 900001
    assert res.meta.source == "blockstream.info" and res.meta.fallback_used
    assert svc.health["mempool"].consecutive_failures == 1


async def test_not_found_does_not_fall_back(upstream: FakeUpstream, settings: Settings) -> None:
    svc = service(upstream, settings)  # mempool returns 404 for unknown routes
    with pytest.raises(ProviderNotFound):
        await svc.get_transaction(TXID)
    assert upstream.count(BLOCKSTREAM, f"/api/tx/{TXID}") == 0


async def test_all_providers_failed(upstream: FakeUpstream, settings: Settings) -> None:
    upstream.status(MEMPOOL, "/api/blocks/tip/height", 500)
    upstream.status(BLOCKSTREAM, "/api/blocks/tip/height", 500)
    with pytest.raises(AllProvidersFailed) as exc:
        await service(upstream, settings).get_tip_height()
    assert len(exc.value.errors) == 2


async def test_provider_cooldown_after_threshold(
    upstream: FakeUpstream, settings: Settings
) -> None:
    upstream.status(MEMPOOL, "/api/blocks/tip/height", 500)
    upstream.text(BLOCKSTREAM, "/api/blocks/tip/height", "1")
    svc = service(upstream, settings, failure_threshold=2, cooldown_s=60, ttl=TTLPolicy(tip=0))
    for _ in range(2):
        await svc.get_tip_height()
    calls_before = upstream.count(MEMPOOL, "/api/blocks/tip/height")
    await svc.get_tip_height()
    assert upstream.count(MEMPOOL, "/api/blocks/tip/height") == calls_before  # skipped
    status = {p["key"]: p for p in svc.provider_status()}
    assert status["mempool"]["in_cooldown"] and not status["blockstream"]["in_cooldown"]


async def test_rate_limit_triggers_immediate_cooldown(
    upstream: FakeUpstream, settings: Settings
) -> None:
    upstream.status(MEMPOOL, "/api/blocks/tip/height", 429, {"Retry-After": "120"})
    upstream.text(BLOCKSTREAM, "/api/blocks/tip/height", "1")
    svc = service(upstream, settings, ttl=TTLPolicy(tip=0))
    await svc.get_tip_height()
    assert svc.provider_status()[0]["cooldown_remaining_s"] > 100


async def test_capability_only_on_some_providers(
    upstream: FakeUpstream, settings: Settings
) -> None:
    # Difficulty adjustment exists only on mempool.space; blockstream must not be tried.
    upstream.status(MEMPOOL, "/api/v1/difficulty-adjustment", 500)
    with pytest.raises(AllProvidersFailed):
        await service(upstream, settings).get_difficulty_adjustment()
    assert not any(host == BLOCKSTREAM for host, _ in upstream.calls)


async def test_unconfirmed_tx_uses_short_ttl(upstream: FakeUpstream, settings: Settings) -> None:
    upstream.json(MEMPOOL, f"/api/tx/{TXID}", tx_payload(confirmed=False))
    svc = service(upstream, settings, ttl=TTLPolicy(tx_unconfirmed=0, tx_confirmed=600))
    await svc.get_transaction(TXID)
    await svc.get_transaction(TXID)
    assert upstream.count(MEMPOOL, f"/api/tx/{TXID}") == 2

    upstream.json(MEMPOOL, f"/api/tx/{TXID}", tx_payload(confirmed=True))
    svc.cache.clear()
    await svc.get_transaction(TXID)
    await svc.get_transaction(TXID)
    assert upstream.count(MEMPOOL, f"/api/tx/{TXID}") == 3
