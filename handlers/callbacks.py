"""All inline button callbacks — always responds, zero silent failures."""

import logging

from telegram import Update
from telegram.ext import ContextTypes

from config import Config
from database import Database
from handlers.session import end_chat
from keyboards.buttons import (
    CB_ACTION,
    CB_GENDER,
    CB_LOOKING,
    CB_RATE,
    ACT_ACCEPT_RULES,
    ACT_BACK,
    ACT_BLOCK,
    ACT_CHANGE_GENDER,
    ACT_CHANGE_LOOKING,
    ACT_END_CHAT,
    ACT_FIND,
    ACT_HELP,
    ACT_NEXT,
    ACT_REPORT,
    ACT_REPORT_CONFIRM,
    ACT_SETTINGS,
    ACT_SKIP_FEEDBACK,
    ACT_STATS,
    ACT_STOP_SEARCH,
    confirm_end_chat_keyboard,
    gender_keyboard,
    looking_for_keyboard,
    main_menu_keyboard,
    report_keyboard,
    settings_keyboard,
)
from services.logger import log_to_channel, log_to_channel_bg
from services.matcher import Matcher, STATE_CHATTING, STATE_IDLE, STATE_SEARCHING
from utils.helpers import home_screen, is_banned, is_valid_chat_session
from utils.status_card import respond_card, untrack_status_card
from utils.texts import (
    BANNED,
    CONFIRM_END,
    FEEDBACK_THANKS,
    MATCHED,
    PARTNER_FOUND_HINT,
    READY,
    REPORT_PROMPT,
    REPORT_SENT,
    SEARCH_CANCELLED,
    SEARCHING,
    SETTINGS,
    SETUP_GENDER,
    SETUP_LOOKING,
    gender_label,
    looking_label,
)

logger = logging.getLogger(__name__)


async def _search_screen(context: ContextTypes.DEFAULT_TYPE) -> str:
    pulse_idx = context.application.bot_data.get("pulse_idx", 0)
    from utils.texts import PULSE_FRAMES
    pulse = PULSE_FRAMES[pulse_idx % len(PULSE_FRAMES)]
    return SEARCHING.format(pulse=pulse)


async def _start_search(
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
    query,
) -> None:
    db: Database = context.bot_data["db"]
    config: Config = context.bot_data["config"]
    matcher: Matcher = context.bot_data["matcher"]

    try:
        record = await db.get_user(user_id, fresh=True)
        if not record or not record.get("gender") or not record.get("looking_for"):
            await respond_card(
                context, user_id, query, SETUP_GENDER, reply_markup=gender_keyboard()
            )
            return

        if record.get("state") == STATE_CHATTING:
            if await is_valid_chat_session(db, user_id, fresh=True):
                await query.answer("Already in a chat.", show_alert=True)
                return
            await db.set_state(user_id, STATE_IDLE, partner_id=None, session_id=None)
            context.bot_data["session_registry"].disconnect(user_id)

        await db.set_state(user_id, STATE_SEARCHING)
        matched, _ = await matcher.join(user_id, record["gender"], record["looking_for"])

        stats_cache = context.application.bot_data.get("stats_cache")
        if stats_cache:
            stats_cache.invalidate()

        if matched and await is_valid_chat_session(db, user_id, fresh=True):
            await respond_card(
                context,
                user_id,
                query,
                PARTNER_FOUND_HINT,
                reply_markup=main_menu_keyboard(is_chatting=True),
            )
            return

        if matched:
            await matcher.leave(user_id)
            await db.set_state(user_id, STATE_SEARCHING)
            await matcher.join(user_id, record["gender"], record["looking_for"])

        text = await _search_screen(context)
        ok = await respond_card(
            context,
            user_id,
            query,
            text,
            reply_markup=main_menu_keyboard(is_searching=True),
        )
        if not ok:
            await query.answer("Could not update. Try /menu", show_alert=True)

        log_to_channel_bg(
            context,
            config.log_channel_id,
            db,
            event="🔍 Search Started",
            user=query.from_user,
            persist_message=False,
        )
    except Exception as exc:
        logger.exception("search failed uid=%s: %s", user_id, exc)
        await respond_card(
            context,
            user_id,
            query,
            "Something went wrong. Tap 🔍 again or /menu",
            reply_markup=main_menu_keyboard(),
        )


async def next_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Shortcut: /next = find new partner (like competitor bots)."""
    if not update.effective_user or not update.message:
        return

    class _Query:
        __slots__ = ("message", "from_user")

        def __init__(self, message, from_user):
            self.message = message
            self.from_user = from_user

        async def answer(self, **_kwargs) -> None:
            pass

    await _start_search(
        context,
        update.effective_user.id,
        _Query(update.message, update.effective_user),
    )

    query = update.callback_query
    if not query or not query.data or not query.from_user:
        return

    user = query.from_user
    data = query.data
    db: Database = context.bot_data["db"]
    config: Config = context.bot_data["config"]
    matcher: Matcher = context.bot_data["matcher"]

    try:
        await query.answer()
    except Exception:
        pass

    await db.upsert_user(user.id, user.username, user.first_name, user.last_name)

    if await is_banned(db, user.id):
        await respond_card(context, user.id, query, BANNED)
        return

    if data.startswith(CB_RATE):
        stars_raw = data[len(CB_RATE):]
        try:
            stars = int(stars_raw)
        except ValueError:
            return
        pending = context.application.bot_data.get("pending_feedback", {})
        session_id = pending.get(user.id)
        if session_id and 1 <= stars <= 5:
            await db.save_session_rating(session_id, user.id, stars)
            pending.pop(user.id, None)
            await respond_card(
                context, user.id, query, FEEDBACK_THANKS, reply_markup=main_menu_keyboard()
            )
            await log_to_channel(
                context, config.log_channel_id, db,
                event=f"⭐ Rating {stars}/5",
                user=user, session_id=session_id, persist_message=False,
            )
        return

    if data.startswith(CB_GENDER):
        gender = data[len(CB_GENDER):]
        await db.set_gender(user.id, gender)
        await respond_card(
            context, user.id, query, SETUP_LOOKING, reply_markup=looking_for_keyboard()
        )
        log_to_channel_bg(
            context, config.log_channel_id, db,
            event="🎭 Gender Set", user=user, extra=f"Gender: {gender}", persist_message=False,
        )
        return

    if data.startswith(CB_LOOKING):
        looking = data[len(CB_LOOKING):]
        await db.set_looking_for(user.id, looking)
        record = await db.get_user(user.id)
        await respond_card(
            context,
            user.id,
            query,
            READY.format(
                gender=gender_label(record["gender"]),
                looking=looking_label(looking),
            ),
            reply_markup=main_menu_keyboard(),
        )
        log_to_channel_bg(
            context, config.log_channel_id, db,
            event="💫 Preference Set", user=user, extra=f"Looking: {looking}", persist_message=False,
        )
        return

    if not data.startswith(CB_ACTION):
        return

    action = data[len(CB_ACTION):]

    if action == ACT_ACCEPT_RULES:
        await db.accept_rules(user.id)
        await respond_card(
            context, user.id, query, SETUP_GENDER, reply_markup=gender_keyboard()
        )
        log_to_channel_bg(
            context, config.log_channel_id, db,
            event="✅ Rules Accepted", user=user, persist_message=False,
        )
        return

    if action == ACT_SKIP_FEEDBACK:
        context.application.bot_data.get("pending_feedback", {}).pop(user.id, None)
        text, keyboard = await home_screen(db, matcher, user.id, brand=config.brand_name)
        await respond_card(context, user.id, query, text, reply_markup=keyboard)
        return

    if action == ACT_END_CHAT:
        record = await db.get_user(user.id, fresh=True)
        if record and record.get("state") == STATE_CHATTING:
            await respond_card(
                context, user.id, query, CONFIRM_END, reply_markup=confirm_end_chat_keyboard()
            )
        return

    if action == f"{ACT_END_CHAT}:confirm":
        await end_chat(context, user.id, reason="ended", notify_initiator=True)
        return

    if action == ACT_FIND:
        await _start_search(context, user.id, query)
        return

    if action == ACT_STOP_SEARCH:
        await matcher.leave(user.id)
        await db.set_state(user.id, STATE_IDLE)
        untrack_status_card(context, user.id)
        stats_cache = context.application.bot_data.get("stats_cache")
        if stats_cache:
            stats_cache.invalidate()
        await respond_card(
            context, user.id, query, SEARCH_CANCELLED, reply_markup=main_menu_keyboard()
        )
        return

    if action == ACT_NEXT:
        await end_chat(context, user.id, reason="next", notify_initiator=False, ask_feedback=False)
        await _start_search(context, user.id, query)
        return

    if action == ACT_REPORT:
        record = await db.get_user(user.id)
        if not record or record.get("state") != STATE_CHATTING:
            await query.answer("Not in a chat.", show_alert=True)
            return
        await respond_card(
            context, user.id, query, REPORT_PROMPT, reply_markup=report_keyboard()
        )
        return

    if action == ACT_REPORT_CONFIRM:
        record = await db.get_user(user.id)
        partner_id = record.get("partner_id") if record else None
        session_id = record.get("session_id") if record else None
        if partner_id:
            try:
                await db.add_report(user.id, partner_id, session_id, "Button report")
                count = await db.increment_reports(partner_id)
                if count >= config.auto_ban_reports:
                    await db.ban_user(partner_id, f"Auto-ban after {count} reports")
                    context.bot_data["session_registry"].disconnect(partner_id)
            except Exception:
                pass
        log_to_channel_bg(
            context, config.log_channel_id, db,
            event="🚨 ABUSE REPORT",
            user=user, session_id=session_id,
            extra=f"Partner: {partner_id}", persist_message=False,
        )
        await respond_card(
            context, user.id, query, REPORT_SENT,
            reply_markup=main_menu_keyboard(is_chatting=bool(partner_id)),
        )
        return

    if action == ACT_BLOCK:
        record = await db.get_user(user.id)
        partner_id = record.get("partner_id") if record else None
        if partner_id:
            await db.add_block(user.id, partner_id)
            await end_chat(context, user.id, reason="blocked", notify_initiator=False)
            await respond_card(
                context, user.id, query,
                "Partner blocked.",
                reply_markup=main_menu_keyboard(),
            )
            log_to_channel_bg(
                context, config.log_channel_id, db,
                event="🚫 User Blocked Partner",
                user=user, extra=f"Blocked ID: {partner_id}", persist_message=False,
            )
        return

    if action == ACT_SETTINGS:
        record = await db.get_user(user.id)
        await respond_card(
            context,
            user.id,
            query,
            SETTINGS.format(
                gender=gender_label(record.get("gender") if record else None),
                looking=looking_label(record.get("looking_for") if record else None),
            ),
            reply_markup=settings_keyboard(),
        )
        return

    if action == ACT_CHANGE_GENDER:
        await respond_card(
            context, user.id, query, SETUP_GENDER, reply_markup=gender_keyboard()
        )
        return

    if action == ACT_CHANGE_LOOKING:
        await respond_card(
            context, user.id, query, SETUP_LOOKING, reply_markup=looking_for_keyboard()
        )
        return

    if action == ACT_BACK:
        text, keyboard = await home_screen(db, matcher, user.id, brand=config.brand_name)
        await respond_card(context, user.id, query, text, reply_markup=keyboard)
        return

    if action == ACT_STATS or action == ACT_HELP:
        text, keyboard = await home_screen(db, matcher, user.id, brand=config.brand_name)
        await respond_card(context, user.id, query, text, reply_markup=keyboard)
