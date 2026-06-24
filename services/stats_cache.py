import asyncio
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class StatsCache:
    """TTL cache for expensive aggregate stats — cuts MongoDB load sharply."""

    ttl_seconds: float = 30.0
    _data: dict[str, Any] = field(default_factory=dict)
    _expires_at: float = 0.0
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def get(self, loader) -> dict[str, int]:
        now = time.monotonic()
        if self._data and now < self._expires_at:
            return self._data

        async with self._lock:
            now = time.monotonic()
            if self._data and now < self._expires_at:
                return self._data
            self._data = await loader()
            self._expires_at = now + self.ttl_seconds
            return self._data

    def invalidate(self) -> None:
        self._expires_at = 0.0
