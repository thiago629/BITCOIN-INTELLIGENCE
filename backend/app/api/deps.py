from fastapi import Request

from app.db.session import Database
from app.ingestion.worker import IngestionWorker
from app.services.blockchain import BlockchainService


def get_service(request: Request) -> BlockchainService:
    return request.app.state.service  # type: ignore[no-any-return]


def get_db(request: Request) -> Database:
    return request.app.state.db  # type: ignore[no-any-return]


def get_worker(request: Request) -> IngestionWorker | None:
    return getattr(request.app.state, "worker", None)
