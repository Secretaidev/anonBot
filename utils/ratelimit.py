import asyncio
import time
from dataclasses import dataclass, field


@dataclass
class RateLimiter:
    """Lightweight per-user sliding window — zero external deps."""

    max_events: int = 25
    window_seconds: float = 60.0
    _hits: dict[int, list[float]] = field(default_factory=dict)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def allow(self, user_id: int) -> bool:
        now = time.monotonic()
        cutoff = now - self.window_seconds
        async with self._lock:
            bucket = self._hits.setdefault(user_id, [])
            bucket[:] = [t for t in bucket if t > cutoff]
            if len(bucket) >= self.max_events:
                return False
            bucket.append(now)
            return True

    async def reset(self, user_id: int) -> None:
        async with self._lock:
            self._hits.pop(user_id, None)
