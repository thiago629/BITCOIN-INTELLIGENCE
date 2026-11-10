"""Periodic ingestion: block history + network snapshots.

Each cycle:
1. Fetches the newest page of blocks and back-fills any missing heights down
   to ``tip - backfill_blocks`` (bounded by ``max_pages`` requests per cycle).
2. Stores a mempool/fee snapshot (time series for later analytics).
3. Writes an ``ingestion_runs`` row so every cycle is auditable.

Failures never crash the worker; they are recorded and retried next cycle.
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from app.db import repository as repo
from app.db.models import IngestionRun, NetworkSnapshot
from app.db.session import Database
from app.domain.models import Block
from app.providers.errors import AllProvidersFailed, ProviderError
from app.services.blockchain import BlockchainService

logger = logging.getLogger(__name__)


@dataclass
class IngestionResult:
    status: str
    blocks_stored: int
    snapshot_stored: bool
    error: str | None


class IngestionWorker:
    def __init__(
        self,
        service: BlockchainService,
        db: Database,
        interval_s: float = 60,
        backfill_blocks: int = 144,
        max_pages: int = 20,
    ) -> None:
        self.service = service
        self.db = db
        self.interval_s = interval_s
        self.backfill_blocks = backfill_blocks
        self.max_pages = max_pages
        self._task: asyncio.Task[None] | None = None
        self._stop = asyncio.Event()
        self.last_result: IngestionResult | None = None
        self.last_run_at: datetime | None = None

    async def run_once(self) -> IngestionResult:
        started = datetime.now(UTC)
        errors: list[str] = []
        sources: set[str] = set()
        blocks_stored = 0
        snapshot_stored = False

        # 1. Blocks ---------------------------------------------------------
        try:
            blocks_stored = await self._ingest_blocks(sources)
        except (ProviderError, AllProvidersFailed) as exc:
            errors.append(f"blocks: {exc}")

        # 2. Network snapshot ----------------------------------------------
        try:
            snapshot_stored, snapshot_errors = await self._store_snapshot(sources)
            errors.extend(f"snapshot {e}" for e in snapshot_errors)
        except Exception as exc:  # snapshot is best effort
            logger.exception("snapshot_store_failed")
            errors.append(f"snapshot: {type(exc).__name__}: {exc}")

        if not errors:
            status = "success"
        elif blocks_stored or snapshot_stored:
            status = "partial"
        else:
            status = "failed"

        result = IngestionResult(status, blocks_stored, snapshot_stored, "; ".join(errors) or None)
        try:
            async with self.db.session() as session:
                await repo.add_run(
                    session,
                    IngestionRun(
                        started_at=started,
                        finished_at=datetime.now(UTC),
                        status=status,
                        blocks_stored=blocks_stored,
                        snapshot_stored=snapshot_stored,
                        sources=",".join(sorted(sources)) or None,
                        error=result.error[:2000] if result.error else None,
                    ),
                )
        except Exception:
            logger.exception("ingestion_run_log_failed")

        self.last_result = result
        self.last_run_at = started
        log = logger.info if status == "success" else logger.warning
        log(
            "ingestion_cycle",
            extra={
                "status": status,
                "blocks_stored": blocks_stored,
                "snapshot_stored": snapshot_stored,
                "error": result.error,
            },
        )
        return result

    async def _ingest_blocks(self, sources: set[str]) -> int:
        first = await self.service.get_recent_blocks(None)
        if not first.data:
            return 0
        sources.add(first.meta.source)
        fetched: dict[int, Block] = {b.height: b for b in first.data}
        tip = max(fetched)
        low = max(0, tip - self.backfill_blocks + 1)

        async with self.db.session() as session:
            existing = await repo.stored_heights(session, low, tip)

        missing = set(range(low, tip + 1)) - existing - set(fetched)
        pages = 1
        while missing and pages < self.max_pages:
            start = max(missing)
            page = await self.service.get_recent_blocks(start)
            pages += 1
            sources.add(page.meta.source)
            if not page.data:
                break
            for b in page.data:
                fetched[b.height] = b
            missing -= {b.height for b in page.data}
            missing -= set(range(min(b.height for b in page.data), start + 1))

        to_store = [b for h, b in fetched.items() if h >= low]
        async with self.db.session() as session:
            return await repo.upsert_blocks(session, to_store, ",".join(sorted(sources)))

    async def _store_snapshot(self, sources: set[str]) -> tuple[bool, list[str]]:
        """Store whatever network data is available. Returns (stored, errors)."""
        tip = mempool = fees = None
        snap_sources: list[str] = []
        errors: list[str] = []
        for name, call in (
            ("tip", self.service.get_tip_height),
            ("mempool", self.service.get_mempool_stats),
            ("fees", self.service.get_fee_estimates),
        ):
            try:
                res = await call()
            except (ProviderError, AllProvidersFailed) as exc:
                errors.append(f"{name}: {exc}")
                continue
            snap_sources.append(res.meta.source)
            if name == "tip":
                tip = res.data
            elif name == "mempool":
                mempool = res.data
            else:
                fees = res.data

        if tip is None and mempool is None and fees is None:
            return False, errors

        sources.update(snap_sources)
        async with self.db.session() as session:
            await repo.add_snapshot(
                session,
                NetworkSnapshot(
                    captured_at=datetime.now(UTC),
                    tip_height=tip,
                    mempool_count=getattr(mempool, "count", None),
                    mempool_vsize=getattr(mempool, "vsize", None),
                    mempool_total_fee_sat=getattr(mempool, "total_fee_sat", None),
                    fee_fastest=getattr(fees, "fastest", None),
                    fee_half_hour=getattr(fees, "half_hour", None),
                    fee_hour=getattr(fees, "hour", None),
                    fee_economy=getattr(fees, "economy", None),
                    source=",".join(sorted(set(snap_sources))),
                ),
            )
        return True, errors

    # ---------------------------------------------------------- lifecycle
    def start(self) -> None:
        if self._task is None:
            self._stop.clear()
            self._task = asyncio.create_task(self._loop(), name="ingestion-worker")

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
                logger.exception("ingestion_cycle_crashed")
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self.interval_s)
            except TimeoutError:
                pass
