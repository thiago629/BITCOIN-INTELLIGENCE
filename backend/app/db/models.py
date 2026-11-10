"""Persistent storage for history that public APIs do not keep for us.

* ``blocks``: per-block statistics (basis for historical charts and the
  anomaly-detection baselines in later phases).
* ``network_snapshots``: periodic mempool / fee snapshots (time series).
* ``ingestion_runs``: audit log of every ingestion cycle.
"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Float, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class BlockRecord(Base):
    __tablename__ = "blocks"

    height: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    tx_count: Mapped[int] = mapped_column(Integer)
    size: Mapped[int] = mapped_column(Integer)
    weight: Mapped[int] = mapped_column(Integer)
    difficulty: Mapped[float | None] = mapped_column(Float, nullable=True)
    total_fees_sat: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    reward_sat: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    median_fee_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_fee_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    source: Mapped[str] = mapped_column(String(64))
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class NetworkSnapshot(Base):
    __tablename__ = "network_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    tip_height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    mempool_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    mempool_vsize: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    mempool_total_fee_sat: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    fee_fastest: Mapped[float | None] = mapped_column(Float, nullable=True)
    fee_half_hour: Mapped[float | None] = mapped_column(Float, nullable=True)
    fee_hour: Mapped[float | None] = mapped_column(Float, nullable=True)
    fee_economy: Mapped[float | None] = mapped_column(Float, nullable=True)
    source: Mapped[str] = mapped_column(String(128))


class WhaleTx(Base):
    """A large transaction detected by the Whale Tracker.

    ``value_sat`` is the sum of all outputs: it is an observed fact but it
    includes change returned to the sender, so it is an upper bound of the
    economic amount transferred. Columns from ``input_count`` onward are only
    filled once the full transaction has been analysed (``enriched``).
    """

    __tablename__ = "whale_txs"

    txid: Mapped[str] = mapped_column(String(64), primary_key=True)
    value_sat: Mapped[int] = mapped_column(BigInteger, index=True)
    fee_sat: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    vsize: Mapped[int | None] = mapped_column(Integer, nullable=True)
    confirmed: Mapped[bool] = mapped_column(index=True)
    block_height: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    block_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    block_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # Time used for ordering/filtering: block time if confirmed, else first seen.
    event_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    detected_via: Mapped[str] = mapped_column(String(16))  # block | mempool
    source: Mapped[str] = mapped_column(String(64))

    enriched: Mapped[bool] = mapped_column(default=False, index=True)
    # The data source no longer knows this txid (e.g. replaced or evicted
    # from the mempool before confirmation).
    upstream_missing: Mapped[bool] = mapped_column(default=False)
    enriched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    input_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    input_sum_sat: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    largest_output_sat: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    input_address_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_address_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    returned_to_input_sat: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    unknown_address_output_count: Mapped[int | None] = mapped_column(Integer, nullable=True)


class WhaleScannedBlock(Base):
    """Blocks already scanned by the Whale Tracker (coverage + audit)."""

    __tablename__ = "whale_scanned_blocks"

    height: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    hash: Mapped[str] = mapped_column(String(64))
    tx_count: Mapped[int] = mapped_column(Integer)
    whale_count: Mapped[int] = mapped_column(Integer)
    scanned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    source: Mapped[str] = mapped_column(String(64))


class AlertRule(Base):
    __tablename__ = "alert_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(80))
    min_btc: Mapped[float] = mapped_column(Float)
    include_unconfirmed: Mapped[bool] = mapped_column(default=True)
    enabled: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AlertEvent(Base):
    __tablename__ = "alert_events"
    __table_args__ = (UniqueConstraint("rule_id", "txid", name="uq_alert_rule_tx"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Kept (as NULL) when the rule is deleted; the name is snapshotted.
    rule_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    rule_name: Mapped[str] = mapped_column(String(80))
    rule_min_btc: Mapped[float] = mapped_column(Float)
    txid: Mapped[str] = mapped_column(String(64), index=True)
    value_sat: Mapped[int] = mapped_column(BigInteger)
    confirmed: Mapped[bool] = mapped_column()
    triggered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class IngestionRun(Base):
    __tablename__ = "ingestion_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(16))  # success | partial | failed
    blocks_stored: Mapped[int] = mapped_column(Integer, default=0)
    snapshot_stored: Mapped[bool] = mapped_column(default=False)
    sources: Mapped[str | None] = mapped_column(String(128), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
