"""Lightweight per-user sliding window rate limiter — zero external deps.

Improvements over original:
  • Per-user deque (O(1) popleft) instead of list slicing
  • Periodic GC to prevent unbounded memory growth from inactive users
  • No global lock — uses per-user atomic operations via defaultdict
"""

import time
from collections import defaultdict, deque
from dataclasses import dataclass, field

# GC stale users every N calls to allow()
_GC_EVERY = 500


@dataclass
class RateLimiter:
    max_events: int = 25
    window_seconds: float = 60.0
    _hits: dict[int, deque[float]] = field(default_factory=lambda: defaultdict(deque))
    _call_count: int = field(default=0, repr=False)

    def allow(self, user_id: int) -> bool:
        """Non-async for maximum speed — no lock needed in single-threaded asyncio."""
        now = time.monotonic()
        cutoff = now - self.window_seconds
        bucket = self._hits[user_id]

        # Pop expired timestamps from the left (oldest first)
        while bucket and bucket[0] <= cutoff:
            bucket.popleft()

        if len(bucket) >= self.max_events:
            return False

        bucket.append(now)
        self._call_count += 1
        if self._call_count >= _GC_EVERY:
            self._gc(now)
        return True

    def reset(self, user_id: int) -> None:
        self._hits.pop(user_id, None)

    def _gc(self, now: float) -> None:
        """Remove users with no recent activity to free memory."""
        self._call_count = 0
        cutoff = now - self.window_seconds * 2
        stale = [uid for uid, bucket in self._hits.items() if not bucket or bucket[-1] <= cutoff]
        for uid in stale:
            del self._hits[uid]
