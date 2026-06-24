import logging
import asyncio
import time
import uuid
from datetime import datetime, timezone
from typing import Any

import certifi
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo import IndexModel, ASCENDING, ReturnDocument
from pymongo.errors import ServerSelectionTimeoutError, ConnectionFailure

from utils.mongo import normalize_mongodb_url

logger = logging.getLogger(__name__)

STATE_IDLE = "idle"
STATE_SEARCHING = "searching"
STATE_CHATTING = "chatting"

# Cache GC runs every N seconds to prune expired entries
_CACHE_GC_INTERVAL = 120.0


class Database:
    """MongoDB persistence — async, indexed, production-ready, zero-waste."""

    __slots__ = (
        "mongodb_url",
        "db_name",
        "user_cache_seconds",
        "_client",
        "_db",
        "_user_cache",
        "_cache_lock",
        "_last_gc",
    )

    def __init__(
        self,
        mongodb_url: str,
        db_name: str = "anoybot",
        *,
        user_cache_seconds: float = 8.0,
    ) -> None:
        self.mongodb_url = mongodb_url
        self.db_name = db_name
        self.user_cache_seconds = user_cache_seconds
        self._client: AsyncIOMotorClient | None = None
        self._db: AsyncIOMotorDatabase | None = None
        self._user_cache: dict[int, tuple[float, dict[str, Any]]] = {}
        self._cache_lock = asyncio.Lock()
        self._last_gc: float = 0.0

    async def connect(self, max_retries: int = 5) -> None:
        url = normalize_mongodb_url(self.mongodb_url, self.db_name)
        last_error: Exception | None = None
        is_srv = url.startswith("mongodb+srv://")

        # Tuned connection pool — low idle footprint, fast bursts
        client_kwargs: dict = {
            "serverSelectionTimeoutMS": 30000,
            "connectTimeoutMS": 20000,
            "socketTimeoutMS": 30000,
            "maxPoolSize": 25,
            "minPoolSize": 2,
            "maxIdleTimeMS": 45000,
            "retryWrites": True,
            "retryReads": True,
            "compressors": "zlib",
        }

        if not is_srv:
            client_kwargs["tls"] = False
        else:
            # Atlas SRV: use certifi CA bundle
            client_kwargs["tls"] = True
            client_kwargs["tlsCAFile"] = certifi.where()
            client_kwargs["tlsAllowInvalidCertificates"] = True

        for attempt in range(1, max_retries + 1):
            try:
                if self._client:
                    self._client.close()
                self._client = AsyncIOMotorClient(url, **client_kwargs)
                self._db = self._client[self.db_name]
                await self._client.admin.command("ping")
                await self._ensure_indexes()
                host = url.split("@")[-1].split("/")[0]
                logger.info("MongoDB connected: %s / %s", host, self.db_name)
                return
            except (ServerSelectionTimeoutError, ConnectionFailure, ConnectionError, OSError, Exception) as exc:
                last_error = exc
                wait = min(attempt * 3, 15)
                logger.warning(
                    "MongoDB connect attempt %s/%s failed (retrying in %ss): %s",
                    attempt, max_retries, wait, type(exc).__name__
                )
                await asyncio.sleep(wait)

        raise RuntimeError(
            "MongoDB connection failed.\n"
            "Atlas fix:\n"
            "  • Network Access → Add IP Address → Allow Access from Anywhere (0.0.0.0/0)\n"
            "  • Database Access → confirm username/password in MONGODB_URL\n"
            "  • Check your internet connection / firewall / VPN\n"
            "Local fix:\n"
            "  • Install MongoDB → set MONGODB_URL=mongodb://127.0.0.1:27017/anoybot\n"
            f"Error: {last_error}"
        ) from last_error

    async def close(self) -> None:
        if self._client:
            self._client.close()
            self._client = None
            self._db = None

    @property
    def db(self) -> AsyncIOMotorDatabase:
        if self._db is None:
            raise RuntimeError("Database not connected")
        return self._db

    async def _ensure_indexes(self) -> None:
        """Create optimal indexes — compound for match queries, TTL for logs."""
        # ── Users ──
        await self.db.users.create_indexes([
            IndexModel([("user_id", ASCENDING)], unique=True),
            IndexModel([("state", ASCENDING)]),
            IndexModel([("is_banned", ASCENDING)]),
            IndexModel([("partner_id", ASCENDING)]),
            # Compound index for match queries: state + gender + looking_for + is_banned
            IndexModel([
                ("state", ASCENDING),
                ("is_banned", ASCENDING),
                ("gender", ASCENDING),
                ("looking_for", ASCENDING),
            ], name="match_compound_idx"),
            # Compound for claim_searching_partner sort
            IndexModel([
                ("state", ASCENDING),
                ("is_banned", ASCENDING),
                ("updated_at", ASCENDING),
            ], name="search_sort_idx"),
        ])

        # ── Sessions ──
        await self.db.sessions.create_indexes([
            IndexModel([("session_id", ASCENDING)], unique=True),
            IndexModel([("user_a_id", ASCENDING)]),
            IndexModel([("user_b_id", ASCENDING)]),
        ])

        # ── Message Logs — TTL auto-expire after 30 days ──
        # Drop conflicting old index if it exists (non-TTL created_at_1)
        try:
            existing = await self.db.message_logs.index_information()
            if "created_at_1" in existing:
                ttl = existing["created_at_1"].get("expireAfterSeconds")
                if ttl is None:
                    await self.db.message_logs.drop_index("created_at_1")
                    logger.info("Dropped old created_at_1 index to create TTL variant")
        except Exception as exc:
            logger.debug("index migration check: %s", exc)

        await self.db.message_logs.create_indexes([
            IndexModel([("session_id", ASCENDING)]),
            IndexModel([("sender_id", ASCENDING)]),
            IndexModel(
                [("created_at", ASCENDING)],
                expireAfterSeconds=30 * 24 * 3600,
                name="ttl_30d",
            ),
        ])

        # ── Blocks ──
        await self.db.blocks.create_indexes([
            IndexModel(
                [("user_id", ASCENDING), ("blocked_id", ASCENDING)],
                unique=True,
            ),
            IndexModel([("blocked_id", ASCENDING)]),
        ])

        # ── Reports ──
        await self.db.reports.create_indexes([
            IndexModel([("reporter_id", ASCENDING)]),
            IndexModel([("reported_id", ASCENDING)]),
        ])

    # ──────────────────────────────────────────────────────────────
    # Helpers
    # ──────────────────────────────────────────────────────────────

    @staticmethod
    def _now() -> datetime:
        """Return UTC datetime — stored natively for TTL indexes to work."""
        return datetime.now(timezone.utc)

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _default_user(user_id: int, username: str | None, first_name: str | None, last_name: str | None, now: str) -> dict[str, Any]:
        return {
            "user_id": user_id,
            "username": username,
            "first_name": first_name,
            "last_name": last_name,
            "gender": None,
            "looking_for": None,
            "state": "idle",
            "partner_id": None,
            "session_id": None,
            "total_sessions": 0,
            "total_messages": 0,
            "accepted_rules": False,
            "is_banned": False,
            "ban_reason": None,
            "reports_received": 0,
            "rating_sum": 0,
            "rating_count": 0,
            "created_at": now,
            "updated_at": now,
            "last_active_at": now,
        }

    # ──────────────────────────────────────────────────────────────
    # User cache — with GC to prevent unbounded growth
    # ──────────────────────────────────────────────────────────────

    def _cache_user(self, user_id: int, doc: dict[str, Any] | None) -> dict[str, Any] | None:
        if doc is None:
            self._user_cache.pop(user_id, None)
            return None
        payload = dict(doc)
        self._user_cache[user_id] = (time.monotonic() + self.user_cache_seconds, payload)
        self._maybe_gc_cache()
        return payload

    def invalidate_user(self, user_id: int) -> None:
        self._user_cache.pop(user_id, None)

    def _maybe_gc_cache(self) -> None:
        """Prune expired entries periodically to prevent memory leaks."""
        now = time.monotonic()
        if now - self._last_gc < _CACHE_GC_INTERVAL:
            return
        self._last_gc = now
        expired = [uid for uid, (exp, _) in self._user_cache.items() if exp <= now]
        for uid in expired:
            del self._user_cache[uid]
        if expired:
            logger.debug("Cache GC: pruned %d stale entries", len(expired))

    # ──────────────────────────────────────────────────────────────
    # User CRUD
    # ──────────────────────────────────────────────────────────────

    async def get_user(self, user_id: int, *, fresh: bool = False) -> dict[str, Any] | None:
        if not fresh:
            cached = self._user_cache.get(user_id)
            if cached and cached[0] > time.monotonic():
                return dict(cached[1])

        doc = await self.db.users.find_one({"user_id": user_id})
        return self._cache_user(user_id, dict(doc) if doc else None)

    async def upsert_user(
        self,
        user_id: int,
        username: str | None,
        first_name: str | None,
        last_name: str | None,
    ) -> dict[str, Any]:
        now = self._now_iso()
        await self.db.users.update_one(
            {"user_id": user_id},
            {
                "$set": {
                    "username": username,
                    "first_name": first_name,
                    "last_name": last_name,
                    "updated_at": now,
                    "last_active_at": now,
                },
                "$setOnInsert": {
                    k: v for k, v in self._default_user(user_id, username, first_name, last_name, now).items()
                    if k not in ("username", "first_name", "last_name", "updated_at", "last_active_at")
                },
            },
            upsert=True,
        )
        user = await self.get_user(user_id)
        return user or {}

    async def accept_rules(self, user_id: int) -> None:
        now = self._now_iso()
        await self.db.users.update_one(
            {"user_id": user_id},
            {"$set": {"accepted_rules": True, "updated_at": now, "last_active_at": now}},
        )
        self.invalidate_user(user_id)

    async def set_gender(self, user_id: int, gender: str) -> None:
        now = self._now_iso()
        await self.db.users.update_one(
            {"user_id": user_id},
            {"$set": {"gender": gender, "updated_at": now, "last_active_at": now}},
        )
        self.invalidate_user(user_id)

    async def set_looking_for(self, user_id: int, looking_for: str) -> None:
        now = self._now_iso()
        await self.db.users.update_one(
            {"user_id": user_id},
            {"$set": {"looking_for": looking_for, "updated_at": now, "last_active_at": now}},
        )
        self.invalidate_user(user_id)

    async def set_state(
        self,
        user_id: int,
        state: str,
        partner_id: int | None = None,
        session_id: str | None = None,
    ) -> None:
        now = self._now_iso()
        await self.db.users.update_one(
            {"user_id": user_id},
            {
                "$set": {
                    "state": state,
                    "partner_id": partner_id,
                    "session_id": session_id,
                    "updated_at": now,
                    "last_active_at": now,
                }
            },
        )
        self.invalidate_user(user_id)

    # ──────────────────────────────────────────────────────────────
    # Session management
    # ──────────────────────────────────────────────────────────────

    async def reset_chatting_sessions(self) -> list[int]:
        """Reset orphaned chats after restart — keep search queue intact."""
        now = self._now_iso()
        cursor = self.db.users.find({"state": STATE_CHATTING}, {"user_id": 1})
        user_ids = [doc["user_id"] async for doc in cursor]
        if not user_ids:
            return []

        await self.db.users.update_many(
            {"state": STATE_CHATTING},
            {
                "$set": {
                    "state": STATE_IDLE,
                    "partner_id": None,
                    "session_id": None,
                    "updated_at": now,
                }
            },
        )
        for uid in user_ids:
            self.invalidate_user(uid)
        return user_ids

    async def reset_active_sessions(self) -> int:
        """Legacy helper — only clears chatting state."""
        cleared = await self.reset_chatting_sessions()
        return len(cleared)

    async def get_searching_users(self) -> list[dict[str, Any]]:
        """Uses compound index: (state, is_banned, gender, looking_for)."""
        cursor = self.db.users.find(
            {
                "state": STATE_SEARCHING,
                "is_banned": {"$ne": True},
                "gender": {"$ne": None},
                "looking_for": {"$ne": None},
            },
            {"user_id": 1, "gender": 1, "looking_for": 1, "updated_at": 1},
        )
        return [dict(doc) async for doc in cursor]

    async def get_block_set(self, user_id: int) -> set[int]:
        """Bidirectional block check — returns all user IDs blocked in either direction."""
        blocked_by_user = self.db.blocks.find({"user_id": user_id}, {"blocked_id": 1})
        blocked_user = self.db.blocks.find({"blocked_id": user_id}, {"user_id": 1})
        ids: set[int] = set()
        async for doc in blocked_by_user:
            ids.add(int(doc["blocked_id"]))
        async for doc in blocked_user:
            ids.add(int(doc["user_id"]))
        return ids

    @staticmethod
    def _partner_gender_filters(gender: str, looking_for: str) -> list[dict[str, Any]]:
        """Build MongoDB filters for compatible searching partners."""
        filters: list[dict[str, Any]] = []

        def partner_wants_me(my_gender: str) -> dict[str, Any]:
            return {
                "$or": [
                    {"looking_for": "any"},
                    {"looking_for": my_gender},
                ]
            }

        if looking_for == "any":
            filters.append(partner_wants_me(gender))
        else:
            filters.append({"gender": looking_for})
            filters.append(partner_wants_me(gender))

        return filters

    async def claim_searching_partner(
        self,
        user_id: int,
        gender: str,
        looking_for: str,
        blocked_ids: set[int],
    ) -> tuple[int, str] | None:
        """Atomically claim one compatible searching user from MongoDB.

        Uses compound index (state, is_banned, updated_at) for sorted scans.
        """
        session_id = str(uuid.uuid4())
        now = self._now_iso()
        exclude = list(blocked_ids | {user_id})

        for extra in self._partner_gender_filters(gender, looking_for):
            query: dict[str, Any] = {
                "state": STATE_SEARCHING,
                "is_banned": {"$ne": True},
                "user_id": {"$nin": exclude},
                **extra,
            }
            partner = await self.db.users.find_one_and_update(
                query,
                {
                    "$set": {
                        "state": STATE_CHATTING,
                        "partner_id": user_id,
                        "session_id": session_id,
                        "updated_at": now,
                        "last_active_at": now,
                    }
                },
                sort=[("updated_at", 1)],
                return_document=ReturnDocument.AFTER,
            )
            if not partner:
                continue

            partner_id = int(partner["user_id"])
            claimed = await self.db.users.update_one(
                {
                    "user_id": user_id,
                    "state": {"$in": [STATE_IDLE, STATE_SEARCHING]},
                },
                {
                    "$set": {
                        "state": STATE_CHATTING,
                        "partner_id": partner_id,
                        "session_id": session_id,
                        "updated_at": now,
                        "last_active_at": now,
                    }
                },
            )
            if claimed.modified_count:
                self.invalidate_user(user_id)
                self.invalidate_user(partner_id)
                return partner_id, session_id

            # Rollback partner if we couldn't claim ourselves
            await self.db.users.update_one(
                {
                    "user_id": partner_id,
                    "session_id": session_id,
                },
                {
                    "$set": {
                        "state": STATE_SEARCHING,
                        "partner_id": None,
                        "session_id": None,
                        "updated_at": now,
                    }
                },
            )
            self.invalidate_user(partner_id)
        return None

    async def create_session(self, session_id: str, user_a: int, user_b: int) -> None:
        """Single round-trip: insert session + bump user counters in parallel."""
        now = self._now_iso()
        await asyncio.gather(
            self.db.sessions.insert_one(
                {
                    "session_id": session_id,
                    "user_a_id": user_a,
                    "user_b_id": user_b,
                    "started_at": now,
                    "ended_at": None,
                    "message_count": 0,
                    "rating_a": None,
                    "rating_b": None,
                }
            ),
            self.db.users.update_many(
                {"user_id": {"$in": [user_a, user_b]}},
                {"$inc": {"total_sessions": 1}, "$set": {"updated_at": now}},
            ),
        )

    async def end_session(self, session_id: str) -> None:
        now = self._now_iso()
        await self.db.sessions.update_one(
            {"session_id": session_id},
            {"$set": {"ended_at": now}},
        )

    async def save_session_rating(self, session_id: str, user_id: int, stars: int) -> None:
        now = self._now_iso()
        session = await self.db.sessions.find_one({"session_id": session_id})
        if not session:
            return
        field = None
        if session.get("user_a_id") == user_id:
            field = "rating_a"
        elif session.get("user_b_id") == user_id:
            field = "rating_b"
        if not field:
            return

        # Parallel: save rating to session + update user aggregate
        await asyncio.gather(
            self.db.sessions.update_one(
                {"session_id": session_id},
                {"$set": {field: stars}},
            ),
            self.db.users.update_one(
                {"user_id": user_id},
                {
                    "$inc": {"rating_sum": stars, "rating_count": 1},
                    "$set": {"updated_at": now},
                },
            ),
        )

    # ──────────────────────────────────────────────────────────────
    # Message logging
    # ──────────────────────────────────────────────────────────────

    async def log_message(
        self,
        session_id: str,
        sender_id: int,
        receiver_id: int | None,
        message_type: str,
        content_preview: str,
    ) -> None:
        now = self._now()  # datetime for TTL index
        # Fire all 3 writes in parallel — none blocks on the others
        await asyncio.gather(
            self.db.message_logs.insert_one(
                {
                    "session_id": session_id,
                    "sender_id": sender_id,
                    "receiver_id": receiver_id,
                    "message_type": message_type,
                    "content_preview": content_preview[:500],
                    "created_at": now,
                }
            ),
            self.db.sessions.update_one(
                {"session_id": session_id},
                {"$inc": {"message_count": 1}},
            ),
            self.db.users.update_one(
                {"user_id": sender_id},
                {"$inc": {"total_messages": 1}, "$set": {"last_active_at": self._now_iso()}},
            ),
            return_exceptions=True,
        )
        self.invalidate_user(sender_id)

    # ──────────────────────────────────────────────────────────────
    # Blocking & reporting
    # ──────────────────────────────────────────────────────────────

    async def add_block(self, user_id: int, blocked_id: int) -> None:
        now = self._now_iso()
        await self.db.blocks.update_one(
            {"user_id": user_id, "blocked_id": blocked_id},
            {"$setOnInsert": {"created_at": now}},
            upsert=True,
        )

    async def is_blocked(self, user_id: int, other_id: int) -> bool:
        """Check both directions of block."""
        doc = await self.db.blocks.find_one({
            "$or": [
                {"user_id": user_id, "blocked_id": other_id},
                {"user_id": other_id, "blocked_id": user_id},
            ]
        })
        return doc is not None

    async def ban_user(self, user_id: int, reason: str) -> None:
        now = self._now_iso()
        await self.db.users.update_one(
            {"user_id": user_id},
            {
                "$set": {
                    "is_banned": True,
                    "ban_reason": reason,
                    "state": "idle",
                    "partner_id": None,
                    "session_id": None,
                    "updated_at": now,
                }
            },
        )
        self.invalidate_user(user_id)

    async def unban_user(self, user_id: int) -> None:
        now = self._now_iso()
        await self.db.users.update_one(
            {"user_id": user_id},
            {"$set": {"is_banned": False, "ban_reason": None, "updated_at": now}},
        )
        self.invalidate_user(user_id)

    async def increment_reports(self, user_id: int) -> int:
        now = self._now_iso()
        doc = await self.db.users.find_one_and_update(
            {"user_id": user_id},
            {"$inc": {"reports_received": 1}, "$set": {"updated_at": now}},
            return_document=ReturnDocument.AFTER,
        )
        return int(doc.get("reports_received", 0)) if doc else 0

    async def add_report(
        self,
        reporter_id: int,
        reported_id: int | None,
        session_id: str | None,
        reason: str,
    ) -> None:
        now = self._now_iso()
        await self.db.reports.insert_one(
            {
                "reporter_id": reporter_id,
                "reported_id": reported_id,
                "session_id": session_id,
                "reason": reason[:500],
                "created_at": now,
            }
        )

    # ──────────────────────────────────────────────────────────────
    # Stats — single $facet aggregation (6 queries → 1)
    # ──────────────────────────────────────────────────────────────

    async def get_stats(self) -> dict[str, int]:
        """Single aggregation pipeline replaces 6 count_documents calls."""
        pipeline = [
            {"$facet": {
                "total": [{"$count": "n"}],
                "searching": [{"$match": {"state": "searching"}}, {"$count": "n"}],
                "chatting": [{"$match": {"state": "chatting"}}, {"$count": "n"}],
                "banned": [{"$match": {"is_banned": True}}, {"$count": "n"}],
            }}
        ]
        result = await self.db.users.aggregate(pipeline).to_list(1)
        facets = result[0] if result else {}

        def _extract(key: str) -> int:
            arr = facets.get(key, [])
            return arr[0]["n"] if arr else 0

        # Sessions and messages are separate collections — count in parallel
        sessions_count, messages_count = await asyncio.gather(
            self.db.sessions.estimated_document_count(),
            self.db.message_logs.estimated_document_count(),
        )

        return {
            "users": _extract("total"),
            "searching": _extract("searching"),
            "chatting": _extract("chatting"),
            "sessions": sessions_count,
            "banned": _extract("banned"),
            "messages": messages_count,
        }

    async def get_users_searching(self) -> list[int]:
        cursor = self.db.users.find({"state": "searching"}, {"user_id": 1})
        return [doc["user_id"] async for doc in cursor]

    async def get_broadcast_user_ids(self) -> list[int]:
        """$ne True catches both False and missing field."""
        cursor = self.db.users.find({"is_banned": {"$ne": True}}, {"user_id": 1})
        return [doc["user_id"] async for doc in cursor]

    async def get_users_by_ids(self, user_ids: list[int]) -> dict[int, dict[str, Any]]:
        """Batch fetch users by IDs — single query for pulse job optimization."""
        if not user_ids:
            return {}
        cursor = self.db.users.find(
            {"user_id": {"$in": user_ids}},
            {"user_id": 1, "state": 1},
        )
        return {int(doc["user_id"]): dict(doc) async for doc in cursor}
