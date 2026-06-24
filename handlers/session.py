"""Session lifecycle — match notification, chat end, feedback.

Speed optimizations:
  • Parallel set_state() for both users via asyncio.gather()
  • Fire-and-forget logging — never blocks response
  • get_chat() in background — doesn't delay match notification
  • Double end-chat guard with fresh state check
"""

import asyncio
import logging

from telegram.ext import ContextTypes

from config import Config
from database import Database
from keyboards.buttons import feedback_keyboard, main_menu_keyboard
from services.logger import log_to_channel_bg
from services.matcher import Matcher, STATE_CHATTING, STATE_IDLE, STATE_SEARCHING
from utils.helpers import is_valid_chat_session, safe_send, untrack_search_card
from utils.texts import (
    CHAT_ENDED, CHAT_NEXT, CHAT_PARTNER_LEFT,
    FEEDBACK, MATCHED, SEARCH_BLOCKED_RETRY,
)

logger = logging.getLogger(__name__)


async def notify_matched(
    context: ContextTypes.DEFAULT_TYPE,
    user_a: int,
    user_b: int,
    session_id: str,
) -> None:
    db: Database = context.bot_data["db"]
    config: Config = context.bot_data["config"]
    matcher: Matcher = context.bot_data["matcher"]

    if await db.is_blocked(user_a, user_b) or await db.is_blocked(user_b, user_a):
        # Parallel reset for both users
        await asyncio.gather(
            db.set_state(user_a, STATE_IDLE),
            db.set_state(user_b, STATE_IDLE),
        )
        untrack_search_card(context, user_a)
        untrack_search_card(context, user_b)

        for uid in (user_a, user_b):
            record = await db.get_user(uid, fresh=True)
            if not record:
                continue
            gender = record.get("gender")
            looking = record.get("looking_for")
            if not gender or not looking:
                await safe_send(context, uid, SEARCH_BLOCKED_RETRY, reply_markup=main_menu_keyboard())
                continue
            await db.set_state(uid, STATE_SEARCHING)
            matched, _ = await matcher.join(uid, gender, looking)
            if not matched:
                await safe_send(context, uid, SEARCH_BLOCKED_RETRY, reply_markup=main_menu_keyboard(is_searching=True))
        return

    untrack_search_card(context, user_a)
    untrack_search_card(context, user_b)

    # Parallel: set both users + create session simultaneously
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

    # Send match notifications in parallel
    kb = main_menu_keyboard(is_chatting=True)
    await asyncio.gather(
        safe_send(context, user_a, MATCHED, reply_markup=kb),
        safe_send(context, user_b, MATCHED, reply_markup=kb),
    )

    # Fire-and-forget logging
    log_to_channel_bg(
        context,
        config.log_channel_id,
        context.bot_data["db"],
        event="🤝 Match Connected",
        extra=f"User A: {user_a} | User B: {user_b} | Session: {session_id}",
        persist_message=False,
    )


async def _send_feedback(context: ContextTypes.DEFAULT_TYPE, user_id: int, session_id: str) -> None:
    context.application.bot_data.setdefault("pending_feedback", {})[user_id] = session_id
    await safe_send(context, user_id, FEEDBACK, reply_markup=feedback_keyboard())


async def end_chat(
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
    reason: str = "ended",
    *,
    notify_initiator: bool = True,
    ask_feedback: bool = True,
) -> None:
    """End chat with double-execution guard + parallel resets."""
    db: Database = context.bot_data["db"]
    config: Config = context.bot_data["config"]
    matcher: Matcher = context.bot_data["matcher"]

    record = await db.get_user(user_id, fresh=True)
    if not record or record.get("state") != STATE_CHATTING:
        return  # Already ended — no-op

    partner_id = record.get("partner_id")
    session_id = record.get("session_id")

    # Parallel reset — prevents double-execution race
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

    kb = main_menu_keyboard()
    messages = {
        "ended": CHAT_ENDED,
        "next": CHAT_NEXT,
        "partner_left": CHAT_PARTNER_LEFT,
        "blocked": CHAT_ENDED,
    }

    # Send notifications in parallel
    send_tasks = []
    if notify_initiator:
        send_tasks.append(safe_send(context, user_id, messages.get(reason, CHAT_ENDED), reply_markup=kb))
    if partner_id and reason not in ("partner_left",):
        send_tasks.append(safe_send(context, partner_id, CHAT_PARTNER_LEFT, reply_markup=kb))
    if send_tasks:
        await asyncio.gather(*send_tasks)

    # Feedback
    if ask_feedback and session_id and reason in ("ended", "next", "partner_left", "blocked"):
        feedback_tasks = []
        if reason == "blocked":
            feedback_tasks.append(_send_feedback(context, user_id, session_id))
        else:
            if partner_id:
                feedback_tasks.append(_send_feedback(context, partner_id, session_id))
            feedback_tasks.append(_send_feedback(context, user_id, session_id))
        if feedback_tasks:
            await asyncio.gather(*feedback_tasks)

    # Fire-and-forget cleanup
    log_to_channel_bg(
        context,
        config.log_channel_id,
        db,
        event=f"🔴 Session {reason.replace('_', ' ').title()}",
        extra=f"User: {user_id} | Partner: {partner_id}" if partner_id else f"User: {user_id}",
        persist_message=False,
    )

    untrack_search_card(context, user_id)
    await matcher.leave(user_id)
    if partner_id:
        await matcher.leave(partner_id)
