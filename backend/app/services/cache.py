"""In-process TTL cache with per-key locking (single-flight).

Concurrent requests for the same key wait for the first one instead of all
hitting the upstream API. The interface is intentionally small so it can be
swapped for Redis when the platform runs with several backend replicas.
"""

import asyncio
import time
import weakref
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class CacheEntry:
    value: Any
    source: str
    fetched_at: datetime
    fallback_used: bool
    expires_at: float  # time.monotonic() deadline


class TTLCache:
    def __init__(self, max_entries: int = 5000) -> None:
        self._data: OrderedDict[str, CacheEntry] = OrderedDict()
        self._locks: weakref.WeakValueDictionary[str, asyncio.Lock] = weakref.WeakValueDictionary()
        self._max_entries = max_entries
        self.hits = 0
        self.misses = 0

    def get(self, key: str) -> CacheEntry | None:
        entry = self._data.get(key)
        if entry is None or entry.expires_at <= time.monotonic():
            if entry is not None:
                del self._data[key]
            self.misses += 1
            return None
        self._data.move_to_end(key)
        self.hits += 1
        return entry

    def set(self, key: str, entry: CacheEntry) -> None:
        self._data[key] = entry
        self._data.move_to_end(key)
        while len(self._data) > self._max_entries:
            self._data.popitem(last=False)

    def lock(self, key: str) -> asyncio.Lock:
        lock = self._locks.get(key)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[key] = lock
        return lock

    def clear(self) -> None:
        self._data.clear()

    def __len__(self) -> int:
        return len(self._data)
