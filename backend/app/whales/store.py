"""Persistence for whale movements and alerts."""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from sqlalchemy import Select, UnaryExpression, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AlertEvent, AlertRule, BlockRecord, WhaleScannedBlock, WhaleTx
from app.db.repository import as_utc
from app.whales.analysis import SATS, Enrichment, WhaleFacts

Change = Literal["new", "confirmed", "updated"] | None


async def upsert_whale(
    session: AsyncSession,
    *,
    txid: str,
    value_sat: int,
    fee_sat: int | None,
    vsize: int | None,
    confirmed: bool,
    detected_via: str,
    source: str,
    block_height: int | None = None,
    block_hash: str | None = None,
    block_time: datetime | None = None,
    now: datetime | None = None,
) -> tuple[WhaleTx, Change]:
    now = now or datetime.now(UTC)
    row = await session.get(WhaleTx, txid)
    if row is None:
        row = WhaleTx(
            txid=txid,
            value_sat=value_sat,
            fee_sat=fee_sat,
            vsize=vsize,
            confirmed=confirmed,
            block_height=block_height,
            block_hash=block_hash,
            block_time=block_time,
            first_seen_at=now,
            event_time=block_time if confirmed and block_time else now,
            detected_via=detected_via,
            source=source,
            enriched=False,
            upstream_missing=False,
        )
        session.add(row)
        return row, "new"

    if confirmed and (not row.confirmed or row.block_hash != block_hash):
        was_confirmed = row.confirmed
        row.confirmed = True
        row.block_height = block_height
        row.block_hash = block_hash
        row.block_time = block_time
        row.event_time = block_time or row.event_time
        row.upstream_missing = False
        if fee_sat is not None:
            row.fee_sat = fee_sat
        if vsize is not None:
            row.vsize = vsize
        return row, "updated" if was_confirmed else "confirmed"
    return row, None


def apply_enrichment(row: WhaleTx, e: Enrichment, now: datetime | None = None) -> None:
    row.enriched = True
    row.enriched_at = now or datetime.now(UTC)
    row.input_count = e.input_count
    row.output_count = e.output_count
    row.input_sum_sat = e.input_sum_sat
    row.largest_output_sat = e.largest_output_sat
    row.input_address_count = e.input_address_count
    row.output_address_count = e.output_address_count
    row.returned_to_input_sat = e.returned_to_input_sat
    row.unknown_address_output_count = e.unknown_address_output_count


def facts(row: WhaleTx) -> WhaleFacts:
    return WhaleFacts(
        value_sat=row.value_sat,
        fee_sat=row.fee_sat,
        confirmed=row.confirmed,
        block_height=row.block_height,
        enriched=row.enriched,
        input_count=row.input_count,
        output_count=row.output_count,
        input_sum_sat=row.input_sum_sat,
        largest_output_sat=row.largest_output_sat,
        input_address_count=row.input_address_count,
        output_address_count=row.output_address_count,
        returned_to_input_sat=row.returned_to_input_sat,
        unknown_address_output_count=row.unknown_address_output_count,
        upstream_missing=row.upstream_missing,
    )


async def scanned_blocks(session: AsyncSession, heights: list[int]) -> dict[int, str]:
    if not heights:
        return {}
    rows = await session.execute(
        select(WhaleScannedBlock.height, WhaleScannedBlock.hash).where(
            WhaleScannedBlock.height.in_(heights)
        )
    )
    return {h: hsh for h, hsh in rows.all()}


async def mark_scanned(
    session: AsyncSession, height: int, block_hash: str, tx_count: int, whales: int, source: str
) -> None:
    row = await session.get(WhaleScannedBlock, height)
    now = datetime.now(UTC)
    if row is None:
        session.add(
            WhaleScannedBlock(
                height=height,
                hash=block_hash,
                tx_count=tx_count,
                whale_count=whales,
                scanned_at=now,
                source=source,
            )
        )
    else:
        row.hash, row.tx_count, row.whale_count, row.scanned_at, row.source = (
            block_hash,
            tx_count,
            whales,
            now,
            source,
        )


async def pending_enrichment(session: AsyncSession, limit: int) -> list[WhaleTx]:
    rows = await session.execute(
        select(WhaleTx)
        .where(WhaleTx.enriched.is_(False), WhaleTx.upstream_missing.is_(False))
        .order_by(WhaleTx.value_sat.desc())
        .limit(limit)
    )
    return list(rows.scalars())


# ---------------------------------------------------------------- queries


@dataclass
class WhaleFilter:
    min_btc: float | None = None
    max_btc: float | None = None
    since: datetime | None = None
    until: datetime | None = None
    status: Literal["all", "confirmed", "unconfirmed"] = "all"
    sort: Literal["time", "value"] = "time"


def _apply(stmt: Select, f: WhaleFilter) -> Select:  # type: ignore[type-arg]
    if f.min_btc is not None:
        stmt = stmt.where(WhaleTx.value_sat >= int(f.min_btc * SATS))
    if f.max_btc is not None:
        stmt = stmt.where(WhaleTx.value_sat < int(f.max_btc * SATS))
    if f.since is not None:
        stmt = stmt.where(WhaleTx.event_time >= f.since)
    if f.until is not None:
        stmt = stmt.where(WhaleTx.event_time < f.until)
    if f.status == "confirmed":
        stmt = stmt.where(WhaleTx.confirmed.is_(True))
    elif f.status == "unconfirmed":
        stmt = stmt.where(WhaleTx.confirmed.is_(False))
    return stmt


async def query_whales(
    session: AsyncSession, f: WhaleFilter, limit: int, offset: int
) -> tuple[list[WhaleTx], int]:
    total = int((await session.execute(_apply(select(func.count(WhaleTx.txid)), f))).scalar_one())
    order: list[UnaryExpression[Any]] = (
        [WhaleTx.value_sat.desc(), WhaleTx.event_time.desc()]
        if f.sort == "value"
        else [WhaleTx.event_time.desc(), WhaleTx.value_sat.desc()]
    )
    rows = await session.execute(
        _apply(select(WhaleTx), f).order_by(*order).limit(limit).offset(offset)
    )
    return list(rows.scalars()), total


async def whales_since(session: AsyncSession, since: datetime) -> list[WhaleTx]:
    rows = await session.execute(select(WhaleTx).where(WhaleTx.event_time >= since))
    return list(rows.scalars())


async def coverage(session: AsyncSession) -> dict[str, object]:
    row = (
        await session.execute(
            select(
                func.count(WhaleScannedBlock.height),
                func.min(WhaleScannedBlock.height),
                func.max(WhaleScannedBlock.height),
                func.max(WhaleScannedBlock.scanned_at),
            )
        )
    ).one()
    covered_since = (
        await session.execute(
            select(func.min(BlockRecord.timestamp)).join(
                WhaleScannedBlock, WhaleScannedBlock.height == BlockRecord.height
            )
        )
    ).scalar_one()
    return {
        "coverage_since": as_utc(covered_since),
        "blocks_scanned": int(row[0] or 0),
        "lowest_height": row[1],
        "highest_height": row[2],
        "last_scan_at": as_utc(row[3]),
    }


# ----------------------------------------------------------------- alerts


async def evaluate_alerts(session: AsyncSession, whale: WhaleTx) -> list[AlertEvent]:
    rules = (
        await session.execute(
            select(AlertRule).where(
                AlertRule.enabled.is_(True), AlertRule.min_btc * SATS <= whale.value_sat
            )
        )
    ).scalars()
    created: list[AlertEvent] = []
    for rule in rules:
        if not whale.confirmed and not rule.include_unconfirmed:
            continue
        exists = await session.execute(
            select(AlertEvent.id).where(
                AlertEvent.rule_id == rule.id, AlertEvent.txid == whale.txid
            )
        )
        if exists.first() is not None:
            continue
        event = AlertEvent(
            rule_id=rule.id,
            rule_name=rule.name,
            rule_min_btc=rule.min_btc,
            txid=whale.txid,
            value_sat=whale.value_sat,
            confirmed=whale.confirmed,
            triggered_at=datetime.now(UTC),
        )
        session.add(event)
        created.append(event)
    return created
