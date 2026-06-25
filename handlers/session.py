"""Session lifecycle — one status card, zero chat spam."""

import asyncio
import logging

from telegram.ext import ContextTypes

from config import Config
from database import Database
from keyboards.buttons import feedback_keyboard, main_menu_keyboard
from services.logger import log_to_channel_bg
from services.matcher import Matcher, STATE_CHATTING, STATE_IDLE, STATE_SEARCHING
from services.session_registry import SessionRegistry
from utils.helpers import _get_app, is_valid_chat_session
from utils.status_card import untrack_status_card, update_status_card
from utils.texts import (
    CHAT_ENDED,
    CHAT_PARTNER_LEFT,
    FEEDBACK,
    MATCHED,
    PULSE_FRAMES,
    SEARCH_BLOCKED_RETRY,
)

logger = logging.getLogger(__name__)


def _pulse() -> str:
    return PULSE_FRAMES[0]


async def notify_matched(
    context: ContextTypes.DEFAULT_TYPE,
    user_a: int,
    user_b: int,
    session_id: str,
) -> None:
    db: Database = context.bot_data["db"]
    config: Config = context.bot_data["config"]
    matcher: Matcher = context.bot_data["matcher"]
    kb = main_menu_keyboard(is_chatting=True)

    if await db.is_blocked(user_a, user_b) or await db.is_blocked(user_b, user_a):
        await asyncio.gather(
            db.set_state(user_a, STATE_IDLE),
            db.set_state(user_b, STATE_IDLE),
        )
        untrack_status_card(context, user_a)
        untrack_status_card(context, user_b)

        retry_kb = main_menu_keyboard(is_searching=True)
        retry_text = SEARCH_BLOCKED_RETRY.format(pulse=_pulse())
        for uid in (user_a, user_b):
            record = await db.get_user(uid, fresh=True)
            if not record:
                continue
            gender = record.get("gender")
            looking = record.get("looking_for")
            if not gender or not looking:
                await update_status_card(context, uid, retry_text, reply_markup=main_menu_keyboard())
                continue
            await db.set_state(uid, STATE_SEARCHING)
            matched, _ = await matcher.join(uid, gender, looking)
            if not matched:
                await update_status_card(context, uid, retry_text, reply_markup=retry_kb)
        return

    # Keep tracked status card — edit in place on match
    await asyncio.gather(
        db.set_state(user_a, STATE_CHATTING, partner_id=user_b, session_id=session_id),
        db.set_state(user_b, STATE_CHATTING, partner_id=user_a, session_id=session_id),
        db.create_session(session_id, user_a, user_b),
    )

    stats_cache = context.bot_data.get("stats_cache")
    if stats_cache:
        stats_cache.invalidate()

    if not await is_valid_chat_session(db, user_a, fresh=True):
        logger.warning("match session invalid after connect: %s <-> %s", user_a, user_b)
        return

    registry: SessionRegistry = context.bot_data["session_registry"]
    registry.connect(user_a, user_b, session_id)

    await asyncio.gather(
        update_status_card(context, user_a, MATCHED, reply_markup=kb),
        update_status_card(context, user_b, MATCHED, reply_markup=kb),
    )

    log_to_channel_bg(
        context,
        config.log_channel_id,
        context.bot_data["db"],
        event="🤝 Match Connected",
        extra=f"User A: {user_a} | User B: {user_b} | Session: {session_id}",
        persist_message=False,
    )


async def end_chat(
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
    reason: str = "ended",
    *,
    notify_initiator: bool = True,
    ask_feedback: bool = True,
) -> None:
    """End chat — updates status card only, never floods chat with system msgs."""
    db: Database = context.bot_data["db"]
    config: Config = context.bot_data["config"]
    matcher: Matcher = context.bot_data["matcher"]

    record = await db.get_user(user_id, fresh=True)
    if not record or record.get("state") != STATE_CHATTING:
        return

    partner_id = record.get("partner_id")
    session_id = record.get("session_id")

    registry: SessionRegistry = context.bot_data["session_registry"]
    registry.disconnect(user_id)

    reset_tasks = [db.set_state(user_id, STATE_IDLE, partner_id=None, session_id=None)]
    if partner_id:
        reset_tasks.append(db.set_state(partner_id, STATE_IDLE, partner_id=None, session_id=None))
    await asyncio.gather(*reset_tasks)

    stats_cache = context.bot_data.get("stats_cache")
    if stats_cache:
        stats_cache.invalidate()

    if session_id:
        asyncio.create_task(db.end_session(session_id)).add_done_callback(
            lambda t: logger.debug("end_session err: %s", t.exception()) if not t.cancelled() and t.exception() else None
        )

    kb_home = main_menu_keyboard()
    fb_kb = feedback_keyboard()

    if reason == "next":
        ask_feedback = False

    bot_data = _get_app(context).bot_data
    card_tasks = []
    if notify_initiator:
        if ask_feedback and session_id and reason in ("ended", "partner_left", "blocked"):
            bot_data.setdefault("pending_feedback", {})[user_id] = session_id
            card_tasks.append(
                update_status_card(context, user_id, FEEDBACK, reply_markup=fb_kb)
            )
        else:
            card_tasks.append(
                update_status_card(context, user_id, CHAT_ENDED, reply_markup=kb_home)
            )

    if partner_id and reason not in ("partner_left",):
        if ask_feedback and session_id and reason != "next":
            bot_data.setdefault("pending_feedback", {})[partner_id] = session_id
            card_tasks.append(
                update_status_card(context, partner_id, FEEDBACK, reply_markup=fb_kb)
            )
        else:
            card_tasks.append(
                update_status_card(context, partner_id, CHAT_PARTNER_LEFT, reply_markup=kb_home)
            )

    if card_tasks:
        await asyncio.gather(*card_tasks)

    log_to_channel_bg(
        context,
        config.log_channel_id,
        db,
        event=f"🔴 Session {reason.replace('_', ' ').title()}",
        extra=f"User: {user_id} | Partner: {partner_id}" if partner_id else f"User: {user_id}",
        persist_message=False,
    )

    await matcher.leave(user_id)
    if partner_id:
        await matcher.leave(partner_id)
