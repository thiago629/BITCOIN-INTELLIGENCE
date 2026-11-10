"""Persistent storage for history that public APIs do not keep for us.

* ``blocks``: per-block statistics (basis for historical charts and the
  anomaly-detection baselines in later phases).
* ``network_snapshots``: periodic mempool / fee snapshots (time series).
* ``ingestion_runs``: audit log of every ingestion cycle.
"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Float, Integer, String, Text
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
