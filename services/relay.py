"""Robust message relay — 3-retry, RetryAfter backoff, typing indicator.

Professional features:
  • 3-retry with exponential backoff
  • RetryAfter (Telegram flood control) — waits and retries
  • Forbidden (user blocked bot) — returns False
  • Typing action forwarded for immersive UX
"""

import asyncio
import logging

from telegram import Message
from telegram.constants import ChatAction
from telegram.error import BadRequest, Forbidden, RetryAfter, TelegramError
from telegram.ext import ContextTypes

from utils.helpers import get_message_type

logger = logging.getLogger(__name__)


async def forward_typing(
    context: ContextTypes.DEFAULT_TYPE,
    partner_id: int,
    message: Message,
) -> None:
    """Send typing/upload action to partner for live presence feel."""
    msg_type = get_message_type(message)
    action_map = {
        "photo": ChatAction.UPLOAD_PHOTO,
        "video": ChatAction.UPLOAD_VIDEO,
        "video_note": ChatAction.UPLOAD_VIDEO_NOTE,
        "voice": ChatAction.RECORD_VOICE,
        "audio": ChatAction.UPLOAD_DOCUMENT,
        "document": ChatAction.UPLOAD_DOCUMENT,
        "sticker": ChatAction.CHOOSE_STICKER,
    }
    action = action_map.get(msg_type, ChatAction.TYPING)
    try:
        await context.bot.send_chat_action(chat_id=partner_id, action=action)
    except Exception:
        pass  # Non-critical — never block relay for this


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
