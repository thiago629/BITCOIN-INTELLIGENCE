"""Blockchain data service: caching, provider failover and provenance.

This is the single entry point the rest of the platform uses to read Bitcoin
data. Every result carries :class:`DataMeta` describing where it came from and
when it was fetched, so the UI and future reports can always show provenance.
"""

import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Generic, TypeVar

from pydantic import BaseModel

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
from app.providers.base import BlockchainProvider, Capability
from app.providers.errors import (
    AllProvidersFailed,
    CapabilityNotSupported,
    ProviderBadResponse,
    ProviderError,
    ProviderNotFound,
    ProviderRateLimited,
    ProviderUnavailable,
)
from app.services.cache import CacheEntry, TTLCache

logger = logging.getLogger(__name__)

T = TypeVar("T")


class DataMeta(BaseModel):
    source: str
    fetched_at: datetime
    cached: bool
    age_seconds: float
    fallback_used: bool


@dataclass(frozen=True)
class Result(Generic[T]):
    data: T
    meta: DataMeta


@dataclass
class ProviderHealth:
    consecutive_failures: int = 0
    cooldown_until: float = 0.0
    last_error: str | None = None
    last_success_at: datetime | None = None
    last_failure_at: datetime | None = None
    total_requests: int = 0
    total_failures: int = 0


@dataclass
class TTLPolicy:
    tip: float = 10
    recent_blocks: float = 20
    block: float = 600
    block_txs: float = 600
    tx_confirmed: float = 600
    tx_unconfirmed: float = 15
    address: float = 30
    mempool: float = 10
    mempool_recent: float = 10
    fees: float = 15
    difficulty: float = 60
    block_summary: float = 600
    extra: dict[str, float] = field(default_factory=dict)


class BlockchainService:
    def __init__(
        self,
        providers: list[BlockchainProvider],
        cache: TTLCache | None = None,
        ttl: TTLPolicy | None = None,
        failure_threshold: int = 3,
        cooldown_s: float = 30.0,
    ) -> None:
        if not providers:
            raise ValueError("BlockchainService needs at least one provider")
        self.providers = providers
        self.cache = cache or TTLCache()
        self.ttl = ttl or TTLPolicy()
        self.failure_threshold = failure_threshold
        self.cooldown_s = cooldown_s
        self.health: dict[str, ProviderHealth] = {p.key: ProviderHealth() for p in providers}

    # ------------------------------------------------------------------ core
    async def _fetch(
        self,
        key: str,
        capability: Capability,
        ttl: float | Callable[[Any], float],
        op: Callable[[BlockchainProvider], Awaitable[T]],
    ) -> Result[T]:
        hit = self._from_cache(key)
        if hit is not None:
            return hit
        async with self.cache.lock(key):
            hit = self._from_cache(key)
            if hit is not None:
                return hit

            candidates = [p for p in self.providers if capability in p.capabilities]
            if not candidates:
                raise CapabilityNotSupported("service", f"no provider supports '{capability}'")

            now = time.monotonic()
            errors: list[ProviderError] = []
            for provider in candidates:
                health = self.health[provider.key]
                if health.cooldown_until > now:
                    errors.append(
                        ProviderUnavailable(
                            provider.key,
                            f"in cooldown for {health.cooldown_until - now:.0f}s "
                            f"after errors: {health.last_error}",
                        )
                    )
                    continue
                health.total_requests += 1
                try:
                    value = await op(provider)
                except ProviderNotFound:
                    self._record_success(provider)
                    raise
                except CapabilityNotSupported as exc:
                    errors.append(exc)
                    continue
                except ProviderError as exc:
                    self._record_failure(provider, exc)
                    errors.append(exc)
                    continue
                except Exception as exc:  # defensive: never let a provider bug crash the API
                    logger.exception("provider_unexpected_error", extra={"provider": provider.key})
                    wrapped = ProviderUnavailable(
                        provider.key, f"internal error: {type(exc).__name__}"
                    )
                    self._record_failure(provider, wrapped)
                    errors.append(wrapped)
                    continue

                self._record_success(provider)
                fetched_at = datetime.now(UTC)
                fallback = provider is not candidates[0]
                ttl_s = ttl(value) if callable(ttl) else ttl
                self.cache.set(
                    key,
                    CacheEntry(
                        value=value,
                        source=provider.display_name,
                        fetched_at=fetched_at,
                        fallback_used=fallback,
                        expires_at=time.monotonic() + ttl_s,
                    ),
                )
                if fallback:
                    logger.warning(
                        "provider_fallback_used",
                        extra={"operation": key, "provider": provider.key},
                    )
                return Result(
                    value,
                    DataMeta(
                        source=provider.display_name,
                        fetched_at=fetched_at,
                        cached=False,
                        age_seconds=0.0,
                        fallback_used=fallback,
                    ),
                )

            logger.error(
                "all_providers_failed",
                extra={"operation": key, "errors": [str(e) for e in errors]},
            )
            raise AllProvidersFailed(key, errors)

    def _from_cache(self, key: str) -> Result[Any] | None:
        entry = self.cache.get(key)
        if entry is None:
            return None
        age = (datetime.now(UTC) - entry.fetched_at).total_seconds()
        return Result(
            entry.value,
            DataMeta(
                source=entry.source,
                fetched_at=entry.fetched_at,
                cached=True,
                age_seconds=round(age, 2),
                fallback_used=entry.fallback_used,
            ),
        )

    def _record_success(self, provider: BlockchainProvider) -> None:
        h = self.health[provider.key]
        h.consecutive_failures = 0
        h.cooldown_until = 0.0
        h.last_success_at = datetime.now(UTC)

    def _record_failure(self, provider: BlockchainProvider, exc: ProviderError) -> None:
        h = self.health[provider.key]
        h.total_failures += 1
        h.last_error = exc.message
        h.last_failure_at = datetime.now(UTC)
        if isinstance(exc, ProviderBadResponse):
            # Endpoint-specific format problem: recorded, but it does not count
            # towards cooldown, so every other operation keeps using this provider.
            pass
        elif isinstance(exc, ProviderRateLimited):
            h.consecutive_failures += 1
            h.cooldown_until = time.monotonic() + (exc.retry_after_s or self.cooldown_s)
        else:
            h.consecutive_failures += 1
            if h.consecutive_failures >= self.failure_threshold:
                h.cooldown_until = time.monotonic() + self.cooldown_s
        logger.warning(
            "provider_failure",
            extra={
                "provider": provider.key,
                "error": exc.message,
                "consecutive_failures": h.consecutive_failures,
            },
        )

    # ------------------------------------------------------------ operations
    async def get_tip_height(self) -> Result[int]:
        return await self._fetch("tip", Capability.TIP, self.ttl.tip, lambda p: p.get_tip_height())

    async def get_recent_blocks(self, start_height: int | None = None) -> Result[list[Block]]:
        return await self._fetch(
            f"blocks:{start_height}",
            Capability.BLOCKS,
            self.ttl.recent_blocks if start_height is None else self.ttl.block,
            lambda p: p.get_recent_blocks(start_height),
        )

    async def get_block(self, block_hash: str) -> Result[Block]:
        return await self._fetch(
            f"block:{block_hash}",
            Capability.BLOCKS,
            self.ttl.block,
            lambda p: p.get_block(block_hash),
        )

    async def get_block_hash(self, height: int) -> Result[str]:
        return await self._fetch(
            f"block_hash:{height}",
            Capability.BLOCKS,
            self.ttl.block,
            lambda p: p.get_block_hash(height),
        )

    async def get_block_by_height(self, height: int) -> Result[Block]:
        block_hash = await self.get_block_hash(height)
        return await self.get_block(block_hash.data)

    async def get_block_txs(
        self, block_hash: str, start_index: int = 0
    ) -> Result[list[Transaction]]:
        return await self._fetch(
            f"block_txs:{block_hash}:{start_index}",
            Capability.BLOCKS,
            self.ttl.block_txs,
            lambda p: p.get_block_txs(block_hash, start_index),
        )

    async def get_transaction(self, txid: str) -> Result[Transaction]:
        def ttl(tx: Transaction) -> float:
            return self.ttl.tx_confirmed if tx.status.confirmed else self.ttl.tx_unconfirmed

        return await self._fetch(
            f"tx:{txid}", Capability.TRANSACTIONS, ttl, lambda p: p.get_transaction(txid)
        )

    async def get_address(self, address: str) -> Result[AddressInfo]:
        return await self._fetch(
            f"address:{address}",
            Capability.ADDRESSES,
            self.ttl.address,
            lambda p: p.get_address(address),
        )

    async def get_address_txs(
        self, address: str, after_txid: str | None = None
    ) -> Result[list[AddressTx]]:
        return await self._fetch(
            f"address_txs:{address}:{after_txid}",
            Capability.ADDRESSES,
            self.ttl.address,
            lambda p: p.get_address_txs(address, after_txid),
        )

    async def get_mempool_stats(self) -> Result[MempoolStats]:
        return await self._fetch(
            "mempool", Capability.MEMPOOL, self.ttl.mempool, lambda p: p.get_mempool_stats()
        )

    async def get_recent_mempool_txs(self) -> Result[list[MempoolRecentTx]]:
        return await self._fetch(
            "mempool_recent",
            Capability.MEMPOOL_RECENT,
            self.ttl.mempool_recent,
            lambda p: p.get_recent_mempool_txs(),
        )

    async def get_fee_estimates(self) -> Result[FeeEstimates]:
        return await self._fetch(
            "fees", Capability.FEES, self.ttl.fees, lambda p: p.get_fee_estimates()
        )

    async def get_difficulty_adjustment(self) -> Result[DifficultyAdjustment]:
        return await self._fetch(
            "difficulty",
            Capability.DIFFICULTY,
            self.ttl.difficulty,
            lambda p: p.get_difficulty_adjustment(),
        )

    async def get_block_summary(self, block_hash: str) -> Result[list[BlockTxSummary]]:
        return await self._fetch(
            f"block_summary:{block_hash}",
            Capability.BLOCK_SUMMARY,
            self.ttl.block_summary,
            lambda p: p.get_block_summary(block_hash),
        )

    # --------------------------------------------------------------- health
    def provider_status(self) -> list[dict[str, Any]]:
        now = time.monotonic()
        out = []
        for p in self.providers:
            h = self.health[p.key]
            cooldown = max(0.0, h.cooldown_until - now)
            out.append(
                {
                    "key": p.key,
                    "name": p.display_name,
                    "capabilities": sorted(c.value for c in p.capabilities),
                    "healthy": cooldown == 0 and h.consecutive_failures == 0,
                    "in_cooldown": cooldown > 0,
                    "cooldown_remaining_s": round(cooldown, 1),
                    "consecutive_failures": h.consecutive_failures,
                    "total_requests": h.total_requests,
                    "total_failures": h.total_failures,
                    "last_error": h.last_error,
                    "last_success_at": h.last_success_at,
                    "last_failure_at": h.last_failure_at,
                }
            )
        return out
