from datetime import UTC, datetime
from typing import Any

import httpx
from sqlalchemy import select

from app.core.config import Settings
from app.db.models import AlertEvent, AlertRule, BlockRecord, WhaleScannedBlock, WhaleTx
from app.db.session import Database
from app.providers.registry import build_providers
from app.services.blockchain import BlockchainService, TTLPolicy
from app.whales.worker import WhaleWorker
from tests.conftest import MEMPOOL, FakeUpstream

SATS = 100_000_000
WHALE = "1" * 64
SMALL = "2" * 64
COINBASE = "3" * 64
MEMPOOL_WHALE = "4" * 64
BLOCK_HASH = "b" * 64


def summary(*txs: tuple[str, int]) -> list[dict[str, Any]]:
    # First entry is always the coinbase in mempool.space summaries.
    out = [{"txid": COINBASE, "value": 9_000 * SATS, "fee": 0, "vsize": 200, "rate": 0}]
    out += [{"txid": t, "value": v, "fee": 5000, "vsize": 250, "rate": 20} for t, v in txs]
    return out


def full_tx(txid: str, confirmed: bool = True) -> dict[str, Any]:
    return {
        "txid": txid,
        "version": 2,
        "locktime": 0,
        "size": 400,
        "weight": 1000,
        "fee": 5000,
        "vin": [
            {
                "txid": "9" * 64,
                "vout": i,
                "prevout": {"scriptpubkey_address": "bc1qsrc", "value": 50 * SATS},
            }
            for i in range(6)
        ],
        "vout": [{"scriptpubkey_address": "bc1qdst", "value": 300 * SATS - 5000}],
        "status": {
            "confirmed": confirmed,
            "block_height": 900,
            "block_hash": BLOCK_HASH,
            "block_time": 1_800_000_000,
        }
        if confirmed
        else {"confirmed": False},
    }


async def setup(upstream: FakeUpstream, settings: Settings) -> tuple[WhaleWorker, Database]:
    client = httpx.AsyncClient(transport=upstream.transport)
    svc = BlockchainService(
        build_providers(settings, client),
        ttl=TTLPolicy(mempool_recent=0, tx_unconfirmed=0, tx_confirmed=0),
    )
    db = Database(settings.database_url)
    await db.create_all()
    async with db.session() as s:
        s.add(
            BlockRecord(
                height=900,
                hash=BLOCK_HASH,
                timestamp=datetime(2027, 1, 15, 8, 0, tzinfo=UTC),
                tx_count=3,
                size=1,
                weight=1,
                source="test",
                ingested_at=datetime.now(UTC),
            )
        )
        await s.commit()
    upstream.json(
        MEMPOOL,
        f"/api/v1/block/{BLOCK_HASH}/summary",
        summary((WHALE, 300 * SATS), (SMALL, 99 * SATS)),
    )
    upstream.json(MEMPOOL, "/api/mempool/recent", [])
    upstream.json(MEMPOOL, f"/api/tx/{WHALE}", full_tx(WHALE))
    worker = WhaleWorker(svc, db, min_btc=100, enrich_per_cycle=10)
    return worker, db


async def test_scans_blocks_skips_coinbase_and_small(
    upstream: FakeUpstream, settings: Settings
) -> None:
    worker, db = await setup(upstream, settings)
    r = await worker.run_once()
    assert r.status == "success" and r.blocks_scanned == 1 and r.whales_new == 1 and r.enriched == 1
    async with db.session() as s:
        whales = list((await s.execute(select(WhaleTx))).scalars())
        scanned = await s.get(WhaleScannedBlock, 900)
    assert [w.txid for w in whales] == [WHALE]
    w = whales[0]
    assert w.confirmed and w.block_height == 900 and w.detected_via == "block"
    assert w.enriched and w.input_count == 6 and w.output_count == 1
    assert scanned is not None and scanned.whale_count == 1 and scanned.tx_count == 2

    # Second cycle: block already scanned -> no new summary request.
    before = upstream.count(MEMPOOL, f"/api/v1/block/{BLOCK_HASH}/summary")
    r2 = await worker.run_once()
    assert r2.blocks_scanned == 0 and r2.whales_new == 0
    assert upstream.count(MEMPOOL, f"/api/v1/block/{BLOCK_HASH}/summary") == before
    await db.dispose()


async def test_mempool_whale_then_confirmation_and_alerts(
    upstream: FakeUpstream, settings: Settings
) -> None:
    worker, db = await setup(upstream, settings)
    upstream.json(MEMPOOL, f"/api/v1/block/{BLOCK_HASH}/summary", summary())  # block has no whale
    upstream.json(
        MEMPOOL,
        "/api/mempool/recent",
        [{"txid": MEMPOOL_WHALE, "fee": 4000, "vsize": 200, "value": 500 * SATS}],
    )
    upstream.json(MEMPOOL, f"/api/tx/{MEMPOOL_WHALE}", full_tx(MEMPOOL_WHALE, confirmed=False))
    now = datetime.now(UTC)
    async with db.session() as s:
        s.add_all(
            [
                AlertRule(
                    name="todas",
                    min_btc=200,
                    include_unconfirmed=True,
                    enabled=True,
                    created_at=now,
                    updated_at=now,
                ),
                AlertRule(
                    name="solo conf.",
                    min_btc=200,
                    include_unconfirmed=False,
                    enabled=True,
                    created_at=now,
                    updated_at=now,
                ),
                AlertRule(
                    name="alta",
                    min_btc=1000,
                    include_unconfirmed=True,
                    enabled=True,
                    created_at=now,
                    updated_at=now,
                ),
                AlertRule(
                    name="off",
                    min_btc=100,
                    include_unconfirmed=True,
                    enabled=False,
                    created_at=now,
                    updated_at=now,
                ),
            ]
        )
        await s.commit()

    r1 = await worker.run_once()
    assert r1.whales_new == 1 and r1.alerts_triggered == 1  # only "todas"
    async with db.session() as s:
        w = await s.get(WhaleTx, MEMPOOL_WHALE)
        assert w is not None and not w.confirmed and w.detected_via == "mempool" and w.enriched

    # Now the transaction confirms (seen in a newly ingested block).
    new_hash = "c" * 64
    async with db.session() as s:
        s.add(
            BlockRecord(
                height=901,
                hash=new_hash,
                timestamp=datetime(2027, 1, 15, 8, 10, tzinfo=UTC),
                tx_count=2,
                size=1,
                weight=1,
                source="t",
                ingested_at=now,
            )
        )
        await s.commit()
    upstream.json(
        MEMPOOL, f"/api/v1/block/{new_hash}/summary", summary((MEMPOOL_WHALE, 500 * SATS))
    )
    r2 = await worker.run_once()
    assert r2.whales_confirmed == 1 and r2.alerts_triggered == 1  # "solo conf." now fires
    r3 = await worker.run_once()
    assert r3.alerts_triggered == 0  # never duplicated

    async with db.session() as s:
        w = await s.get(WhaleTx, MEMPOOL_WHALE)
        events = list((await s.execute(select(AlertEvent))).scalars())
    assert w is not None and w.confirmed and w.block_height == 901
    assert sorted(e.rule_name for e in events) == ["solo conf.", "todas"]
    await db.dispose()


async def test_summary_failure_is_reported_not_fatal(
    upstream: FakeUpstream, settings: Settings
) -> None:
    worker, db = await setup(upstream, settings)
    upstream.status(MEMPOOL, f"/api/v1/block/{BLOCK_HASH}/summary", 500)
    r = await worker.run_once()
    assert r.blocks_scanned == 0 and r.errors and r.status == "failed"
    async with db.session() as s:
        assert await s.get(WhaleScannedBlock, 900) is None  # retried next cycle
    await db.dispose()


async def test_missing_upstream_tx_is_marked(upstream: FakeUpstream, settings: Settings) -> None:
    worker, db = await setup(upstream, settings)
    upstream.json(MEMPOOL, f"/api/v1/block/{BLOCK_HASH}/summary", summary())
    upstream.json(
        MEMPOOL,
        "/api/mempool/recent",
        [{"txid": MEMPOOL_WHALE, "fee": 1, "vsize": 1, "value": 200 * SATS}],
    )
    await worker.run_once()  # /api/tx/<id> -> 404 in the fake upstream
    async with db.session() as s:
        w = await s.get(WhaleTx, MEMPOOL_WHALE)
    assert w is not None and w.upstream_missing and not w.enriched
    await db.dispose()
