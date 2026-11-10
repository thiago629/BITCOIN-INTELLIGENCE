"""FastAPI application factory for BITCOIN INTELLIGENCE."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import explorer, history, network, system
from app.core.config import APP_VERSION, Settings, get_settings
from app.core.logging import configure_logging
from app.core.middleware import RateLimitMiddleware, RequestContextMiddleware
from app.db.session import Database
from app.ingestion.worker import IngestionWorker
from app.providers.errors import (
    AllProvidersFailed,
    CapabilityNotSupported,
    ProviderError,
    ProviderNotFound,
)
from app.providers.registry import build_providers
from app.services.blockchain import BlockchainService

logger = logging.getLogger(__name__)


def _error(status: int, code: str, message: str, details: list[str] | None = None) -> JSONResponse:
    body: dict[str, object] = {"code": code, "message": message}
    if details:
        body["details"] = details
    return JSONResponse(status_code=status, content={"error": body})


def create_app(
    settings: Settings | None = None,
    http_transport: httpx.AsyncBaseTransport | None = None,
) -> FastAPI:
    """Build the app. ``http_transport`` lets tests inject a mock upstream."""
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        configure_logging(settings.log_level)
        client = httpx.AsyncClient(
            timeout=settings.http_timeout_s,
            transport=http_transport,
            headers={"User-Agent": f"BitcoinIntelligence/{APP_VERSION}"},
            follow_redirects=False,
        )
        service = BlockchainService(
            build_providers(settings, client),
            failure_threshold=settings.provider_failure_threshold,
            cooldown_s=settings.provider_cooldown_s,
        )
        db = Database(settings.database_url)
        await db.create_all()
        app.state.settings = settings
        app.state.service = service
        app.state.db = db
        worker: IngestionWorker | None = None
        if settings.ingestion_enabled:
            worker = IngestionWorker(
                service,
                db,
                interval_s=settings.ingestion_interval_s,
                backfill_blocks=settings.ingestion_backfill_blocks,
                max_pages=settings.ingestion_max_pages_per_run,
            )
            worker.start()
        app.state.worker = worker
        logger.info(
            "startup",
            extra={
                "version": APP_VERSION,
                "providers": settings.providers,
                "database": db.backend_name,
                "ingestion": settings.ingestion_enabled,
            },
        )
        try:
            yield
        finally:
            if worker:
                await worker.stop()
            await client.aclose()
            await db.dispose()
            logger.info("shutdown")

    app = FastAPI(
        title=settings.app_name,
        version=APP_VERSION,
        lifespan=lifespan,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        redoc_url=None,
    )

    app.add_middleware(RateLimitMiddleware, limit_per_minute=settings.rate_limit_per_minute)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET"],
        allow_headers=["*"],
    )
    app.add_middleware(RequestContextMiddleware)

    @app.exception_handler(ProviderNotFound)
    async def not_found(_: Request, exc: ProviderNotFound) -> JSONResponse:
        return _error(404, "not_found", "The requested object was not found on the blockchain")

    @app.exception_handler(CapabilityNotSupported)
    async def unsupported(_: Request, exc: CapabilityNotSupported) -> JSONResponse:
        return _error(501, "not_supported", "No configured data source supports this operation")

    @app.exception_handler(AllProvidersFailed)
    async def upstream_down(_: Request, exc: AllProvidersFailed) -> JSONResponse:
        return _error(
            503,
            "upstream_unavailable",
            "Data sources are currently unavailable. "
            "No data is shown rather than stale or invented data.",
            [str(e) for e in exc.errors],
        )

    @app.exception_handler(ProviderError)
    async def provider_error(_: Request, exc: ProviderError) -> JSONResponse:
        return _error(502, "upstream_error", "Unexpected answer from the data source", [str(exc)])

    prefix = "/api/v1"
    app.include_router(system.router, prefix=prefix)
    app.include_router(network.router, prefix=prefix)
    app.include_router(explorer.router, prefix=prefix)
    app.include_router(history.router, prefix=prefix)
    return app


app = create_app()
