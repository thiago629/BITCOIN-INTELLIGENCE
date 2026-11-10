"""Blockchain Explorer endpoints: blocks, transactions, addresses, search."""

from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.api.deps import get_service
from app.api.schemas import HEX64, ApiResponse, BlockHash, TxId, envelope, is_valid_address
from app.domain.models import AddressInfo, AddressTx, Block, Transaction
from app.providers.errors import ProviderNotFound
from app.services.blockchain import BlockchainService

router = APIRouter(tags=["explorer"])
Service = Annotated[BlockchainService, Depends(get_service)]


def _require_address(address: str) -> str:
    if not is_valid_address(address):
        raise HTTPException(status_code=422, detail="Invalid Bitcoin mainnet address format")
    return address


@router.get("/blocks/recent", response_model=ApiResponse[list[Block]])
async def recent_blocks(
    service: Service,
    start_height: Annotated[int | None, Query(ge=0)] = None,
) -> Any:
    return envelope(await service.get_recent_blocks(start_height))


@router.get("/blocks/height/{height}", response_model=ApiResponse[Block])
async def block_by_height(height: int, service: Service) -> Any:
    if height < 0:
        raise HTTPException(status_code=422, detail="height must be >= 0")
    return envelope(await service.get_block_by_height(height))


@router.get("/blocks/{block_hash}", response_model=ApiResponse[Block])
async def block_by_hash(block_hash: BlockHash, service: Service) -> Any:
    return envelope(await service.get_block(block_hash.lower()))


@router.get("/blocks/{block_hash}/txs", response_model=ApiResponse[list[Transaction]])
async def block_txs(
    block_hash: BlockHash,
    service: Service,
    start_index: Annotated[int, Query(ge=0, le=100_000)] = 0,
) -> Any:
    if start_index % 25:
        raise HTTPException(status_code=422, detail="start_index must be a multiple of 25")
    return envelope(await service.get_block_txs(block_hash.lower(), start_index))


@router.get("/tx/{txid}", response_model=ApiResponse[Transaction])
async def transaction(txid: TxId, service: Service) -> Any:
    return envelope(await service.get_transaction(txid.lower()))


@router.get("/address/{address}", response_model=ApiResponse[AddressInfo])
async def address_info(address: str, service: Service) -> Any:
    return envelope(await service.get_address(_require_address(address)))


@router.get("/address/{address}/txs", response_model=ApiResponse[list[AddressTx]])
async def address_txs(
    address: str,
    service: Service,
    after_txid: Annotated[str | None, Query(pattern=HEX64)] = None,
) -> Any:
    return envelope(
        await service.get_address_txs(
            _require_address(address), after_txid.lower() if after_txid else None
        )
    )


class SearchResult(BaseModel):
    type: Literal["block", "transaction", "address"]
    id: str


@router.get("/search", response_model=SearchResult)
async def search(
    service: Service,
    q: Annotated[str, Query(min_length=1, max_length=100)],
) -> Any:
    """Resolve a free-text query (height, block hash, txid or address)."""
    query = q.strip()
    if query.isdigit():
        result = await service.get_block_hash(int(query))
        return SearchResult(type="block", id=result.data)
    if len(query) == 64 and all(c in "0123456789abcdefABCDEF" for c in query):
        query = query.lower()
        try:
            await service.get_transaction(query)
            return SearchResult(type="transaction", id=query)
        except ProviderNotFound:
            await service.get_block(query)  # raises ProviderNotFound -> 404
            return SearchResult(type="block", id=query)
    if is_valid_address(query):
        return SearchResult(type="address", id=query)
    raise HTTPException(
        status_code=422,
        detail="Query must be a block height, block hash, transaction id or mainnet address",
    )
