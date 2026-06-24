from telegram.ext import ContextTypes

from config import Config
from database import Database
from keyboards.buttons import feedback_keyboard, main_menu_keyboard
from services.logger import log_to_channel
from services.matcher import Matcher, STATE_CHATTING, STATE_IDLE
from utils.helpers import chat_to_user, safe_send, untrack_search_card
from utils.texts import CHAT_ENDED, CHAT_NEXT, CHAT_PARTNER_LEFT, FEEDBACK, MATCHED


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
        await matcher.leave(user_a)
        await matcher.leave(user_b)
        await db.set_state(user_a, STATE_IDLE)
        await db.set_state(user_b, STATE_IDLE)
        return

    untrack_search_card(context, user_a)
    untrack_search_card(context, user_b)

    await db.set_state(user_a, STATE_CHATTING, partner_id=user_b, session_id=session_id)
    await db.set_state(user_b, STATE_CHATTING, partner_id=user_a, session_id=session_id)
    await db.create_session(session_id, user_a, user_b)

    kb = main_menu_keyboard(is_chatting=True)
    for uid in (user_a, user_b):
        await safe_send(context, uid, MATCHED, reply_markup=kb)

    try:
        ua = chat_to_user(await context.bot.get_chat(user_a))
        ub = chat_to_user(await context.bot.get_chat(user_b))
        await log_to_channel(
            context,
            config.log_channel_id,
            db,
            event="🤝 Match Connected",
            user=ua,
            partner=ub,
            session_id=session_id,
            persist_message=False,
        )
    except Exception:
        pass


async def _send_feedback(context: ContextTypes.DEFAULT_TYPE, user_id: int, session_id: str) -> None:
    context.application.bot_data.setdefault("pending_feedback", {})[user_id] = session_id
    await safe_send(
        context,
        user_id,
        FEEDBACK,
        reply_markup=feedback_keyboard(),
    )


async def end_chat(
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
    reason: str = "ended",
    *,
    notify_initiator: bool = True,
    ask_feedback: bool = True,
) -> None:
    db: Database = context.bot_data["db"]
    config: Config = context.bot_data["config"]
    matcher: Matcher = context.bot_data["matcher"]

    record = await db.get_user(user_id)
    if not record or record.get("state") != STATE_CHATTING:
        return

    partner_id = record.get("partner_id")
    session_id = record.get("session_id")

    await db.set_state(user_id, STATE_IDLE, partner_id=None, session_id=None)
    if partner_id:
        await db.set_state(partner_id, STATE_IDLE, partner_id=None, session_id=None)

    if session_id:
        await db.end_session(session_id)

    kb = main_menu_keyboard()
    messages = {
        "ended": CHAT_ENDED,
        "next": CHAT_NEXT,
        "partner_left": CHAT_PARTNER_LEFT,
        "blocked": CHAT_ENDED,
    }

    if notify_initiator:
        await safe_send(context, user_id, messages.get(reason, CHAT_ENDED), reply_markup=kb)

    if partner_id and reason not in ("partner_left",):
        await safe_send(context, partner_id, CHAT_PARTNER_LEFT, reply_markup=kb)

    if ask_feedback and session_id and reason in ("ended", "next", "partner_left", "blocked"):
        if partner_id and reason != "blocked":
            await _send_feedback(context, partner_id, session_id)
        if reason != "blocked":
            await _send_feedback(context, user_id, session_id)

    try:
        u = chat_to_user(await context.bot.get_chat(user_id))
        await log_to_channel(
            context,
            config.log_channel_id,
            db,
            event=f"🔴 Session {reason.replace('_', ' ').title()}",
            user=u,
            session_id=session_id,
            extra=f"Partner: {partner_id}" if partner_id else None,
            persist_message=False,
        )
    except Exception:
        pass

    untrack_search_card(context, user_id)
    await matcher.leave(user_id)
    if partner_id:
        await matcher.leave(partner_id)
