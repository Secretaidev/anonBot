"""Core helpers — safe_send, safe_edit, session validation, home screen.

Performance notes:
  • is_banned() uses cached reads (ban state changes rarely)
  • is_valid_chat_session() uses cached reads on the hot relay path
  • safe_send() has 3-retry with exponential backoff + RetryAfter
  • safe_edit() silently ignores "message is not modified"
"""

import asyncio
import logging
from typing import Any

from telegram import Chat, InlineKeyboardMarkup, User
from telegram.error import BadRequest, Forbidden, RetryAfter, TelegramError
from telegram.ext import ContextTypes

from database import Database
from keyboards.buttons import main_menu_keyboard, rules_keyboard
from services.matcher import Matcher, STATE_CHATTING, STATE_IDLE, STATE_SEARCHING
from utils.texts import (
    MATCHED,
    PULSE_FRAMES,
    READY,
    SEARCHING,
    WELCOME,
    gender_label,
    looking_label,
)

logger = logging.getLogger(__name__)


def chat_to_user(chat: Chat) -> User:
    """Convert Chat object to User for logging — lightweight, no API call."""
    return User(
        id=chat.id,
        is_bot=False,
        first_name=chat.first_name or "",
        last_name=chat.last_name,
        username=chat.username,
    )


async def safe_edit(
    query: Any,
    text: str,
    *,
    parse_mode: str | None = "HTML",
    reply_markup: Any = None,
) -> bool:
    """Edit a callback query message — silently ignores benign errors."""
    try:
        await query.edit_message_text(
            text, parse_mode=parse_mode, reply_markup=reply_markup
        )
        return True
    except BadRequest as exc:
        msg = str(exc).lower()
        if "message is not modified" not in msg and "can't parse" not in msg:
            logger.debug("edit failed: %s", exc)
        return False


async def safe_send(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    text: str,
    *,
    parse_mode: str | None = "HTML",
    reply_markup: Any = None,
) -> bool:
    """Send message with 3-retry, RetryAfter backoff, and graceful Forbidden handling."""
    for attempt in range(3):
        try:
            await context.bot.send_message(
                chat_id, text, parse_mode=parse_mode, reply_markup=reply_markup
            )
            return True
        except RetryAfter as exc:
            await asyncio.sleep(exc.retry_after + 0.5)
        except (Forbidden, BadRequest) as exc:
            logger.debug("send to %s failed: %s", chat_id, exc)
            return False
        except TelegramError as exc:
            logger.warning("telegram send error %s: %s", chat_id, exc)
            if attempt == 2:
                return False
            await asyncio.sleep(0.5 * (attempt + 1))
    return False


async def is_valid_chat_session(db: Database, user_id: int, *, fresh: bool = False) -> bool:
    """True only when user and partner are both actively in the same chat.

    Uses cached reads by default on hot relay path. Callers that mutate
    state (end_chat, session connect) should pass fresh=True.
    """
    record = await db.get_user(user_id, fresh=fresh)
    if not record or record.get("state") != STATE_CHATTING:
        return False
    partner_id = record.get("partner_id")
    session_id = record.get("session_id")
    if not partner_id or not session_id:
        return False
    partner = await db.get_user(partner_id, fresh=fresh)
    if not partner or partner.get("state") != STATE_CHATTING:
        return False
    return partner.get("partner_id") == user_id and partner.get("session_id") == session_id


async def home_screen(
    db: Database,
    matcher: Matcher,
    user_id: int,
    *,
    brand: str = "AnoyBot",
    stats: dict | None = None,
) -> tuple[str, InlineKeyboardMarkup]:
    """Return the correct message + keyboard for the user's real state."""
    record = await db.get_user(user_id, fresh=True)
    if not record:
        return WELCOME.format(brand=brand), rules_keyboard()

    if not record.get("accepted_rules"):
        return WELCOME.format(brand=brand), rules_keyboard()

    gender = record.get("gender")
    looking = record.get("looking_for")
    state = record.get("state", STATE_IDLE)

    if state == STATE_CHATTING:
        if await is_valid_chat_session(db, user_id, fresh=True):
            return MATCHED, main_menu_keyboard(is_chatting=True)
        await db.set_state(user_id, STATE_IDLE, partner_id=None, session_id=None)
        state = STATE_IDLE

    if state == STATE_SEARCHING:
        pulse_idx = 0
        pulse = PULSE_FRAMES[pulse_idx % len(PULSE_FRAMES)]
        searching_count = stats.get("searching", 0) if stats else 0
        chatting_count = stats.get("chatting", 0) if stats else 0
        queue = max(searching_count, await matcher.queue_size())
        return (
            SEARCHING.format(pulse=pulse, online=queue, chatting=chatting_count),
            main_menu_keyboard(is_searching=True),
        )

    if not gender or not looking:
        from utils.texts import SETUP_GENDER
        from keyboards.buttons import gender_keyboard
        return SETUP_GENDER, gender_keyboard()

    queue = await matcher.queue_size()
    if stats:
        queue = max(stats.get("searching", 0), queue)
    return (
        READY.format(
            gender=gender_label(gender),
            looking=looking_label(looking),
            online=queue,
        ),
        main_menu_keyboard(),
    )


async def menu_for_user(db: Database, user_id: int) -> InlineKeyboardMarkup:
    """Get the right keyboard for user's current state."""
    record = await db.get_user(user_id)
    if not record:
        return main_menu_keyboard()
    state = record.get("state", STATE_IDLE)
    if state == STATE_CHATTING and not await is_valid_chat_session(db, user_id):
        state = STATE_IDLE
    return main_menu_keyboard(
        is_searching=state == STATE_SEARCHING,
        is_chatting=state == STATE_CHATTING,
    )


async def is_banned(db: Database, user_id: int) -> bool:
    """Cached read — ban state rarely changes, no need for fresh DB hit."""
    record = await db.get_user(user_id)
    return bool(record and record.get("is_banned"))


def track_search_card(
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
    chat_id: int,
    message_id: int,
) -> None:
    cards: dict = context.application.bot_data.setdefault("search_cards", {})
    cards[user_id] = (chat_id, message_id)


def untrack_search_card(context: ContextTypes.DEFAULT_TYPE, user_id: int) -> None:
    cards: dict = context.application.bot_data.get("search_cards", {})
    cards.pop(user_id, None)
