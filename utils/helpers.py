import asyncio
import logging
from typing import Any

from telegram import Chat, User
from telegram.error import BadRequest, Forbidden, RetryAfter, TelegramError
from telegram.ext import ContextTypes

from database import Database
from keyboards.buttons import main_menu_keyboard
from services.matcher import STATE_CHATTING, STATE_SEARCHING

logger = logging.getLogger(__name__)


def chat_to_user(chat: Chat) -> User:
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
) -> None:
    try:
        await query.edit_message_text(
            text, parse_mode=parse_mode, reply_markup=reply_markup
        )
    except BadRequest as exc:
        msg = str(exc).lower()
        if "message is not modified" not in msg and "can't parse" not in msg:
            logger.debug("edit failed: %s", exc)


async def safe_send(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    text: str,
    *,
    parse_mode: str | None = "HTML",
    reply_markup: Any = None,
) -> bool:
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
            await asyncio.sleep(0.5)
    return False


async def menu_for_user(db: Database, user_id: int) -> Any:
    record = await db.get_user(user_id)
    if not record:
        return main_menu_keyboard()
    return main_menu_keyboard(
        is_searching=record.get("state") == STATE_SEARCHING,
        is_chatting=record.get("state") == STATE_CHATTING,
    )


async def is_banned(db: Database, user_id: int) -> bool:
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
