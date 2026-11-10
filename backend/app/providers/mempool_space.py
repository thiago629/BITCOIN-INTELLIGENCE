"""mempool.space provider.

mempool.space implements the Esplora API and adds extra endpoints (block fee
extras, recommended fees, difficulty adjustment). Reference:
https://mempool.space/docs/api/rest
"""

from typing import Any

from app.domain.models import Block, DifficultyAdjustment, FeeEstimates, FeeMethod
from app.providers.base import Capability
from app.providers.esplora import EsploraProvider, ts


class MempoolSpaceProvider(EsploraProvider):
    capabilities = EsploraProvider.capabilities | {Capability.DIFFICULTY}

    @classmethod
    def parse_block_with_extras(cls, raw: dict[str, Any]) -> Block:
        block = cls.parse_block(raw)
        extras = raw.get("extras") or {}
        block.total_fees_sat = extras.get("totalFees")
        block.reward_sat = extras.get("reward")
        block.median_fee_rate = extras.get("medianFee")
        block.avg_fee_rate = extras.get("avgFeeRate")
        return block

    async def get_recent_blocks(self, start_height: int | None = None) -> list[Block]:
        path = "/v1/blocks" if start_height is None else f"/v1/blocks/{start_height}"
        raw = await self.http.get_json(path)
        return self._guard(lambda r: [self.parse_block_with_extras(b) for b in r], raw)

    async def get_block(self, block_hash: str) -> Block:
        raw = await self.http.get_json(f"/v1/block/{block_hash}")
        return self._guard(self.parse_block_with_extras, raw)

    async def get_fee_estimates(self) -> FeeEstimates:
        raw = await self.http.get_json("/v1/fees/recommended")
        return self._guard(
            lambda r: FeeEstimates(
                fastest=r["fastestFee"],
                half_hour=r["halfHourFee"],
                hour=r["hourFee"],
                economy=r["economyFee"],
                minimum=r["minimumFee"],
                method=FeeMethod.RECOMMENDED,
            ),
            raw,
        )

    async def get_difficulty_adjustment(self) -> DifficultyAdjustment:
        raw = await self.http.get_json("/v1/difficulty-adjustment")
        return self._guard(
            lambda r: DifficultyAdjustment(
                progress_percent=r["progressPercent"],
                difficulty_change_percent=r["difficultyChange"],
                # mempool.space returns this value in milliseconds.
                estimated_retarget_date=ts(int(r["estimatedRetargetDate"] // 1000)),
                remaining_blocks=r["remainingBlocks"],
                next_retarget_height=r["nextRetargetHeight"],
                previous_retarget_percent=r.get("previousRetarget"),
            ),
            raw,
        )
