"""API envelope and validators shared by all routes."""

import re
from datetime import datetime
from typing import Annotated, Any, Generic, TypeVar

from fastapi import Path
from pydantic import BaseModel

from app.services.blockchain import DataMeta, Result

T = TypeVar("T")

HEX64 = r"^[0-9a-fA-F]{64}$"
# Mainnet only: legacy P2PKH/P2SH (base58) and bech32/bech32m (segwit v0/v1).
BASE58_ADDRESS = re.compile(r"^[13][a-km-zA-HJ-NP-Z1-9]{25,34}$")
BECH32_ADDRESS = re.compile(r"^(bc1|BC1)[02-9ac-hj-np-zAC-HJ-NP-Z]{11,87}$")

TxId = Annotated[str, Path(pattern=HEX64, description="64-char hex transaction id")]
BlockHash = Annotated[str, Path(pattern=HEX64, description="64-char hex block hash")]


def is_valid_address(value: str) -> bool:
    if BECH32_ADDRESS.match(value):
        # bech32 must not mix case
        return value == value.lower() or value == value.upper()
    return bool(BASE58_ADDRESS.match(value))


class ApiResponse(BaseModel, Generic[T]):
    data: T
    meta: DataMeta


def envelope(result: Result[Any]) -> dict[str, Any]:
    return {"data": result.data, "meta": result.meta}


class Section(BaseModel, Generic[T]):
    """A piece of a composite response that may be independently unavailable."""

    data: T | None = None
    meta: DataMeta | None = None
    error: str | None = None


class ErrorBody(BaseModel):
    code: str
    message: str
    details: list[str] | None = None


class StoredMeta(BaseModel):
    """Provenance for data served from our own database."""

    source: str = "database"
    generated_at: datetime
    records: int
