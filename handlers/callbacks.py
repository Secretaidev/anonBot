from telegram import Update
from telegram.ext import ContextTypes

from config import Config
from database import Database
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
    rules_keyboard,
    settings_keyboard,
)
from services.logger import log_to_channel
from services.matcher import Matcher, STATE_CHATTING, STATE_IDLE, STATE_SEARCHING
from handlers.session import end_chat
from utils.helpers import (
    is_banned,
    menu_for_user,
    safe_edit,
    track_search_card,
    untrack_search_card,
)
from utils.texts import (
    BANNED,
    CONFIRM_END,
    FEEDBACK_THANKS,
    HELP,
    PARTNER_FOUND_HINT,
    READY,
    REPORT_PROMPT,
    REPORT_SENT,
    SEARCH_CANCELLED,
    SEARCHING,
    SETTINGS,
    SETUP_GENDER,
    SETUP_LOOKING,
    STATS,
    WELCOME,
    gender_label,
    looking_label,
)


async def _search_screen(
    context: ContextTypes.DEFAULT_TYPE,
    matcher: Matcher,
    stats: dict,
) -> str:
    pulse_idx = context.application.bot_data.get("pulse_idx", 0)
    from utils.texts import PULSE_FRAMES
    pulse = PULSE_FRAMES[pulse_idx % len(PULSE_FRAMES)]
    return SEARCHING.format(
        pulse=pulse,
        online=max(stats.get("searching", 0), await matcher.queue_size()),
        chatting=stats["chatting"],
    )


async def _start_search(
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
    query,
) -> None:
    db: Database = context.bot_data["db"]
    config: Config = context.bot_data["config"]
    matcher: Matcher = context.bot_data["matcher"]

    record = await db.get_user(user_id)
    if not record or not record.get("gender") or not record.get("looking_for"):
        await safe_edit(query, SETUP_GENDER, reply_markup=gender_keyboard())
        return

    if record.get("state") == STATE_CHATTING:
        await query.answer("Already in a chat.", show_alert=True)
        return

    await db.set_state(user_id, STATE_SEARCHING)
    matched, _ = await matcher.join(user_id, record["gender"], record["looking_for"])
    stats_cache = context.application.bot_data.get("stats_cache")
    if stats_cache:
        stats_cache.invalidate()

    if matched:
        untrack_search_card(context, user_id)
        await safe_edit(
            query,
            PARTNER_FOUND_HINT,
            reply_markup=main_menu_keyboard(is_chatting=True),
        )
    else:
        stats_cache = context.application.bot_data["stats_cache"]
        stats = await stats_cache.get(context.bot_data["db"].get_stats)
        text = await _search_screen(context, matcher, stats)
        await safe_edit(
            query,
            text,
            reply_markup=main_menu_keyboard(is_searching=True),
        )
        if query.message:
            track_search_card(
                context, user_id, query.message.chat_id, query.message.message_id
            )
        await log_to_channel(
            context,
            config.log_channel_id,
            db,
            event="🔍 Search Started",
            user=query.from_user,
            persist_message=False,
        )


async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not query.data or not query.from_user:
        return

    await query.answer()
    data = query.data
    user = query.from_user
    db: Database = context.bot_data["db"]
    config: Config = context.bot_data["config"]
    matcher: Matcher = context.bot_data["matcher"]

    await db.upsert_user(user.id, user.username, user.first_name, user.last_name)

    if await is_banned(db, user.id):
        await safe_edit(query, BANNED)
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
            await safe_edit(query, FEEDBACK_THANKS, reply_markup=main_menu_keyboard())
            await log_to_channel(
                context, config.log_channel_id, db,
                event=f"⭐ Rating {stars}/5",
                user=user, session_id=session_id, persist_message=False,
            )
        return

    if data.startswith(CB_GENDER):
        gender = data[len(CB_GENDER):]
        await db.set_gender(user.id, gender)
        await safe_edit(query, SETUP_LOOKING, reply_markup=looking_for_keyboard())
        await log_to_channel(
            context, config.log_channel_id, db,
            event="🎭 Gender Set", user=user, extra=f"Gender: {gender}", persist_message=False,
        )
        return

    if data.startswith(CB_LOOKING):
        looking = data[len(CB_LOOKING):]
        await db.set_looking_for(user.id, looking)
        record = await db.get_user(user.id)
        online = await matcher.queue_size()
        await safe_edit(
            query,
            READY.format(
                gender=gender_label(record["gender"]),
                looking=looking_label(looking),
                online=online,
            ),
            reply_markup=main_menu_keyboard(),
        )
        await log_to_channel(
            context, config.log_channel_id, db,
            event="💫 Preference Set", user=user, extra=f"Looking: {looking}", persist_message=False,
        )
        return

    if not data.startswith(CB_ACTION):
        return

    action = data[len(CB_ACTION):]

    if action == ACT_ACCEPT_RULES:
        await db.accept_rules(user.id)
        await safe_edit(query, SETUP_GENDER, reply_markup=gender_keyboard())
        await log_to_channel(
            context, config.log_channel_id, db,
            event="✅ Rules Accepted", user=user, persist_message=False,
        )
        return

    if action == ACT_SKIP_FEEDBACK:
        pending = context.application.bot_data.get("pending_feedback", {})
        pending.pop(user.id, None)
        record = await db.get_user(user.id)
        if record and record.get("gender") and record.get("looking_for"):
            online = await matcher.queue_size()
            await safe_edit(
                query,
                READY.format(
                    gender=gender_label(record["gender"]),
                    looking=looking_label(record["looking_for"]),
                    online=online,
                ),
                reply_markup=await menu_for_user(db, user.id),
            )
        else:
            await safe_edit(query, SETUP_GENDER, reply_markup=gender_keyboard())
        return

    if action == ACT_END_CHAT:
        record = await db.get_user(user.id)
        if record and record.get("state") == STATE_CHATTING:
            await safe_edit(query, CONFIRM_END, reply_markup=confirm_end_chat_keyboard())
        return

    if action == f"{ACT_END_CHAT}:confirm":
        await end_chat(context, user.id, reason="ended", notify_initiator=False)
        await safe_edit(query, "🔴 Chat ended.", reply_markup=main_menu_keyboard())
        return

    if action == ACT_FIND:
        await _start_search(context, user.id, query)
        return

    if action == ACT_STOP_SEARCH:
        await matcher.leave(user.id)
        await db.set_state(user.id, STATE_IDLE)
        untrack_search_card(context, user.id)
        stats_cache = context.application.bot_data.get("stats_cache")
        if stats_cache:
            stats_cache.invalidate()
        await safe_edit(query, SEARCH_CANCELLED, reply_markup=main_menu_keyboard())
        return

    if action == ACT_NEXT:
        await end_chat(context, user.id, reason="next", notify_initiator=False)
        await _start_search(context, user.id, query)
        return

    if action == ACT_REPORT:
        record = await db.get_user(user.id)
        if not record or record.get("state") != STATE_CHATTING:
            await query.answer("Not in a chat.", show_alert=True)
            return
        await safe_edit(query, REPORT_PROMPT, reply_markup=report_keyboard())
        return

    if action == ACT_REPORT_CONFIRM:
        record = await db.get_user(user.id)
        partner_id = record.get("partner_id") if record else None
        session_id = record.get("session_id") if record else None
        partner_user = None
        if partner_id:
            try:
                from utils.helpers import chat_to_user
                partner_user = chat_to_user(await context.bot.get_chat(partner_id))
                await db.add_report(user.id, partner_id, session_id, "Button report")
                count = await db.increment_reports(partner_id)
                if count >= config.auto_ban_reports:
                    await db.ban_user(partner_id, f"Auto-ban after {count} reports")
            except Exception:
                pass
        await log_to_channel(
            context, config.log_channel_id, db,
            event="🚨 ABUSE REPORT",
            user=user, partner=partner_user, session_id=session_id,
            extra="Reported via button", persist_message=False,
        )
        await safe_edit(
            query, REPORT_SENT,
            reply_markup=main_menu_keyboard(is_chatting=bool(partner_id)),
        )
        return

    if action == ACT_BLOCK:
        record = await db.get_user(user.id)
        partner_id = record.get("partner_id") if record else None
        if partner_id:
            await db.add_block(user.id, partner_id)
            await end_chat(context, user.id, reason="blocked", notify_initiator=False, ask_feedback=False)
            await safe_edit(
                query,
                "🚫 Partner blocked. They won't be matched with you again.",
                reply_markup=main_menu_keyboard(),
            )
            await log_to_channel(
                context, config.log_channel_id, db,
                event="🚫 User Blocked Partner",
                user=user, extra=f"Blocked ID: {partner_id}", persist_message=False,
            )
        return

    if action == ACT_SETTINGS:
        record = await db.get_user(user.id)
        await safe_edit(
            query,
            SETTINGS.format(
                gender=gender_label(record.get("gender") if record else None),
                looking=looking_label(record.get("looking_for") if record else None),
            ),
            reply_markup=settings_keyboard(),
        )
        return

    if action == ACT_CHANGE_GENDER:
        await safe_edit(query, SETUP_GENDER, reply_markup=gender_keyboard())
        return

    if action == ACT_CHANGE_LOOKING:
        await safe_edit(query, SETUP_LOOKING, reply_markup=looking_for_keyboard())
        return

    if action == ACT_STATS:
        stats_cache = context.application.bot_data["stats_cache"]
        stats = await stats_cache.get(db.get_stats)
        queue = await matcher.queue_size()
        record = await db.get_user(user.id)
        await safe_edit(
            query,
            STATS.format(
                users=stats["users"],
                searching=stats["searching"],
                chatting=stats["chatting"],
                sessions=stats["sessions"],
                queue=queue,
                banned=stats["banned"],
                my_sessions=record.get("total_sessions", 0) if record else 0,
                my_messages=record.get("total_messages", 0) if record else 0,
            ),
            reply_markup=await menu_for_user(db, user.id),
        )
        return

    if action == ACT_HELP:
        await safe_edit(query, HELP, reply_markup=await menu_for_user(db, user.id))
        return

    if action == ACT_BACK:
        record = await db.get_user(user.id)
        if record and record.get("gender") and record.get("looking_for"):
            online = await matcher.queue_size()
            await safe_edit(
                query,
                READY.format(
                    gender=gender_label(record["gender"]),
                    looking=looking_label(record["looking_for"]),
                    online=online,
                ),
                reply_markup=await menu_for_user(db, user.id),
            )
        elif record and record.get("accepted_rules"):
            await safe_edit(query, SETUP_GENDER, reply_markup=gender_keyboard())
        else:
            await safe_edit(
                query,
                WELCOME.format(brand=config.brand_name),
                reply_markup=rules_keyboard(),
            )
