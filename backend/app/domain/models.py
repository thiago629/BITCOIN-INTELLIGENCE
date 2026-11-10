"""Provider-independent domain models.

Every provider maps its own payloads into these models, so the rest of the
platform (API, ingestion, future analytics modules) never depends on the shape
of a specific third-party API. Amounts are always integers in satoshis.
"""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class Block(BaseModel):
    hash: str
    height: int
    timestamp: datetime
    median_time: datetime | None = None
    tx_count: int
    size: int
    weight: int
    version: int | None = None
    merkle_root: str | None = None
    previous_block_hash: str | None = None
    nonce: int | None = None
    bits: int | None = None
    difficulty: float | None = None
    # Optional enrichment (only some providers expose it). None = unknown.
    total_fees_sat: int | None = None
    reward_sat: int | None = None
    median_fee_rate: float | None = Field(default=None, description="sat/vB")
    avg_fee_rate: float | None = Field(default=None, description="sat/vB")


class TxStatus(BaseModel):
    confirmed: bool
    block_height: int | None = None
    block_hash: str | None = None
    block_time: datetime | None = None


class TxInput(BaseModel):
    prev_txid: str | None
    prev_vout: int | None
    is_coinbase: bool = False
    address: str | None = None
    value_sat: int | None = None
    script_type: str | None = None


class TxOutput(BaseModel):
    index: int
    address: str | None = None
    value_sat: int
    script_type: str | None = None


class Transaction(BaseModel):
    txid: str
    version: int
    locktime: int
    size: int
    weight: int
    vsize: int
    fee_sat: int | None
    fee_rate: float | None = Field(default=None, description="sat/vB")
    status: TxStatus
    inputs: list[TxInput]
    outputs: list[TxOutput]
    total_input_sat: int | None
    total_output_sat: int


class AddressStats(BaseModel):
    funded_txo_count: int
    funded_sum_sat: int
    spent_txo_count: int
    spent_sum_sat: int
    tx_count: int


class AddressInfo(BaseModel):
    address: str
    chain: AddressStats
    mempool: AddressStats
    confirmed_balance_sat: int
    unconfirmed_delta_sat: int


class AddressTx(BaseModel):
    """A transaction as seen from one address (net effect on that address)."""

    txid: str
    status: TxStatus
    fee_sat: int | None
    received_sat: int
    sent_sat: int
    net_sat: int


class MempoolStats(BaseModel):
    count: int
    vsize: int
    total_fee_sat: int
    fee_histogram: list[tuple[float, int]] = Field(
        description="[fee_rate sat/vB, vsize] buckets, highest fee rate first"
    )


class FeeMethod(StrEnum):
    RECOMMENDED = "recommended"  # provider's own recommendation endpoint
    TARGET_ESTIMATES = "target_estimates"  # derived from confirmation-target estimates


class FeeEstimates(BaseModel):
    fastest: float
    half_hour: float
    hour: float
    economy: float
    minimum: float
    method: FeeMethod


class DifficultyAdjustment(BaseModel):
    progress_percent: float
    difficulty_change_percent: float
    estimated_retarget_date: datetime
    remaining_blocks: int
    next_retarget_height: int
    previous_retarget_percent: float | None = None


class MempoolRecentTx(BaseModel):
    txid: str
    fee_sat: int
    vsize: int
    value_sat: int
