import logging
import asyncio
import ssl
from datetime import datetime, timezone
from typing import Any

import certifi
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo import ReturnDocument
from pymongo.errors import ServerSelectionTimeoutError, ConnectionFailure, ConfigurationError

from utils.mongo import normalize_mongodb_url

logger = logging.getLogger(__name__)


class Database:
    """MongoDB persistence — async, indexed, production-ready."""

    def __init__(self, mongodb_url: str, db_name: str = "anoybot") -> None:
        self.mongodb_url = mongodb_url
        self.db_name = db_name
        self._client: AsyncIOMotorClient | None = None
        self._db: AsyncIOMotorDatabase | None = None

    async def connect(self, max_retries: int = 5) -> None:
        url = normalize_mongodb_url(self.mongodb_url, self.db_name)
        last_error: Exception | None = None
        is_srv = url.startswith("mongodb+srv://")

        # Base connection options
        client_kwargs: dict = {
            "serverSelectionTimeoutMS": 30000,
            "connectTimeoutMS": 20000,
            "socketTimeoutMS": 30000,
            "maxPoolSize": 50,
            "minPoolSize": 1,
            "retryWrites": True,
        }

        if not is_srv:
            client_kwargs["tls"] = False
        else:
            # Atlas SRV: use certifi CA bundle; allow invalid certs as fallback for Windows SSL issues
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
        await self.db.users.create_index("user_id", unique=True)
        await self.db.users.create_index("state")
        await self.db.users.create_index("is_banned")
        await self.db.users.create_index("partner_id")
        await self.db.sessions.create_index("session_id", unique=True)
        await self.db.sessions.create_index("user_a_id")
        await self.db.sessions.create_index("user_b_id")
        await self.db.message_logs.create_index("session_id")
        await self.db.message_logs.create_index("sender_id")
        await self.db.message_logs.create_index("created_at")
        await self.db.blocks.create_index([("user_id", 1), ("blocked_id", 1)], unique=True)
        await self.db.reports.create_index("reporter_id")
        await self.db.reports.create_index("reported_id")

    @staticmethod
    def _now() -> str:
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

    async def upsert_user(
        self,
        user_id: int,
        username: str | None,
        first_name: str | None,
        last_name: str | None,
    ) -> dict[str, Any]:
        now = self._now()
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

    async def get_user(self, user_id: int) -> dict[str, Any] | None:
        doc = await self.db.users.find_one({"user_id": user_id})
        return dict(doc) if doc else None

    async def accept_rules(self, user_id: int) -> None:
        now = self._now()
        await self.db.users.update_one(
            {"user_id": user_id},
            {"$set": {"accepted_rules": True, "updated_at": now, "last_active_at": now}},
        )

    async def set_gender(self, user_id: int, gender: str) -> None:
        now = self._now()
        await self.db.users.update_one(
            {"user_id": user_id},
            {"$set": {"gender": gender, "updated_at": now, "last_active_at": now}},
        )

    async def set_looking_for(self, user_id: int, looking_for: str) -> None:
        now = self._now()
        await self.db.users.update_one(
            {"user_id": user_id},
            {"$set": {"looking_for": looking_for, "updated_at": now, "last_active_at": now}},
        )

    async def set_state(
        self,
        user_id: int,
        state: str,
        partner_id: int | None = None,
        session_id: str | None = None,
    ) -> None:
        now = self._now()
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

    async def reset_active_sessions(self) -> int:
        now = self._now()
        result = await self.db.users.update_many(
            {"state": {"$in": ["searching", "chatting"]}},
            {
                "$set": {
                    "state": "idle",
                    "partner_id": None,
                    "session_id": None,
                    "updated_at": now,
                }
            },
        )
        return result.modified_count

    async def create_session(self, session_id: str, user_a: int, user_b: int) -> None:
        now = self._now()
        await self.db.sessions.insert_one(
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
        )
        await self.db.users.update_many(
            {"user_id": {"$in": [user_a, user_b]}},
            {"$inc": {"total_sessions": 1}, "$set": {"updated_at": now}},
        )

    async def end_session(self, session_id: str) -> None:
        now = self._now()
        msg_count = await self.db.message_logs.count_documents({"session_id": session_id})
        await self.db.sessions.update_one(
            {"session_id": session_id},
            {"$set": {"ended_at": now, "message_count": msg_count}},
        )

    async def save_session_rating(self, session_id: str, user_id: int, stars: int) -> None:
        now = self._now()
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
        await self.db.sessions.update_one(
            {"session_id": session_id},
            {"$set": {field: stars}},
        )
        await self.db.users.update_one(
            {"user_id": user_id},
            {
                "$inc": {"rating_sum": stars, "rating_count": 1},
                "$set": {"updated_at": now},
            },
        )

    async def log_message(
        self,
        session_id: str,
        sender_id: int,
        receiver_id: int | None,
        message_type: str,
        content_preview: str,
    ) -> None:
        now = self._now()
        await self.db.message_logs.insert_one(
            {
                "session_id": session_id,
                "sender_id": sender_id,
                "receiver_id": receiver_id,
                "message_type": message_type,
                "content_preview": content_preview[:500],
                "created_at": now,
            }
        )
        await self.db.users.update_one(
            {"user_id": sender_id},
            {"$inc": {"total_messages": 1}, "$set": {"last_active_at": now}},
        )

    async def add_block(self, user_id: int, blocked_id: int) -> None:
        now = self._now()
        await self.db.blocks.update_one(
            {"user_id": user_id, "blocked_id": blocked_id},
            {"$setOnInsert": {"created_at": now}},
            upsert=True,
        )

    async def is_blocked(self, user_id: int, other_id: int) -> bool:
        doc = await self.db.blocks.find_one({"user_id": user_id, "blocked_id": other_id})
        return doc is not None

    async def ban_user(self, user_id: int, reason: str) -> None:
        now = self._now()
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

    async def unban_user(self, user_id: int) -> None:
        now = self._now()
        await self.db.users.update_one(
            {"user_id": user_id},
            {"$set": {"is_banned": False, "ban_reason": None, "updated_at": now}},
        )

    async def increment_reports(self, user_id: int) -> int:
        now = self._now()
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
        now = self._now()
        await self.db.reports.insert_one(
            {
                "reporter_id": reporter_id,
                "reported_id": reported_id,
                "session_id": session_id,
                "reason": reason[:500],
                "created_at": now,
            }
        )

    async def get_stats(self) -> dict[str, int]:
        users = await self.db.users.count_documents({})
        searching = await self.db.users.count_documents({"state": "searching"})
        chatting = await self.db.users.count_documents({"state": "chatting"})
        sessions = await self.db.sessions.count_documents({})
        banned = await self.db.users.count_documents({"is_banned": True})
        messages = await self.db.message_logs.count_documents({})
        return {
            "users": users,
            "searching": searching,
            "chatting": chatting,
            "sessions": sessions,
            "banned": banned,
            "messages": messages,
        }

    async def get_users_searching(self) -> list[int]:
        cursor = self.db.users.find({"state": "searching"}, {"user_id": 1})
        return [doc["user_id"] async for doc in cursor]

    async def get_broadcast_user_ids(self) -> list[int]:
        cursor = self.db.users.find({"is_banned": False}, {"user_id": 1})
        return [doc["user_id"] async for doc in cursor]
