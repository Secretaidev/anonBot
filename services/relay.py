"""Robust message relay — 3-retry, RetryAfter backoff, graceful Forbidden handling.

Used by chat.py for every message relay to partner. Handles:
  • RetryAfter (Telegram flood control) — waits and retries
  • Forbidden (user blocked the bot) — returns False, caller ends chat
  • BadRequest (deleted chat, etc.) — returns False
  • Generic TelegramError — retries with backoff
"""

import asyncio
import logging

from telegram import Message
from telegram.error import BadRequest, Forbidden, RetryAfter, TelegramError
from telegram.ext import ContextTypes

from database import Database
from handlers.session import end_chat
from utils.helpers import get_message_type

logger = logging.getLogger(__name__)




async def copy_to_partner(
    context: ContextTypes.DEFAULT_TYPE,
    message: Message,
    partner_id: int,
    *,
    sender_id: int | None = None,
) -> bool:
    """Copy any message type to the chat partner — fast, retried, crash-proof."""
    for attempt in range(3):
        try:
            await context.bot.copy_message(
                chat_id=partner_id,
                from_chat_id=message.chat_id,
                message_id=message.message_id,
            )
            return True
        except RetryAfter as exc:
            if attempt == 2:
                break
            await asyncio.sleep(exc.retry_after + 0.3)
        except Forbidden:
            logger.info("partner %s blocked bot (sender=%s)", partner_id, sender_id)
            return False
        except BadRequest as exc:
            logger.warning("copy bad request %s -> %s: %s", sender_id, partner_id, exc)
            return False
        except TelegramError as exc:
            logger.warning("copy failed %s -> %s: %s", sender_id, partner_id, exc)
            if attempt == 2:
                return False
            await asyncio.sleep(0.4 * (attempt + 1))
    return False


async def relay_chat_message(
    context: ContextTypes.DEFAULT_TYPE,
    db: Database,
    *,
    user_id: int,
    partner_id: int,
    session_id: str,
    message: Message,
    max_length: int,
) -> tuple[bool, str | None]:
    """
    Relay one message to partner.
    Returns (ok, error_text). Never raises.
    """
    content = message.text or message.caption
    msg_type = get_message_type(message)
    if content is None and msg_type == "text":
        content = ""
    if content is None:
        content = f"[{msg_type}]"

    if len(content) > max_length:
        return False, f"⚠️ Message too long (max {max_length} chars)."

    ok = await copy_to_partner(context, message, partner_id, sender_id=user_id)
    if ok:
        return True, None

    try:
        await end_chat(context, user_id, reason="partner_left")
    except Exception as exc:
        logger.warning("end_chat after relay fail: %s", exc)
    return False, "❌ Partner unavailable. Chat ended."
