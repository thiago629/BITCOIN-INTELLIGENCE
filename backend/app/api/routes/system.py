"""Health and operational status."""

from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel

from app.api.deps import get_db, get_service, get_worker
from app.core.config import APP_VERSION
from app.db import repository as repo
from app.db.repository import as_utc
from app.db.session import Database
from app.ingestion.worker import IngestionWorker
from app.services.blockchain import BlockchainService

router = APIRouter(tags=["system"])


class ProviderStatus(BaseModel):
    key: str
    name: str
    capabilities: list[str]
    healthy: bool
    in_cooldown: bool
    cooldown_remaining_s: float
    consecutive_failures: int
    total_requests: int
    total_failures: int
    last_error: str | None
    last_success_at: datetime | None
    last_failure_at: datetime | None


class IngestionStatus(BaseModel):
    enabled: bool
    running: bool
    interval_s: float | None
    last_run_at: datetime | None
    last_status: str | None
    stored_blocks: int


class HealthResponse(BaseModel):
    status: str
    version: str
    environment: str
    time: datetime
    database: dict[str, Any]
    cache: dict[str, int]
    providers: list[ProviderStatus]
    ingestion: IngestionStatus


@router.get("/health", response_model=HealthResponse)
async def health(
    request: Request,
    service: Annotated[BlockchainService, Depends(get_service)],
    db: Annotated[Database, Depends(get_db)],
    worker: Annotated[IngestionWorker | None, Depends(get_worker)],
) -> Any:
    db_ok = await db.ping()
    stored = 0
    if db_ok:
        async with db.session() as session:
            stored = await repo.count_blocks(session)
    providers = service.provider_status()
    any_provider_ok = any(not p["in_cooldown"] for p in providers)
    status = "ok" if db_ok and any_provider_ok else "degraded"
    return HealthResponse(
        status=status,
        version=APP_VERSION,
        environment=request.app.state.settings.environment,
        time=datetime.now(UTC),
        database={"ok": db_ok, "backend": db.backend_name},
        cache={
            "entries": len(service.cache),
            "hits": service.cache.hits,
            "misses": service.cache.misses,
        },
        providers=[ProviderStatus(**p) for p in providers],
        ingestion=IngestionStatus(
            enabled=worker is not None,
            running=bool(worker and worker.running),
            interval_s=worker.interval_s if worker else None,
            last_run_at=worker.last_run_at if worker else None,
            last_status=worker.last_result.status if worker and worker.last_result else None,
            stored_blocks=stored,
        ),
    )


class IngestionRunOut(BaseModel):
    id: int
    started_at: datetime
    finished_at: datetime | None
    status: str
    blocks_stored: int
    snapshot_stored: bool
    sources: str | None
    error: str | None


@router.get("/system/ingestion-runs", response_model=list[IngestionRunOut])
async def ingestion_runs(
    db: Annotated[Database, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=200)] = 20,
) -> Any:
    async with db.session() as session:
        rows = await repo.list_runs(session, limit)
    return [
        IngestionRunOut(
            id=r.id,
            started_at=as_utc(r.started_at),  # type: ignore[arg-type]
            finished_at=as_utc(r.finished_at),
            status=r.status,
            blocks_stored=r.blocks_stored,
            snapshot_stored=r.snapshot_stored,
            sources=r.sources,
            error=r.error,
        )
        for r in rows
    ]
