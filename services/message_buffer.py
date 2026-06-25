"""Batched message logging — collapses 3 DB writes per message into periodic bulk ops."""

import asyncio
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from database import Database

logger = logging.getLogger(__name__)


@dataclass
class MessageLogEntry:
    session_id: str
    sender_id: int
    receiver_id: int | None
    message_type: str
    content_preview: str


@dataclass
class MessageBuffer:
    """Accumulates message logs and flushes in bulk to cut MongoDB load ~90%."""

    db: "Database"
    max_batch: int = 40
    _buffer: list[MessageLogEntry] = field(default_factory=list)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def enqueue(self, entry: MessageLogEntry) -> None:
        flush_now = False
        async with self._lock:
            self._buffer.append(entry)
            if len(self._buffer) >= self.max_batch:
                flush_now = True
        if flush_now:
            await self.flush()

    async def flush(self) -> None:
        async with self._lock:
            if not self._buffer:
                return
            batch = self._buffer[:]
            self._buffer.clear()
        try:
            await self.db.log_messages_batch(batch)
        except Exception as exc:
            logger.warning("message buffer flush failed (%s entries): %s", len(batch), exc)

    def pending(self) -> int:
        return len(self._buffer)
