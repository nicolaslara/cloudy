"""Cache seam: which backend serves a deployment is config, not code.

Values are strings (JSON), so a future shared backend (e.g. Redis) is a
drop-in — nothing in the contract can hold a Python object. "memory" is
correct while there is exactly one API process.
"""

import time
from collections import OrderedDict
from functools import lru_cache
from typing import Protocol

from cloudy.config import get_settings


class Cache(Protocol):
    def get(self, key: str) -> str | None: ...

    def set(self, key: str, value: str, ttl_s: int) -> None: ...


class MemoryCache:
    """Process-local LRU with per-entry TTL."""

    def __init__(self, maxsize: int = 1024, clock=time.monotonic) -> None:  # type: ignore[no-untyped-def]
        self._entries: OrderedDict[str, tuple[float, str]] = OrderedDict()
        self._maxsize = maxsize
        self._clock = clock

    def get(self, key: str) -> str | None:
        entry = self._entries.get(key)
        if entry is None:
            return None
        expires_at, value = entry
        if self._clock() >= expires_at:
            del self._entries[key]
            return None
        self._entries.move_to_end(key)
        return value

    def set(self, key: str, value: str, ttl_s: int) -> None:
        self._entries[key] = (self._clock() + ttl_s, value)
        self._entries.move_to_end(key)
        while len(self._entries) > self._maxsize:
            self._entries.popitem(last=False)


@lru_cache  # one cache instance per process
def get_cache() -> Cache:
    backend = get_settings().cache_backend
    if backend == "memory":
        return MemoryCache()
    raise ValueError(f"unknown cache backend: {backend!r} (supported: memory)")
