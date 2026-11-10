"""Network state endpoints (mempool, fees, difficulty, composite summary)."""

import asyncio
from collections.abc import Awaitable, Callable
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.deps import get_service
from app.api.schemas import ApiResponse, Section, envelope
from app.domain.models import DifficultyAdjustment, FeeEstimates, MempoolRecentTx, MempoolStats
from app.providers.errors import AllProvidersFailed, ProviderError
from app.services.blockchain import BlockchainService, Result

router = APIRouter(prefix="/network", tags=["network"])
Service = Annotated[BlockchainService, Depends(get_service)]


@router.get("/tip", response_model=ApiResponse[int])
async def tip(service: Service) -> Any:
    return envelope(await service.get_tip_height())


@router.get("/mempool", response_model=ApiResponse[MempoolStats])
async def mempool(service: Service) -> Any:
    return envelope(await service.get_mempool_stats())


@router.get("/mempool/recent", response_model=ApiResponse[list[MempoolRecentTx]])
async def mempool_recent(service: Service) -> Any:
    return envelope(await service.get_recent_mempool_txs())


@router.get("/fees", response_model=ApiResponse[FeeEstimates])
async def fees(service: Service) -> Any:
    return envelope(await service.get_fee_estimates())


@router.get("/difficulty", response_model=ApiResponse[DifficultyAdjustment])
async def difficulty(service: Service) -> Any:
    return envelope(await service.get_difficulty_adjustment())


class NetworkSummary(BaseModel):
    tip_height: Section[int]
    mempool: Section[MempoolStats]
    fees: Section[FeeEstimates]
    difficulty: Section[DifficultyAdjustment]


async def _section(call: Callable[[], Awaitable[Result[Any]]]) -> Section[Any]:
    try:
        res = await call()
        return Section(data=res.data, meta=res.meta)
    except (ProviderError, AllProvidersFailed) as exc:
        return Section(error=str(exc))


@router.get("/summary", response_model=NetworkSummary)
async def summary(service: Service) -> Any:
    """Dashboard overview. Each section succeeds or fails independently."""
    tip_s, mempool_s, fees_s, diff_s = await asyncio.gather(
        _section(service.get_tip_height),
        _section(service.get_mempool_stats),
        _section(service.get_fee_estimates),
        _section(service.get_difficulty_adjustment),
    )
    return NetworkSummary(tip_height=tip_s, mempool=mempool_s, fees=fees_s, difficulty=diff_s)
