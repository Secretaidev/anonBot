"""Single status card — colorful buttons with automatic plain fallback."""

import logging
from typing import Any

from telegram.error import BadRequest, Forbidden, TelegramError

from keyboards.buttons import strip_styles
from utils.helpers import _get_app

logger = logging.getLogger(__name__)


def _cards(context) -> dict[int, tuple[int, int]]:
    app = _get_app(context)
    return app.bot_data.setdefault("status_cards", {})


def track_status_card(context, user_id: int, chat_id: int, message_id: int) -> None:
    _cards(context)[user_id] = (chat_id, message_id)


def untrack_status_card(context, user_id: int) -> None:
    _cards(context).pop(user_id, None)


def get_status_card(context, user_id: int) -> tuple[int, int] | None:
    return _cards(context).get(user_id)


async def _edit_or_send(
    bot,
    *,
    user_id: int,
    text: str,
    chat_id: int | None = None,
    message_id: int | None = None,
    parse_mode: str | None = "HTML",
    reply_markup: Any = None,
) -> tuple[bool, int | None, int | None]:
    """Styled keyboard first; plain fallback if Telegram rejects colors."""

    markups = [reply_markup]
    plain = strip_styles(reply_markup)
    if plain is not reply_markup:
        markups.append(plain)

    last_exc: Exception | None = None
    for markup in markups:
        try:
            if chat_id is not None and message_id is not None:
                await bot.edit_message_text(
                    text,
                    chat_id=chat_id,
                    message_id=message_id,
                    parse_mode=parse_mode,
                    reply_markup=markup,
                )
                return True, chat_id, message_id
            sent = await bot.send_message(
                user_id,
                text,
                parse_mode=parse_mode,
                reply_markup=markup,
            )
            return True, sent.chat_id, sent.message_id
        except BadRequest as exc:
            msg = str(exc).lower()
            if "message is not modified" in msg and chat_id and message_id:
                return True, chat_id, message_id
            last_exc = exc
            logger.info("markup attempt failed uid=%s: %s", user_id, exc)
            continue
        except (Forbidden, TelegramError) as exc:
            logger.warning("status card failed uid=%s: %s", user_id, exc)
            return False, None, None

    if last_exc:
        logger.warning("all markup attempts failed uid=%s: %s", user_id, last_exc)
    return False, None, None


async def update_status_card(
    context,
    user_id: int,
    text: str,
    *,
    parse_mode: str | None = "HTML",
    reply_markup: Any = None,
) -> bool:
    app = _get_app(context)
    cards = _cards(context)
    chat_id, msg_id = cards.get(user_id, (None, None))

    ok, new_chat, new_msg = await _edit_or_send(
        app.bot,
        user_id=user_id,
        text=text,
        chat_id=chat_id,
        message_id=msg_id,
        parse_mode=parse_mode,
        reply_markup=reply_markup,
    )
    if ok and new_chat is not None and new_msg is not None:
        cards[user_id] = (new_chat, new_msg)
    elif not ok:
        cards.pop(user_id, None)
    return ok


async def respond_card(
    context,
    user_id: int,
    query: Any,
    text: str,
    *,
    parse_mode: str | None = "HTML",
    reply_markup: Any = None,
) -> bool:
    chat_id = message_id = None
    if query and getattr(query, "message", None):
        chat_id = query.message.chat_id
        message_id = query.message.message_id

    app = _get_app(context)
    ok, new_chat, new_msg = await _edit_or_send(
        app.bot,
        user_id=user_id,
        text=text,
        chat_id=chat_id,
        message_id=message_id,
        parse_mode=parse_mode,
        reply_markup=reply_markup,
    )
    if ok and new_chat is not None and new_msg is not None:
        track_status_card(context, user_id, new_chat, new_msg)
    return ok
