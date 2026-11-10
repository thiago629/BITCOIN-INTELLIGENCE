"""Whale Tracker endpoints (served from the database filled by WhaleWorker)."""

from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from app.api.deps import get_db, get_service
from app.api.schemas import TxId
from app.db.models import WhaleTx
from app.db.repository import as_utc
from app.db.session import Database
from app.providers.errors import AllProvidersFailed, ProviderError, ProviderNotFound
from app.services.blockchain import BlockchainService
from app.whales import store
from app.whales.analysis import Analysis, Tier, analyse, build_tiers, enrich, tier_for

router = APIRouter(prefix="/whales", tags=["whales"])
Db = Annotated[Database, Depends(get_db)]


def _tiers(request: Request) -> list[Tier]:
    return build_tiers(request.app.state.settings.whale_tiers_btc)


class WhaleOut(BaseModel):
    txid: str
    value_sat: int
    fee_sat: int | None
    vsize: int | None
    confirmed: bool
    block_height: int | None
    block_hash: str | None
    block_time: datetime | None
    first_seen_at: datetime
    event_time: datetime
    detected_via: str
    source: str
    tier: Tier | None
    enriched: bool
    upstream_missing: bool
    input_count: int | None
    output_count: int | None
    returned_to_input_sat: int | None


def _out(row: WhaleTx, tiers: list[Tier]) -> WhaleOut:
    return WhaleOut(
        txid=row.txid,
        value_sat=row.value_sat,
        fee_sat=row.fee_sat,
        vsize=row.vsize,
        confirmed=row.confirmed,
        block_height=row.block_height,
        block_hash=row.block_hash,
        block_time=as_utc(row.block_time),
        first_seen_at=as_utc(row.first_seen_at),  # type: ignore[arg-type]
        event_time=as_utc(row.event_time),  # type: ignore[arg-type]
        detected_via=row.detected_via,
        source=row.source,
        tier=tier_for(row.value_sat, tiers),
        enriched=row.enriched,
        upstream_missing=row.upstream_missing,
        input_count=row.input_count,
        output_count=row.output_count,
        returned_to_input_sat=row.returned_to_input_sat,
    )


class Tracking(BaseModel):
    enabled: bool
    min_btc: float
    tiers: list[Tier]
    blocks_scanned: int
    lowest_height: int | None
    highest_height: int | None
    last_scan_at: datetime | None
    coverage_since: datetime | None = Field(
        description="Block time of the oldest analysed block: earlier periods are not covered"
    )
    notes: list[str]


async def _tracking(request: Request, db: Database) -> Tracking:
    s = request.app.state.settings
    async with db.session() as session:
        cov = await store.coverage(session)
    return Tracking(
        enabled=getattr(request.app.state, "whale_worker", None) is not None,
        min_btc=s.whale_min_btc,
        tiers=build_tiers(s.whale_tiers_btc),
        notes=[
            "El importe es la suma de todas las salidas e incluye el posible cambio "
            "devuelto al emisor: es un máximo, no el importe económico real.",
            "Las transacciones confirmadas se detectan analizando bloques completos "
            "(cobertura total de los bloques escaneados).",
            "Las transacciones sin confirmar proceden de una muestra periódica del mempool, "
            "no de su totalidad.",
        ],
        **cov,  # type: ignore[arg-type]
    )


class WhaleList(BaseModel):
    data: list[WhaleOut]
    total: int
    limit: int
    offset: int
    generated_at: datetime
    source: str = "database"
    tracking: Tracking


@router.get("", response_model=WhaleList)
async def list_whales(
    request: Request,
    db: Db,
    min_btc: Annotated[float | None, Query(ge=0, le=21_000_000)] = None,
    max_btc: Annotated[float | None, Query(gt=0, le=21_000_000)] = None,
    since: datetime | None = None,
    until: datetime | None = None,
    status: Literal["all", "confirmed", "unconfirmed"] = "all",
    sort: Literal["time", "value"] = "time",
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0, le=100_000)] = 0,
) -> Any:
    if min_btc is not None and max_btc is not None and max_btc <= min_btc:
        raise HTTPException(422, "max_btc must be greater than min_btc")
    if since and until and until <= since:
        raise HTTPException(422, "until must be after since")
    f = store.WhaleFilter(
        min_btc=min_btc,
        max_btc=max_btc,
        since=_aware(since),
        until=_aware(until),
        status=status,
        sort=sort,
    )
    tiers = _tiers(request)
    async with db.session() as session:
        rows, total = await store.query_whales(session, f, limit, offset)
    return WhaleList(
        data=[_out(r, tiers) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
        generated_at=datetime.now(UTC),
        tracking=await _tracking(request, db),
    )


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


class HourBucket(BaseModel):
    hour: datetime
    # None = hour not (fully) covered by analysed blocks: unknown, not zero.
    count: int | None
    volume_sat: int | None


class TierCount(BaseModel):
    tier: Tier
    count: int
    volume_sat: int


class WhaleStats(BaseModel):
    hours: int
    count: int
    confirmed_count: int
    unconfirmed_count: int
    volume_sat: int
    largest: WhaleOut | None
    by_hour: list[HourBucket]
    by_tier: list[TierCount]
    generated_at: datetime
    source: str = "database"
    tracking: Tracking


@router.get("/stats", response_model=WhaleStats)
async def whale_stats(
    request: Request, db: Db, hours: Annotated[int, Query(ge=1, le=24 * 30)] = 24
) -> Any:
    now = datetime.now(UTC)
    since = now - timedelta(hours=hours)
    tiers = _tiers(request)
    async with db.session() as session:
        rows = await store.whales_since(session, since)

    start = since.replace(minute=0, second=0, microsecond=0)
    buckets = {start + timedelta(hours=i): [0, 0] for i in range(hours + 1)}
    for r in rows:
        key = as_utc(r.event_time).replace(minute=0, second=0, microsecond=0)  # type: ignore[union-attr]
        if key in buckets:
            buckets[key][0] += 1
            buckets[key][1] += r.value_sat
    by_tier = []
    for t in tiers:
        members = [r for r in rows if (rt := tier_for(r.value_sat, tiers)) and rt.level == t.level]
        by_tier.append(
            TierCount(tier=t, count=len(members), volume_sat=sum(m.value_sat for m in members))
        )
    largest = max(rows, key=lambda r: r.value_sat, default=None)
    tracking = await _tracking(request, db)
    # First fully covered hour: the hour after the oldest analysed block.
    covered = (
        tracking.coverage_since.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
        if tracking.coverage_since
        else None
    )
    return WhaleStats(
        hours=hours,
        count=len(rows),
        confirmed_count=sum(1 for r in rows if r.confirmed),
        unconfirmed_count=sum(1 for r in rows if not r.confirmed),
        volume_sat=sum(r.value_sat for r in rows),
        largest=_out(largest, tiers) if largest else None,
        by_hour=[
            HourBucket(hour=h, count=c, volume_sat=v)
            if covered is not None and h >= covered
            else HourBucket(hour=h, count=None, volume_sat=None)
            for h, (c, v) in sorted(buckets.items())
        ],
        by_tier=by_tier,
        generated_at=now,
        tracking=tracking,
    )


class WhaleDetail(BaseModel):
    whale: WhaleOut
    analysis: Analysis
    generated_at: datetime
    enrichment_error: str | None = None


@router.get("/{txid}", response_model=WhaleDetail)
async def whale_detail(
    txid: TxId,
    request: Request,
    db: Db,
    service: Annotated[BlockchainService, Depends(get_service)],
) -> Any:
    txid = txid.lower()
    error: str | None = None
    async with db.session() as session:
        row = await session.get(WhaleTx, txid)
        if row is None:
            raise HTTPException(404, "This transaction is not in the Whale Tracker")
        if not row.enriched and not row.upstream_missing:
            # Analyse on demand so the detail view is complete without waiting.
            try:
                res = await service.get_transaction(txid)
                store.apply_enrichment(row, enrich(res.data))
                await session.commit()
            except ProviderNotFound:
                row.upstream_missing = True
                await session.commit()
            except (ProviderError, AllProvidersFailed) as exc:
                error = str(exc)
        return WhaleDetail(
            whale=_out(row, _tiers(request)),
            analysis=analyse(store.facts(row)),
            generated_at=datetime.now(UTC),
            enrichment_error=error,
        )
