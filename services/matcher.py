import asyncio
import logging
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Awaitable, Callable

logger = logging.getLogger(__name__)

GENDER_MALE = "male"
GENDER_FEMALE = "female"
GENDER_OTHER = "other"

STATE_IDLE = "idle"
STATE_SEARCHING = "searching"
STATE_CHATTING = "chatting"

LOOKING_MALE = "male"
LOOKING_FEMALE = "female"
LOOKING_ANY = "any"


@dataclass
class QueueEntry:
    user_id: int
    gender: str
    looking_for: str
    joined_at: float


def _compatible(a: QueueEntry, b: QueueEntry) -> bool:
    def wants(entry: QueueEntry, target_gender: str) -> bool:
        if entry.looking_for == LOOKING_ANY:
            return True
        return entry.looking_for == target_gender

    return wants(a, b.gender) and wants(b, a.gender)


@dataclass
class Matcher:
    """Fast in-memory matchmaking with bucket hints and timeout sweep."""

    timeout_seconds: float = 300.0
    _queue: dict[int, QueueEntry] = field(default_factory=dict)
    _buckets: dict[str, set[int]] = field(default_factory=lambda: defaultdict(set))
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    _on_match: Callable[[int, int, str], Awaitable[None]] | None = None
    _on_timeout: Callable[[int], Awaitable[None]] | None = None

    def set_match_callback(
        self, callback: Callable[[int, int, str], Awaitable[None]]
    ) -> None:
        self._on_match = callback

    def set_timeout_callback(
        self, callback: Callable[[int], Awaitable[None]]
    ) -> None:
        self._on_timeout = callback

    def _bucket_key(self, gender: str, looking_for: str) -> str:
        return f"{gender}:{looking_for}"

    def _add_to_bucket(self, entry: QueueEntry) -> None:
        self._buckets[self._bucket_key(entry.gender, entry.looking_for)].add(entry.user_id)

    def _remove_from_bucket(self, entry: QueueEntry) -> None:
        key = self._bucket_key(entry.gender, entry.looking_for)
        bucket = self._buckets.get(key)
        if bucket:
            bucket.discard(entry.user_id)
            if not bucket:
                del self._buckets[key]

    def _candidate_ids(self, entry: QueueEntry) -> list[int]:
        """Prefer same-preference bucket, then scan full queue."""
        keys = [self._bucket_key(entry.gender, entry.looking_for)]
        if entry.looking_for != LOOKING_ANY:
            keys.append(self._bucket_key(entry.gender, LOOKING_ANY))
        keys.append("*")

        seen: set[int] = set()
        ordered: list[int] = []
        for key in keys:
            if key == "*":
                ids = self._queue.keys()
            else:
                ids = self._buckets.get(key, ())
            for uid in ids:
                if uid not in seen and uid != entry.user_id:
                    seen.add(uid)
                    ordered.append(uid)
        return ordered

    async def join(self, user_id: int, gender: str, looking_for: str) -> tuple[bool, str | None]:
        session_id: str | None = None
        match_pair: tuple[int, int] | None = None

        async with self._lock:
            if user_id in self._queue:
                return False, None

            entry = QueueEntry(
                user_id=user_id,
                gender=gender,
                looking_for=looking_for,
                joined_at=time.monotonic(),
            )

            for other_id in self._candidate_ids(entry):
                other = self._queue.get(other_id)
                if other and _compatible(entry, other):
                    del self._queue[other_id]
                    self._remove_from_bucket(other)
                    session_id = str(uuid.uuid4())
                    match_pair = (user_id, other_id)
                    break

            if not match_pair:
                self._queue[user_id] = entry
                self._add_to_bucket(entry)
                return False, None

        if match_pair and session_id and self._on_match:
            try:
                await self._on_match(match_pair[0], match_pair[1], session_id)
            except Exception as exc:
                logger.exception("match callback failed: %s", exc)

        return True, session_id

    async def leave(self, user_id: int) -> bool:
        async with self._lock:
            entry = self._queue.pop(user_id, None)
            if entry:
                self._remove_from_bucket(entry)
                return True
            return False

    async def queue_size(self) -> int:
        return len(self._queue)

    async def online_count(self) -> int:
        return len(self._queue)

    async def sweep_timeouts(self) -> list[int]:
        """Remove users waiting longer than timeout_seconds."""
        expired: list[int] = []
        now = time.monotonic()
        async with self._lock:
            for uid, entry in list(self._queue.items()):
                if now - entry.joined_at >= self.timeout_seconds:
                    del self._queue[uid]
                    self._remove_from_bucket(entry)
                    expired.append(uid)

        if self._on_timeout:
            for uid in expired:
                try:
                    await self._on_timeout(uid)
                except Exception as exc:
                    logger.debug("timeout callback for %s: %s", uid, exc)
        return expired
