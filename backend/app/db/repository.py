"""Data-access functions (kept dialect-agnostic: SQLite and PostgreSQL)."""

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import BlockRecord, IngestionRun, NetworkSnapshot
from app.domain.models import Block


def as_utc(value: datetime | None) -> datetime | None:
    """SQLite drops tzinfo; normalise everything read back to aware UTC."""
    if value is None:
        return None
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


async def upsert_blocks(session: AsyncSession, blocks: list[Block], source: str) -> int:
    """Insert new blocks; replace rows whose hash changed (chain reorganisation).

    Returns the number of rows inserted or replaced.
    """
    if not blocks:
        return 0
    heights = [b.height for b in blocks]
    existing = {
        r.height: r
        for r in (
            await session.execute(select(BlockRecord).where(BlockRecord.height.in_(heights)))
        ).scalars()
    }
    now = datetime.now(UTC)
    changed = 0
    for b in blocks:
        row = existing.get(b.height)
        if row is not None and row.hash == b.hash:
            continue
        if row is not None:
            await session.delete(row)  # reorg: the block at this height changed
            await session.flush()
        session.add(
            BlockRecord(
                height=b.height,
                hash=b.hash,
                timestamp=b.timestamp,
                tx_count=b.tx_count,
                size=b.size,
                weight=b.weight,
                difficulty=b.difficulty,
                total_fees_sat=b.total_fees_sat,
                reward_sat=b.reward_sat,
                median_fee_rate=b.median_fee_rate,
                avg_fee_rate=b.avg_fee_rate,
                source=source,
                ingested_at=now,
            )
        )
        changed += 1
    await session.commit()
    return changed


async def stored_heights(session: AsyncSession, low: int, high: int) -> set[int]:
    rows = await session.execute(
        select(BlockRecord.height).where(BlockRecord.height.between(low, high))
    )
    return set(rows.scalars())


async def list_blocks(session: AsyncSession, limit: int) -> list[BlockRecord]:
    rows = await session.execute(
        select(BlockRecord).order_by(BlockRecord.height.desc()).limit(limit)
    )
    return list(rows.scalars())


async def count_blocks(session: AsyncSession) -> int:
    return int((await session.execute(select(func.count(BlockRecord.height)))).scalar_one())


async def add_snapshot(session: AsyncSession, snapshot: NetworkSnapshot) -> None:
    session.add(snapshot)
    await session.commit()


async def list_snapshots(session: AsyncSession, since: datetime) -> list[NetworkSnapshot]:
    rows = await session.execute(
        select(NetworkSnapshot)
        .where(NetworkSnapshot.captured_at >= since)
        .order_by(NetworkSnapshot.captured_at.asc())
    )
    return list(rows.scalars())


async def add_run(session: AsyncSession, run: IngestionRun) -> IngestionRun:
    session.add(run)
    await session.commit()
    return run


async def list_runs(session: AsyncSession, limit: int) -> list[IngestionRun]:
    rows = await session.execute(select(IngestionRun).order_by(IngestionRun.id.desc()).limit(limit))
    return list(rows.scalars())
