"""Handler for /stop — edits status card, no new messages."""

from telegram import Update
from telegram.ext import ContextTypes

from database import Database
from handlers.session import end_chat
from keyboards.buttons import main_menu_keyboard
from services.matcher import Matcher, STATE_CHATTING, STATE_IDLE, STATE_SEARCHING
from utils.helpers import is_banned, menu_for_user
from utils.status_card import untrack_status_card, update_status_card
from utils.texts import BANNED, STOP_CHAT, STOP_IDLE, STOP_SEARCH


async def stop_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message:
        return

    user = update.effective_user
    db: Database = context.bot_data["db"]
    matcher: Matcher = context.bot_data["matcher"]

    if await is_banned(db, user.id):
        await update.message.reply_text(BANNED, parse_mode="HTML")
        return

    record = await db.get_user(user.id)
    if not record:
        await update_status_card(context, user.id, STOP_IDLE, reply_markup=main_menu_keyboard())
        return

    state = record.get("state", STATE_IDLE)

    if state == STATE_SEARCHING:
        await matcher.leave(user.id)
        await db.set_state(user.id, STATE_IDLE)
        untrack_status_card(context, user.id)
        stats_cache = context.application.bot_data.get("stats_cache")
        if stats_cache:
            stats_cache.invalidate()
        await update_status_card(context, user.id, STOP_SEARCH, reply_markup=main_menu_keyboard())
        return

    if state == STATE_CHATTING:
        await end_chat(
            context, user.id, reason="ended",
            notify_initiator=True, ask_feedback=False,
        )
        return

    await update_status_card(
        context,
        user.id,
        STOP_IDLE,
        reply_markup=await menu_for_user(db, user.id),
    )
