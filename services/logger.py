"""HTML-formatted admin channel logger with MongoDB message persistence.

Performance improvements:
  • Total message length capped at 4000 chars to prevent Telegram 4096 limit
  • Fire-and-forget helper for non-critical events
  • All Telegram API exceptions caught and logged (never crashes caller)
"""

import asyncio
import logging
from html import escape
from datetime import datetime, timezone

from telegram import User
from telegram.ext import ContextTypes

from database import Database

logger = logging.getLogger(__name__)

# Telegram message length limit minus safety margin
_MAX_LOG_LENGTH = 4000


def _s(value: object) -> str:
    return escape(str(value))


def profile_link(user: User) -> str:
    if user.username:
        return f"https://t.me/{user.username}"
    return f"tg://user?id={user.id}"


def display_name(user: User) -> str:
    parts = [user.first_name or "", user.last_name or ""]
    return " ".join(p for p in parts if p).strip() or "Unknown"


def format_time() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


async def log_to_channel(
    context: ContextTypes.DEFAULT_TYPE,
    channel_id: int,
    db: Database,
    *,
    event: str,
    user: User,
    partner: User | None = None,
    session_id: str | None = None,
    message_type: str | None = None,
    content: str | None = None,
    extra: str | None = None,
    persist_message: bool = True,
) -> None:
    """Send structured HTML log to admin channel. Never raises."""
    try:
        name = _s(display_name(user))
        username = f"@{_s(user.username)}" if user.username else "—"
        link = profile_link(user)
        is_premium = "⭐ Yes" if getattr(user, "is_premium", False) else "No"
        lang = getattr(user, "language_code", None) or "—"

        lines = [
            f"<b>📋 Event</b>  {_s(event)}",
            f"<b>🕐 Time</b>  {format_time()}",
            "━━━━━━━━━━━━━━━━━━━━",
            f"<b>🆔 User ID</b>  <code>{user.id}</code>",
            f"<b>📛 Name</b>  {name}",
            f"<b>🏷 Username</b>  {username}",
            f'<b>🔗 Profile</b>  <a href="{link}">Open</a>',
            f"<b>🌐 Language</b>  {_s(lang)}",
            f"<b>💎 Premium</b>  {is_premium}",
        ]

        if session_id:
            lines.append(f"<b>🔑 Session</b>  <code>{_s(session_id)}</code>")

        if partner:
            p_name = _s(display_name(partner))
            p_user = f"@{_s(partner.username)}" if partner.username else "—"
            lines.extend(
                [
                    "━━━━━━━━━━━━━━━━━━━━",
                    f"<b>🤝 Partner ID</b>  <code>{partner.id}</code>",
                    f"<b>🤝 Partner</b>  {p_name} ({p_user})",
                    f'<b>🔗 Partner</b>  <a href="{profile_link(partner)}">Open</a>',
                ]
            )

        if message_type and content is not None:
            preview = _s(content[:400])
            if len(content) > 400:
                preview += "…"
            lines.extend(
                [
                    "━━━━━━━━━━━━━━━━━━━━",
                    f"<b>💬 Type</b>  {_s(message_type)}",
                    f"<b>📝 Content</b>\n{preview}",
                ]
            )

        if extra:
            lines.extend(["━━━━━━━━━━━━━━━━━━━━", _s(extra)])

        text = "\n".join(lines)

        # Safety: truncate if exceeds Telegram limit
        if len(text) > _MAX_LOG_LENGTH:
            text = text[:_MAX_LOG_LENGTH] + "\n…[truncated]"

        await context.bot.send_message(
            chat_id=channel_id,
            text=text,
            parse_mode="HTML",
            disable_web_page_preview=True,
        )
    except Exception as exc:
        logger.warning("log channel send failed: %s", exc)

    if persist_message and session_id and message_type and content is not None:
        try:
            await db.log_message(
                session_id=session_id,
                sender_id=user.id,
                receiver_id=partner.id if partner else None,
                message_type=str(message_type),
                content_preview=content,
            )
        except Exception as exc:
            logger.warning("db log_message failed: %s", exc)


def log_to_channel_bg(
    context: ContextTypes.DEFAULT_TYPE,
    channel_id: int,
    db: Database,
    **kwargs,
) -> None:
    """Fire-and-forget log — use for non-critical events on the hot path.

    Creates an asyncio task with proper error callback so exceptions
    are logged instead of silently swallowed.
    """
    task = asyncio.create_task(
        log_to_channel(context, channel_id, db, **kwargs)
    )
    task.add_done_callback(_task_error_callback)


def _task_error_callback(task: asyncio.Task) -> None:
    """Log any unhandled exception from fire-and-forget tasks."""
    if task.cancelled():
        return
    exc = task.exception()
    if exc:
        logger.warning("background log task failed: %s", exc)
