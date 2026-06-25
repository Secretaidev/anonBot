"""Single status card — always responds, never silent failures."""

import logging
from typing import Any

from telegram.error import BadRequest, Forbidden, TelegramError

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


async def update_status_card(
    context,
    user_id: int,
    text: str,
    *,
    parse_mode: str | None = "HTML",
    reply_markup: Any = None,
) -> bool:
    """Edit tracked status card, or send a new one."""
    app = _get_app(context)
    bot = app.bot
    cards = _cards(context)

    if user_id in cards:
        chat_id, msg_id = cards[user_id]
        try:
            await bot.edit_message_text(
                text,
                chat_id=chat_id,
                message_id=msg_id,
                parse_mode=parse_mode,
                reply_markup=reply_markup,
            )
            return True
        except BadRequest as exc:
            msg = str(exc).lower()
            if "message is not modified" in msg:
                return True
            logger.info("status card edit failed uid=%s: %s", user_id, exc)
            cards.pop(user_id, None)
        except (Forbidden, TelegramError) as exc:
            logger.debug("status card edit %s: %s", user_id, exc)
            cards.pop(user_id, None)

    try:
        sent = await bot.send_message(
            user_id,
            text,
            parse_mode=parse_mode,
            reply_markup=reply_markup,
        )
        cards[user_id] = (sent.chat_id, sent.message_id)
        return True
    except (Forbidden, TelegramError) as exc:
        logger.warning("status card send failed uid=%s: %s", user_id, exc)
        return False


async def respond_card(
    context,
    user_id: int,
    query: Any,
    text: str,
    *,
    parse_mode: str | None = "HTML",
    reply_markup: Any = None,
) -> bool:
    """Edit the button message first — fallback to status card send."""
    if query and getattr(query, "message", None):
        try:
            await query.edit_message_text(
                text,
                parse_mode=parse_mode,
                reply_markup=reply_markup,
            )
            track_status_card(
                context,
                user_id,
                query.message.chat_id,
                query.message.message_id,
            )
            return True
        except BadRequest as exc:
            msg = str(exc).lower()
            if "message is not modified" in msg:
                track_status_card(
                    context,
                    user_id,
                    query.message.chat_id,
                    query.message.message_id,
                )
                return True
            logger.info("callback edit failed uid=%s: %s", user_id, exc)
        except (Forbidden, TelegramError) as exc:
            logger.warning("callback edit error uid=%s: %s", user_id, exc)

    return await update_status_card(
        context, user_id, text, parse_mode=parse_mode, reply_markup=reply_markup
    )
