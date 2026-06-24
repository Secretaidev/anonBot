"""Background jobs — search pulse animation, startup notify, bot commands.

Performance improvements:
  • search_pulse_job: batch user state check via single $in query
    (was: N individual get_user calls per pulse tick)
  • Stale card auto-cleanup
  • Startup notification with graceful error handling
"""

import logging

from telegram import BotCommand
from telegram.error import BadRequest
from telegram.ext import Application, ContextTypes

from database import Database
from handlers.callbacks import _search_screen
from services.matcher import Matcher, STATE_SEARCHING

logger = logging.getLogger(__name__)


async def setup_bot_commands(application: Application) -> None:
    await application.bot.set_my_commands(
        [
            BotCommand("start", "Open AnoyBot"),
            BotCommand("menu", "Main menu"),
            BotCommand("stop", "End chat or cancel search"),
            BotCommand("report", "Report abuse"),
            BotCommand("panel", "Admin / Owner panel"),
        ]
    )


async def notify_startup(application: Application) -> None:
    config = application.bot_data["config"]
    stats_cache = application.bot_data["stats_cache"]
    db: Database = application.bot_data["db"]
    stats = await stats_cache.get(db.get_stats)
    me = await application.bot.get_me()
    try:
        await application.bot.send_message(
            config.log_channel_id,
            f"🟢 <b>{config.brand_name} Online</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"🤖 @{me.username}\n"
            f"👥 Users: {stats['users']}\n"
            f"🔍 Searching: {stats['searching']}\n"
            f"🤝 Sessions: {stats['sessions']}\n"
            f"💬 Messages: {stats['messages']}",
            parse_mode="HTML",
        )
    except Exception as exc:
        logger.warning("startup notify failed: %s", exc)


async def search_pulse_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Animate search screens for waiting users.

    Optimization: batch-fetch user states in one $in query instead
    of N individual get_user() calls.
    """
    app = context.application
    db: Database = app.bot_data["db"]
    matcher: Matcher = app.bot_data["matcher"]
    stats_cache = app.bot_data["stats_cache"]
    cards: dict = app.bot_data.get("search_cards", {})
    if not cards:
        return

    app.bot_data["pulse_idx"] = app.bot_data.get("pulse_idx", 0) + 1
    stats = await stats_cache.get(db.get_stats)
    text = await _search_screen(context, matcher, stats)

    from keyboards.buttons import main_menu_keyboard

    # Batch fetch all user states in one query
    user_ids = list(cards.keys())
    user_states = await db.get_users_by_ids(user_ids)

    stale: list[int] = []
    for uid in user_ids:
        record = user_states.get(uid)
        if not record or record.get("state") != STATE_SEARCHING:
            stale.append(uid)
            continue

        chat_id, msg_id = cards[uid]
        try:
            await app.bot.edit_message_text(
                text,
                chat_id=chat_id,
                message_id=msg_id,
                parse_mode="HTML",
                reply_markup=main_menu_keyboard(is_searching=True),
            )
        except BadRequest as exc:
            msg = str(exc).lower()
            if "message is not modified" in msg:
                continue
            stale.append(uid)
        except Exception as exc:
            logger.debug("pulse edit %s: %s", uid, exc)

    for uid in stale:
        cards.pop(uid, None)
