"""TTL cache for expensive aggregate stats — cuts MongoDB load sharply.

Improvements:
  • Double-checked locking (already existed)
  • Jitter on TTL to prevent thundering herd after mass invalidation
  • Stale-while-revalidate: returns stale data while refreshing in background
"""

import asyncio
import random
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class StatsCache:
    ttl_seconds: float = 30.0
    _data: dict[str, Any] = field(default_factory=dict)
    _expires_at: float = 0.0
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    _refreshing: bool = field(default=False, repr=False)

    async def get(self, loader) -> dict[str, int]:
        now = time.monotonic()
        if self._data and now < self._expires_at:
            return self._data

        # Stale-while-revalidate: return stale data if another task is refreshing
        if self._refreshing and self._data:
            return self._data

        async with self._lock:
            now = time.monotonic()
            if self._data and now < self._expires_at:
                return self._data

            self._refreshing = True
            try:
                self._data = await loader()
                # Add jitter (±15%) to prevent thundering herd
                jitter = self.ttl_seconds * random.uniform(-0.15, 0.15)
                self._expires_at = now + self.ttl_seconds + jitter
                return self._data
            finally:
                self._refreshing = False

    def invalidate(self) -> None:
        self._expires_at = 0.0
