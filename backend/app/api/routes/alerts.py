"""Alert rules (configurable thresholds) and triggered alert events."""

import hmac
import logging
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select, update

from app.api.deps import get_db
from app.db.models import AlertEvent, AlertRule
from app.db.repository import as_utc
from app.db.session import Database

router = APIRouter(prefix="/alerts", tags=["alerts"])
Db = Annotated[Database, Depends(get_db)]
audit = logging.getLogger("app.audit")


def require_writer(request: Request, x_api_key: Annotated[str | None, Header()] = None) -> None:
    """Write access: admin API key; open only in development without a key.

    Full user authentication arrives in Phase 5. Until then, any environment
    other than ``development`` must set ``BI_ADMIN_API_KEY``.
    """
    settings = request.app.state.settings
    expected = settings.admin_api_key
    if expected:
        if not x_api_key or not hmac.compare_digest(x_api_key, expected):
            raise HTTPException(401, "Valid X-API-Key header required")
        return
    if settings.environment != "development":
        raise HTTPException(403, "Write operations are disabled: BI_ADMIN_API_KEY is not set")


Writer = Annotated[None, Depends(require_writer)]


class RuleIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    min_btc: float = Field(gt=0, le=21_000_000)
    include_unconfirmed: bool = True
    enabled: bool = True

    @field_validator("name")
    @classmethod
    def strip_name(cls, v: str) -> str:
        v = " ".join(v.split())
        if not v:
            raise ValueError("name must not be blank")
        return v


class RulePatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    min_btc: float | None = Field(default=None, gt=0, le=21_000_000)
    include_unconfirmed: bool | None = None
    enabled: bool | None = None


class RuleOut(BaseModel):
    id: int
    name: str
    min_btc: float
    include_unconfirmed: bool
    enabled: bool
    created_at: datetime
    updated_at: datetime
    events_count: int


class EventOut(BaseModel):
    id: int
    rule_id: int | None
    rule_name: str
    rule_min_btc: float
    txid: str
    value_sat: int
    confirmed: bool
    triggered_at: datetime


class EventList(BaseModel):
    data: list[EventOut]
    total: int
    generated_at: datetime
    source: str = "database"


def _check_threshold(request: Request, min_btc: float) -> None:
    floor = request.app.state.settings.whale_min_btc
    if min_btc < floor:
        raise HTTPException(
            422,
            f"min_btc must be >= {floor} BTC: smaller transactions are not tracked "
            "(BI_WHALE_MIN_BTC)",
        )


async def _rule_out(db: Database, rule: AlertRule) -> RuleOut:
    async with db.session() as session:
        count = (
            await session.execute(
                select(func.count(AlertEvent.id)).where(AlertEvent.rule_id == rule.id)
            )
        ).scalar_one()
    return RuleOut(
        id=rule.id,
        name=rule.name,
        min_btc=rule.min_btc,
        include_unconfirmed=rule.include_unconfirmed,
        enabled=rule.enabled,
        created_at=as_utc(rule.created_at),  # type: ignore[arg-type]
        updated_at=as_utc(rule.updated_at),  # type: ignore[arg-type]
        events_count=int(count),
    )


@router.get("/rules", response_model=list[RuleOut])
async def list_rules(db: Db) -> Any:
    async with db.session() as session:
        rules = list((await session.execute(select(AlertRule).order_by(AlertRule.id))).scalars())
    return [await _rule_out(db, r) for r in rules]


@router.post("/rules", response_model=RuleOut, status_code=201)
async def create_rule(body: RuleIn, request: Request, db: Db, _: Writer) -> Any:
    _check_threshold(request, body.min_btc)
    now = datetime.now(UTC)
    async with db.session() as session:
        if (await session.execute(select(func.count(AlertRule.id)))).scalar_one() >= 100:
            raise HTTPException(422, "Maximum of 100 alert rules reached")
        rule = AlertRule(**body.model_dump(), created_at=now, updated_at=now)
        session.add(rule)
        await session.commit()
    audit.info("alert_rule_created", extra={"rule_id": rule.id, "min_btc": rule.min_btc})
    return await _rule_out(db, rule)


@router.patch("/rules/{rule_id}", response_model=RuleOut)
async def update_rule(rule_id: int, body: RulePatch, request: Request, db: Db, _: Writer) -> Any:
    changes = body.model_dump(exclude_unset=True, exclude_none=True)
    if "min_btc" in changes:
        _check_threshold(request, changes["min_btc"])
    if "name" in changes:
        changes["name"] = RuleIn.strip_name(changes["name"])
    async with db.session() as session:
        rule = await session.get(AlertRule, rule_id)
        if rule is None:
            raise HTTPException(404, "Alert rule not found")
        for k, v in changes.items():
            setattr(rule, k, v)
        rule.updated_at = datetime.now(UTC)
        await session.commit()
    audit.info("alert_rule_updated", extra={"rule_id": rule_id, "changes": list(changes)})
    return await _rule_out(db, rule)


@router.delete("/rules/{rule_id}", status_code=204)
async def delete_rule(rule_id: int, db: Db, _: Writer) -> Response:
    """Delete a rule. Its past alert events are kept (with the rule name)."""
    async with db.session() as session:
        rule = await session.get(AlertRule, rule_id)
        if rule is None:
            raise HTTPException(404, "Alert rule not found")
        await session.execute(
            update(AlertEvent).where(AlertEvent.rule_id == rule_id).values(rule_id=None)
        )
        await session.delete(rule)
        await session.commit()
    audit.info("alert_rule_deleted", extra={"rule_id": rule_id})
    return Response(status_code=204)


@router.get("/events", response_model=EventList)
async def list_events(
    db: Db,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0, le=100_000)] = 0,
) -> Any:
    async with db.session() as session:
        total = (await session.execute(select(func.count(AlertEvent.id)))).scalar_one()
        rows = (
            await session.execute(
                select(AlertEvent)
                .order_by(AlertEvent.triggered_at.desc(), AlertEvent.id.desc())
                .limit(limit)
                .offset(offset)
            )
        ).scalars()
        data = [
            EventOut(
                id=e.id,
                rule_id=e.rule_id,
                rule_name=e.rule_name,
                rule_min_btc=e.rule_min_btc,
                txid=e.txid,
                value_sat=e.value_sat,
                confirmed=e.confirmed,
                triggered_at=as_utc(e.triggered_at),  # type: ignore[arg-type]
            )
            for e in rows
        ]
    return EventList(data=data, total=int(total), generated_at=datetime.now(UTC))
