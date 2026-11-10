"""Provider contract.

To add a new data source (e.g. Bitcoin Core RPC) implement this interface,
declare the capabilities it supports and register it in
``app.providers.registry``. Nothing else in the platform has to change.
"""

from abc import ABC, abstractmethod
from enum import StrEnum

from app.domain.models import (
    AddressInfo,
    AddressTx,
    Block,
    BlockTxSummary,
    DifficultyAdjustment,
    FeeEstimates,
    MempoolRecentTx,
    MempoolStats,
    Transaction,
)
from app.providers.errors import CapabilityNotSupported


class Capability(StrEnum):
    TIP = "tip"
    BLOCKS = "blocks"
    TRANSACTIONS = "transactions"
    ADDRESSES = "addresses"
    MEMPOOL = "mempool"
    MEMPOOL_RECENT = "mempool_recent"
    FEES = "fees"
    DIFFICULTY = "difficulty"
    BLOCK_SUMMARY = "block_summary"  # every tx of a block (txid/value/fee) in one call


class BlockchainProvider(ABC):
    #: Stable identifier used in configuration (e.g. "mempool").
    key: str
    #: Human readable source name shown to users (e.g. "mempool.space").
    display_name: str
    capabilities: frozenset[Capability]

    @abstractmethod
    async def get_tip_height(self) -> int: ...

    @abstractmethod
    async def get_recent_blocks(self, start_height: int | None = None) -> list[Block]:
        """Return a page of blocks, newest first, starting at ``start_height`` (or the tip)."""

    @abstractmethod
    async def get_block(self, block_hash: str) -> Block: ...

    @abstractmethod
    async def get_block_hash(self, height: int) -> str: ...

    @abstractmethod
    async def get_block_txs(self, block_hash: str, start_index: int = 0) -> list[Transaction]: ...

    @abstractmethod
    async def get_transaction(self, txid: str) -> Transaction: ...

    @abstractmethod
    async def get_address(self, address: str) -> AddressInfo: ...

    @abstractmethod
    async def get_address_txs(
        self, address: str, after_txid: str | None = None
    ) -> list[AddressTx]: ...

    async def get_mempool_stats(self) -> MempoolStats:
        raise CapabilityNotSupported(self.key, "mempool stats not supported")

    async def get_recent_mempool_txs(self) -> list[MempoolRecentTx]:
        raise CapabilityNotSupported(self.key, "recent mempool txs not supported")

    async def get_fee_estimates(self) -> FeeEstimates:
        raise CapabilityNotSupported(self.key, "fee estimates not supported")

    async def get_difficulty_adjustment(self) -> DifficultyAdjustment:
        raise CapabilityNotSupported(self.key, "difficulty adjustment not supported")

    async def get_block_summary(self, block_hash: str) -> list[BlockTxSummary]:
        """All non-coinbase transactions of a block with their output value."""
        raise CapabilityNotSupported(self.key, "block summary not supported")
