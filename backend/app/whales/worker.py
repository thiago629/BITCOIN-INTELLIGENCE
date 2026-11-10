"""Whale Tracker worker.

Each cycle:
1. **Blocks** — scans blocks already stored by the ingestion worker (newest
   first, bounded per cycle) with one block-summary request per block and
   stores every transaction at or above the tracking threshold.
2. **Mempool sample** — checks the provider's list of the latest mempool
   transactions. This is a *sample* of unconfirmed activity, not full
   coverage; confirmed data always comes from step 1.
3. **Enrichment** — fetches full details for a bounded number of pending
   whales (largest first) to compute observable structure.
4. **Alerts** — evaluates alert rules for new and newly confirmed whales.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import BlockRecord, WhaleTx
from app.db.repository import as_utc
from app.db.session import Database
from app.providers.errors import (
    AllProvidersFailed,
    ProviderBadResponse,
    ProviderError,
    ProviderNotFound,
)
from app.services.blockchain import BlockchainService
from app.whales import store
from app.whales.analysis import SATS, enrich

logger = logging.getLogger(__name__)


@dataclass
class WhaleCycleResult:
    blocks_scanned: int = 0
    whales_new: int = 0
    whales_confirmed: int = 0
    enriched: int = 0
    alerts_triggered: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def status(self) -> str:
        if not self.errors:
            return "success"
        return "partial" if (self.blocks_scanned or self.whales_new or self.enriched) else "failed"


class WhaleWorker:
    def __init__(
        self,
        service: BlockchainService,
        db: Database,
        min_btc: float,
        interval_s: float = 30,
        max_blocks_per_cycle: int = 6,
        enrich_per_cycle: int = 20,
        lookback_blocks: int = 144,
    ) -> None:
        self.service = service
        self.db = db
        self.min_sat = int(min_btc * SATS)
        self.interval_s = interval_s
        self.max_blocks = max_blocks_per_cycle
        self.enrich_limit = enrich_per_cycle
        self.lookback = lookback_blocks
        self._task: asyncio.Task[None] | None = None
        self._stop = asyncio.Event()
        self.last_result: WhaleCycleResult | None = None
        self.last_run_at: datetime | None = None

    async def run_once(self) -> WhaleCycleResult:
        result = WhaleCycleResult()
        self.last_run_at = datetime.now(UTC)
        async with self.db.session() as session:
            await self._scan_blocks(session, result)
            await self._sample_mempool(session, result)
            await self._enrich(session, result)
            await session.commit()
        self.last_result = result
        (logger.info if result.status == "success" else logger.warning)(
            "whale_cycle",
            extra={
                "status": result.status,
                "blocks_scanned": result.blocks_scanned,
                "whales_new": result.whales_new,
                "whales_confirmed": result.whales_confirmed,
                "enriched": result.enriched,
                "alerts": result.alerts_triggered,
                "errors": result.errors or None,
            },
        )
        return result

    async def _after_change(
        self, session: AsyncSession, row: WhaleTx, change: store.Change, result: WhaleCycleResult
    ) -> None:
        if change == "new":
            result.whales_new += 1
        elif change == "confirmed":
            result.whales_confirmed += 1
        if change in ("new", "confirmed"):
            await session.flush()
            result.alerts_triggered += len(await store.evaluate_alerts(session, row))

    async def _scan_blocks(self, session: AsyncSession, result: WhaleCycleResult) -> None:
        blocks = list(
            (
                await session.execute(
                    select(BlockRecord).order_by(BlockRecord.height.desc()).limit(self.lookback)
                )
            ).scalars()
        )
        done = await store.scanned_blocks(session, [b.height for b in blocks])
        todo = [b for b in blocks if done.get(b.height) != b.hash][: self.max_blocks]
        for block in todo:
            try:
                summary = await self.service.get_block_summary(block.hash)
            except (ProviderError, AllProvidersFailed) as exc:
                result.errors.append(f"block {block.height}: {exc}")
                errors = exc.errors if isinstance(exc, AllProvidersFailed) else [exc]
                if errors and all(isinstance(e, ProviderBadResponse) for e in errors):
                    continue  # this block's payload is the problem: try the next one
                break  # sources unavailable: stop and retry next cycle
            whales = [t for t in summary.data if t.value_sat >= self.min_sat]
            for t in whales:
                row, change = await store.upsert_whale(
                    session,
                    txid=t.txid,
                    value_sat=t.value_sat,
                    fee_sat=t.fee_sat,
                    vsize=t.vsize,
                    confirmed=True,
                    detected_via="block",
                    source=summary.meta.source,
                    block_height=block.height,
                    block_hash=block.hash,
                    block_time=as_utc(block.timestamp),
                )
                await self._after_change(session, row, change, result)
            await store.mark_scanned(
                session,
                block.height,
                block.hash,
                len(summary.data),
                len(whales),
                summary.meta.source,
            )
            result.blocks_scanned += 1
            await session.commit()

    async def _sample_mempool(self, session: AsyncSession, result: WhaleCycleResult) -> None:
        try:
            recent = await self.service.get_recent_mempool_txs()
        except (ProviderError, AllProvidersFailed) as exc:
            result.errors.append(f"mempool: {exc}")
            return
        for t in recent.data:
            if t.value_sat < self.min_sat:
                continue
            row, change = await store.upsert_whale(
                session,
                txid=t.txid,
                value_sat=t.value_sat,
                fee_sat=t.fee_sat,
                vsize=t.vsize,
                confirmed=False,
                detected_via="mempool",
                source=recent.meta.source,
            )
            await self._after_change(session, row, change, result)

    async def _enrich(self, session: AsyncSession, result: WhaleCycleResult) -> None:
        for row in await store.pending_enrichment(session, self.enrich_limit):
            try:
                res = await self.service.get_transaction(row.txid)
            except ProviderNotFound:
                row.upstream_missing = True
                continue
            except (ProviderError, AllProvidersFailed) as exc:
                result.errors.append(f"enrich {row.txid[:12]}: {exc}")
                break
            tx = res.data
            store.apply_enrichment(row, enrich(tx))
            result.enriched += 1
            if tx.status.confirmed and not row.confirmed:
                _, change = await store.upsert_whale(
                    session,
                    txid=row.txid,
                    value_sat=row.value_sat,
                    fee_sat=tx.fee_sat,
                    vsize=tx.vsize,
                    confirmed=True,
                    detected_via=row.detected_via,
                    source=row.source,
                    block_height=tx.status.block_height,
                    block_hash=tx.status.block_hash,
                    block_time=tx.status.block_time,
                )
                await self._after_change(session, row, change, result)

    # ---------------------------------------------------------- lifecycle
    def start(self) -> None:
        if self._task is None:
            self._stop.clear()
            self._task = asyncio.create_task(self._loop(), name="whale-worker")

    async def stop(self) -> None:
        self._stop.set()
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    async def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                await self.run_once()
            except Exception:
                logger.exception("whale_cycle_crashed")
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self.interval_s)
            except TimeoutError:
                pass
