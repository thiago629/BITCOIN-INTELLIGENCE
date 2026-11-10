"""Esplora REST API provider (blockstream.info and compatible servers).

Reference: https://github.com/Blockstream/esplora/blob/master/API.md
"""

import math
from datetime import UTC, datetime
from typing import Any

from app.domain.models import (
    AddressInfo,
    AddressStats,
    AddressTx,
    Block,
    FeeEstimates,
    FeeMethod,
    MempoolRecentTx,
    MempoolStats,
    Transaction,
    TxInput,
    TxOutput,
    TxStatus,
)
from app.providers.base import BlockchainProvider, Capability
from app.providers.errors import ProviderBadResponse
from app.providers.http import ProviderHttpClient


def ts(value: int | None) -> datetime | None:
    return datetime.fromtimestamp(value, UTC) if value is not None else None


class EsploraProvider(BlockchainProvider):
    capabilities = frozenset(
        {
            Capability.TIP,
            Capability.BLOCKS,
            Capability.TRANSACTIONS,
            Capability.ADDRESSES,
            Capability.MEMPOOL,
            Capability.MEMPOOL_RECENT,
            Capability.FEES,
        }
    )

    def __init__(self, http: ProviderHttpClient, key: str, display_name: str) -> None:
        self.http = http
        self.key = key
        self.display_name = display_name

    # ---- parsing helpers -------------------------------------------------
    def _guard(self, fn: Any, payload: Any) -> Any:
        try:
            return fn(payload)
        except (KeyError, TypeError, ValueError) as exc:
            raise ProviderBadResponse(
                self.key, f"unexpected response format ({type(exc).__name__}: {exc})"
            ) from exc

    @staticmethod
    def parse_block(raw: dict[str, Any]) -> Block:
        return Block(
            hash=raw["id"],
            height=raw["height"],
            timestamp=ts(raw["timestamp"]),
            median_time=ts(raw.get("mediantime")),
            tx_count=raw["tx_count"],
            size=raw["size"],
            weight=raw["weight"],
            version=raw.get("version"),
            merkle_root=raw.get("merkle_root"),
            previous_block_hash=raw.get("previousblockhash"),
            nonce=raw.get("nonce"),
            bits=raw.get("bits"),
            difficulty=raw.get("difficulty"),
        )

    @staticmethod
    def parse_status(raw: dict[str, Any]) -> TxStatus:
        return TxStatus(
            confirmed=bool(raw.get("confirmed")),
            block_height=raw.get("block_height"),
            block_hash=raw.get("block_hash"),
            block_time=ts(raw.get("block_time")),
        )

    @classmethod
    def parse_tx(cls, raw: dict[str, Any]) -> Transaction:
        inputs: list[TxInput] = []
        for vin in raw["vin"]:
            prevout = vin.get("prevout") or {}
            is_coinbase = bool(vin.get("is_coinbase"))
            inputs.append(
                TxInput(
                    prev_txid=None if is_coinbase else vin.get("txid"),
                    prev_vout=None if is_coinbase else vin.get("vout"),
                    is_coinbase=is_coinbase,
                    address=prevout.get("scriptpubkey_address"),
                    value_sat=prevout.get("value"),
                    script_type=prevout.get("scriptpubkey_type"),
                )
            )
        outputs = [
            TxOutput(
                index=i,
                address=vout.get("scriptpubkey_address"),
                value_sat=vout["value"],
                script_type=vout.get("scriptpubkey_type"),
            )
            for i, vout in enumerate(raw["vout"])
        ]
        weight = raw["weight"]
        vsize = math.ceil(weight / 4)
        fee = raw.get("fee")
        is_coinbase_tx = any(i.is_coinbase for i in inputs)
        total_in: int | None
        if is_coinbase_tx or any(i.value_sat is None for i in inputs):
            total_in = None
        else:
            total_in = sum(i.value_sat or 0 for i in inputs)
        return Transaction(
            txid=raw["txid"],
            version=raw["version"],
            locktime=raw["locktime"],
            size=raw["size"],
            weight=weight,
            vsize=vsize,
            fee_sat=fee,
            fee_rate=round(fee / vsize, 2) if fee is not None and vsize else None,
            status=cls.parse_status(raw.get("status") or {}),
            inputs=inputs,
            outputs=outputs,
            total_input_sat=total_in,
            total_output_sat=sum(o.value_sat for o in outputs),
        )

    @staticmethod
    def _parse_addr_stats(raw: dict[str, Any]) -> AddressStats:
        return AddressStats(
            funded_txo_count=raw["funded_txo_count"],
            funded_sum_sat=raw["funded_txo_sum"],
            spent_txo_count=raw["spent_txo_count"],
            spent_sum_sat=raw["spent_txo_sum"],
            tx_count=raw["tx_count"],
        )

    @classmethod
    def parse_address(cls, raw: dict[str, Any]) -> AddressInfo:
        chain = cls._parse_addr_stats(raw["chain_stats"])
        mempool = cls._parse_addr_stats(raw["mempool_stats"])
        return AddressInfo(
            address=raw["address"],
            chain=chain,
            mempool=mempool,
            confirmed_balance_sat=chain.funded_sum_sat - chain.spent_sum_sat,
            unconfirmed_delta_sat=mempool.funded_sum_sat - mempool.spent_sum_sat,
        )

    @classmethod
    def parse_address_tx(cls, address: str, raw: dict[str, Any]) -> AddressTx:
        received = sum(v["value"] for v in raw["vout"] if v.get("scriptpubkey_address") == address)
        sent = sum(
            (vin.get("prevout") or {}).get("value", 0)
            for vin in raw["vin"]
            if (vin.get("prevout") or {}).get("scriptpubkey_address") == address
        )
        return AddressTx(
            txid=raw["txid"],
            status=cls.parse_status(raw.get("status") or {}),
            fee_sat=raw.get("fee"),
            received_sat=received,
            sent_sat=sent,
            net_sat=received - sent,
        )

    # ---- operations ------------------------------------------------------
    async def get_tip_height(self) -> int:
        text = await self.http.get_text("/blocks/tip/height")
        return self._guard(int, text)

    async def get_recent_blocks(self, start_height: int | None = None) -> list[Block]:
        path = "/blocks" if start_height is None else f"/blocks/{start_height}"
        raw = await self.http.get_json(path)
        return self._guard(lambda r: [self.parse_block(b) for b in r], raw)

    async def get_block(self, block_hash: str) -> Block:
        raw = await self.http.get_json(f"/block/{block_hash}")
        return self._guard(self.parse_block, raw)

    async def get_block_hash(self, height: int) -> str:
        return await self.http.get_text(f"/block-height/{height}")

    async def get_block_txs(self, block_hash: str, start_index: int = 0) -> list[Transaction]:
        raw = await self.http.get_json(f"/block/{block_hash}/txs/{start_index}")
        return self._guard(lambda r: [self.parse_tx(t) for t in r], raw)

    async def get_transaction(self, txid: str) -> Transaction:
        raw = await self.http.get_json(f"/tx/{txid}")
        return self._guard(self.parse_tx, raw)

    async def get_address(self, address: str) -> AddressInfo:
        raw = await self.http.get_json(f"/address/{address}")
        return self._guard(self.parse_address, raw)

    async def get_address_txs(self, address: str, after_txid: str | None = None) -> list[AddressTx]:
        path = (
            f"/address/{address}/txs"
            if after_txid is None
            else f"/address/{address}/txs/chain/{after_txid}"
        )
        raw = await self.http.get_json(path)
        return self._guard(lambda r: [self.parse_address_tx(address, t) for t in r], raw)

    async def get_mempool_stats(self) -> MempoolStats:
        raw = await self.http.get_json("/mempool")

        def parse(r: dict[str, Any]) -> MempoolStats:
            return MempoolStats(
                count=r["count"],
                vsize=r["vsize"],
                total_fee_sat=int(r["total_fee"]),
                fee_histogram=[(float(rate), int(vs)) for rate, vs in r["fee_histogram"]],
            )

        return self._guard(parse, raw)

    async def get_recent_mempool_txs(self) -> list[MempoolRecentTx]:
        raw = await self.http.get_json("/mempool/recent")
        return self._guard(
            lambda r: [
                MempoolRecentTx(
                    txid=t["txid"], fee_sat=t["fee"], vsize=t["vsize"], value_sat=t["value"]
                )
                for t in r
            ],
            raw,
        )

    async def get_fee_estimates(self) -> FeeEstimates:
        raw = await self.http.get_json("/fee-estimates")

        def parse(r: dict[str, Any]) -> FeeEstimates:
            targets = {int(k): float(v) for k, v in r.items()}
            if not targets:
                raise ValueError("empty fee estimates")

            def at(target: int) -> float:
                # Use the closest available target at or above the requested one.
                eligible = sorted(t for t in targets if t >= target)
                key = eligible[0] if eligible else max(targets)
                return round(targets[key], 2)

            return FeeEstimates(
                fastest=at(1),
                half_hour=at(3),
                hour=at(6),
                economy=at(144),
                minimum=at(1008),
                method=FeeMethod.TARGET_ESTIMATES,
            )

        return self._guard(parse, raw)
