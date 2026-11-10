from typing import Any

import httpx

from app.core.config import Settings
from app.db import repository as repo
from app.db.session import Database
from app.ingestion.worker import IngestionWorker
from app.providers.registry import build_providers
from app.services.blockchain import BlockchainService, TTLPolicy
from tests.conftest import BLOCKSTREAM, MEMPOOL, MEMPOOL_PAYLOAD, FakeUpstream, block_payload

TIP = 1000


def page(start: int, n: int = 15, **kw: Any) -> list[dict[str, Any]]:
    return [block_payload(h, extras=True, **kw) for h in range(start, start - n, -1)]


def setup_network(upstream: FakeUpstream) -> None:
    upstream.json(MEMPOOL, "/api/v1/blocks", page(TIP))
    for start in range(TIP - 15, TIP - 200, -15):
        upstream.json(MEMPOOL, f"/api/v1/blocks/{start}", page(start))
    upstream.text(MEMPOOL, "/api/blocks/tip/height", str(TIP))
    upstream.json(MEMPOOL, "/api/mempool", MEMPOOL_PAYLOAD)
    upstream.json(
        MEMPOOL,
        "/api/v1/fees/recommended",
        {"fastestFee": 5, "halfHourFee": 4, "hourFee": 3, "economyFee": 2, "minimumFee": 1},
    )


async def make_worker(
    upstream: FakeUpstream, settings: Settings, backfill: int
) -> tuple[IngestionWorker, Database]:
    client = httpx.AsyncClient(transport=upstream.transport)
    svc = BlockchainService(
        build_providers(settings, client), ttl=TTLPolicy(recent_blocks=0, block=0)
    )
    db = Database(settings.database_url)
    await db.create_all()
    return IngestionWorker(svc, db, backfill_blocks=backfill, max_pages=20), db


async def test_backfill_and_snapshot(upstream: FakeUpstream, settings: Settings) -> None:
    setup_network(upstream)
    worker, db = await make_worker(upstream, settings, backfill=40)
    result = await worker.run_once()
    assert result.status == "success"
    assert result.blocks_stored == 40
    assert result.snapshot_stored
    async with db.session() as s:
        blocks = await repo.list_blocks(s, 100)
        runs = await repo.list_runs(s, 10)
    assert [b.height for b in blocks] == list(range(TIP, TIP - 40, -1))
    assert blocks[0].total_fees_sat == 2_500_000
    assert runs[0].status == "success" and runs[0].sources == "mempool.space"

    # Second run: nothing missing -> only the first page is requested.
    calls_before = len(upstream.calls)
    result2 = await worker.run_once()
    assert result2.blocks_stored == 0
    block_calls = [p for _, p in upstream.calls[calls_before:] if p.startswith("/api/v1/blocks")]
    assert block_calls == ["/api/v1/blocks"]
    await db.dispose()


async def test_reorg_replaces_block(upstream: FakeUpstream, settings: Settings) -> None:
    setup_network(upstream)
    worker, db = await make_worker(upstream, settings, backfill=15)
    await worker.run_once()
    reorged = page(TIP)
    reorged[0] = block_payload(TIP, extras=True, hash_="9" * 64)
    upstream.json(MEMPOOL, "/api/v1/blocks", reorged)
    result = await worker.run_once()
    assert result.blocks_stored == 1
    async with db.session() as s:
        top = (await repo.list_blocks(s, 1))[0]
    assert top.height == TIP and top.hash == "9" * 64
    await db.dispose()


async def test_failed_run_is_recorded(upstream: FakeUpstream, settings: Settings) -> None:
    for host in (MEMPOOL, BLOCKSTREAM):
        upstream.status(host, "/api/v1/blocks", 500)
        upstream.status(host, "/api/blocks", 500)
    worker, db = await make_worker(upstream, settings, backfill=15)
    result = await worker.run_once()
    assert result.status == "failed"
    assert result.blocks_stored == 0 and not result.snapshot_stored
    async with db.session() as s:
        runs = await repo.list_runs(s, 1)
        assert await repo.count_blocks(s) == 0
    assert runs[0].status == "failed" and runs[0].error
    await db.dispose()


async def test_partial_run_when_only_snapshot_works(
    upstream: FakeUpstream, settings: Settings
) -> None:
    setup_network(upstream)
    upstream.status(MEMPOOL, "/api/v1/blocks", 500)
    upstream.status(BLOCKSTREAM, "/api/blocks", 500)
    worker, db = await make_worker(upstream, settings, backfill=15)
    result = await worker.run_once()
    assert result.status == "partial" and result.snapshot_stored
    await db.dispose()
