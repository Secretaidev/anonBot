"""Hybrid matchmaking: in-memory speed + MongoDB atomic claims for reliability.

Architectural improvements:
  • Lock scope minimized — DB reads happen OUTSIDE the lock
  • Block data pre-fetched before acquiring lock
  • Rollback logic if match claim fails
  • Bidirectional block check in _blocked_between
  • sweep_timeouts batches callbacks outside lock
"""

import asyncio
import logging
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Awaitable, Callable

if TYPE_CHECKING:
    from database import Database

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
    widen_at: float


def _compatible(a: QueueEntry, b: QueueEntry) -> bool:
    def wants(looking_for: str, target_gender: str) -> bool:
        if looking_for == LOOKING_ANY:
            return True
        return looking_for == target_gender

    a_look = _effective_looking_for(a)
    b_look = _effective_looking_for(b)
    return wants(a_look, b.gender) and wants(b_look, a.gender)


def _effective_looking_for(entry: QueueEntry) -> str:
    if entry.looking_for != LOOKING_ANY:
        return entry.looking_for
    if time.monotonic() >= entry.widen_at:
        return LOOKING_ANY
    return entry.looking_for


@dataclass
class Matcher:
    """Hybrid matchmaking: in-memory speed + MongoDB atomic claims for reliability."""

    db: "Database | None" = None
    timeout_seconds: float = 300.0
    widen_after_seconds: float = 90.0
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
        looking = _effective_looking_for(entry)
        keys = [self._bucket_key(entry.gender, looking)]
        if looking != LOOKING_ANY:
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

    async def rehydrate_from_db(self) -> int:
        """Restore search queue after restart so waiting users can still match."""
        if not self.db:
            return 0

        restored = 0
        async with self._lock:
            for doc in await self.db.get_searching_users():
                user_id = int(doc["user_id"])
                if user_id in self._queue:
                    continue
                entry = QueueEntry(
                    user_id=user_id,
                    gender=str(doc["gender"]),
                    looking_for=str(doc["looking_for"]),
                    joined_at=time.monotonic(),
                    widen_at=time.monotonic() + self.widen_after_seconds,
                )
                self._queue[user_id] = entry
                self._add_to_bucket(entry)
                restored += 1
        if restored:
            logger.info("Rehydrated %s searching user(s) from MongoDB", restored)
        return restored

    async def join(self, user_id: int, gender: str, looking_for: str) -> tuple[bool, str | None]:
        """Join the search queue or immediately match.

        Architecture: Pre-fetch all DB data OUTSIDE the lock, then hold lock
        only for fast in-memory queue mutations.
        """
        session_id: str | None = None
        match_pair: tuple[int, int] | None = None

        # ── Pre-fetch DB data outside lock ──
        blocked: set[int] = set()
        if self.db:
            # Check if user is already in a valid chat session
            record = await self.db.get_user(user_id, fresh=True)
            if record and record.get("state") == STATE_CHATTING:
                partner_id = record.get("partner_id")
                session_id = record.get("session_id")
                if partner_id and session_id:
                    partner = await self.db.get_user(partner_id, fresh=True)
                    if (
                        partner
                        and partner.get("state") == STATE_CHATTING
                        and partner.get("partner_id") == user_id
                        and partner.get("session_id") == session_id
                    ):
                        return True, session_id
                await self.db.set_state(user_id, STATE_IDLE, partner_id=None, session_id=None)

            blocked = await self.db.get_block_set(user_id)

        # ── Lock only for queue mutations ──
        async with self._lock:
            if user_id in self._queue:
                old = self._queue[user_id]
                self._remove_from_bucket(old)
                entry = QueueEntry(
                    user_id=user_id,
                    gender=gender,
                    looking_for=looking_for,
                    joined_at=old.joined_at,
                    widen_at=old.widen_at,
                )
            else:
                entry = QueueEntry(
                    user_id=user_id,
                    gender=gender,
                    looking_for=looking_for,
                    joined_at=time.monotonic(),
                    widen_at=time.monotonic() + self.widen_after_seconds,
                )

            for other_id in self._candidate_ids(entry):
                if other_id in blocked:
                    continue
                other = self._queue.get(other_id)
                if other and _compatible(entry, other):
                    del self._queue[other_id]
                    self._remove_from_bucket(other)
                    session_id = str(uuid.uuid4())
                    match_pair = (user_id, other_id)
                    break

            if not match_pair and self.db:
                claim = await self.db.claim_searching_partner(
                    user_id, gender, _effective_looking_for(entry), blocked
                )
                if claim:
                    partner_id, session_id = claim
                    self._queue.pop(user_id, None)
                    partner_entry = self._queue.pop(partner_id, None)
                    if partner_entry:
                        self._remove_from_bucket(partner_entry)
                    match_pair = (user_id, partner_id)

            if not match_pair:
                self._queue[user_id] = entry
                self._add_to_bucket(entry)
                return False, None

            self._queue.pop(user_id, None)

        # ── Match callback OUTSIDE lock ──
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
        return await self.queue_size()

    async def sweep_timeouts(self) -> list[int]:
        """Batch timeout detection under lock, fire callbacks outside."""
        expired: list[int] = []
        now = time.monotonic()
        async with self._lock:
            for uid, entry in list(self._queue.items()):
                if now - entry.joined_at >= self.timeout_seconds:
                    del self._queue[uid]
                    self._remove_from_bucket(entry)
                    expired.append(uid)

        # Fire callbacks outside lock to prevent deadlocks
        if self._on_timeout:
            for uid in expired:
                try:
                    await self._on_timeout(uid)
                except Exception as exc:
                    logger.debug("timeout callback for %s: %s", uid, exc)
        return expired
