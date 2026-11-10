"""Historical data served from our own database (filled by ingestion)."""

from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from app.api.deps import get_db
from app.api.schemas import StoredMeta
from app.db import repository as repo
from app.db.repository import as_utc
from app.db.session import Database

router = APIRouter(prefix="/history", tags=["history"])
Db = Annotated[Database, Depends(get_db)]


class StoredBlock(BaseModel):
    height: int
    hash: str
    timestamp: datetime
    tx_count: int
    size: int
    weight: int
    total_fees_sat: int | None
    reward_sat: int | None
    median_fee_rate: float | None
    avg_fee_rate: float | None
    source: str
    ingested_at: datetime


class StoredSnapshot(BaseModel):
    captured_at: datetime
    tip_height: int | None
    mempool_count: int | None
    mempool_vsize: int | None
    mempool_total_fee_sat: int | None
    fee_fastest: float | None
    fee_half_hour: float | None
    fee_hour: float | None
    fee_economy: float | None
    source: str


class BlocksHistory(BaseModel):
    data: list[StoredBlock]
    meta: StoredMeta


class SnapshotsHistory(BaseModel):
    data: list[StoredSnapshot]
    meta: StoredMeta


@router.get("/blocks", response_model=BlocksHistory)
async def blocks_history(db: Db, limit: Annotated[int, Query(ge=1, le=2016)] = 144) -> Any:
    async with db.session() as session:
        rows = await repo.list_blocks(session, limit)
    data = [
        StoredBlock(
            height=r.height,
            hash=r.hash,
            timestamp=as_utc(r.timestamp),  # type: ignore[arg-type]
            tx_count=r.tx_count,
            size=r.size,
            weight=r.weight,
            total_fees_sat=r.total_fees_sat,
            reward_sat=r.reward_sat,
            median_fee_rate=r.median_fee_rate,
            avg_fee_rate=r.avg_fee_rate,
            source=r.source,
            ingested_at=as_utc(r.ingested_at),  # type: ignore[arg-type]
        )
        for r in rows
    ]
    return BlocksHistory(
        data=data, meta=StoredMeta(generated_at=datetime.now(UTC), records=len(data))
    )


@router.get("/network", response_model=SnapshotsHistory)
async def network_history(db: Db, hours: Annotated[int, Query(ge=1, le=24 * 30)] = 24) -> Any:
    since = datetime.now(UTC) - timedelta(hours=hours)
    async with db.session() as session:
        rows = await repo.list_snapshots(session, since)
    data = [
        StoredSnapshot(
            captured_at=as_utc(r.captured_at),  # type: ignore[arg-type]
            tip_height=r.tip_height,
            mempool_count=r.mempool_count,
            mempool_vsize=r.mempool_vsize,
            mempool_total_fee_sat=r.mempool_total_fee_sat,
            fee_fastest=r.fee_fastest,
            fee_half_hour=r.fee_half_hour,
            fee_hour=r.fee_hour,
            fee_economy=r.fee_economy,
            source=r.source,
        )
        for r in rows
    ]
    return SnapshotsHistory(
        data=data, meta=StoredMeta(generated_at=datetime.now(UTC), records=len(data))
    )
