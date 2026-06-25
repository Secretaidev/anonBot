"""Background jobs — search pulse animation, startup notify, bot commands.

Performance improvements:
  • search_pulse_job: batch user state check via single $in query
  • No stats fetch during pulse (was wasted MongoDB aggregation every tick)
  • Parallel message edits with bounded concurrency
  • Stale card auto-cleanup
"""

import asyncio
import logging

from telegram import BotCommand
from telegram.error import BadRequest
from telegram.ext import Application, ContextTypes

from database import Database
from handlers.callbacks import _search_screen
from services.matcher import Matcher, STATE_SEARCHING

logger = logging.getLogger(__name__)
_PULSE_CONCURRENCY = 12


async def setup_bot_commands(application: Application) -> None:
    await application.bot.set_my_commands(
        [
            BotCommand("start", "Open AnoyBot"),
            BotCommand("menu", "Main menu"),
            BotCommand("help", "How it works"),
            BotCommand("stop", "End chat or cancel search"),
            BotCommand("report", "Report abuse"),
            BotCommand("link", "Share your profile safely"),
            BotCommand("panel", "Admin / Owner panel"),
        ]
    )


async def notify_startup(application: Application) -> None:
    config = application.bot_data["config"]
    stats_cache = application.bot_data["stats_cache"]
    db: Database = application.bot_data["db"]
    registry = application.bot_data.get("session_registry")
    stats = await stats_cache.get(db.get_stats)
    me = await application.bot.get_me()
    active_mem = registry.size() // 2 if registry else 0
    try:
        await application.bot.send_message(
            config.log_channel_id,
            f"🟢 <b>{config.brand_name} Online</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"🤖 @{me.username}\n"
            f"👥 Users: {stats['users']}\n"
            f"🔍 Searching: {stats['searching']}\n"
            f"💬 In chat: {stats['chatting']}\n"
            f"🤝 Sessions: {stats['sessions']}\n"
            f"💬 Messages: {stats['messages']}\n"
            f"⚡ Memory sessions: {active_mem}",
            parse_mode="HTML",
        )
    except Exception as exc:
        logger.warning("startup notify failed: %s", exc)


async def search_pulse_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Animate search screens for waiting users — minimal server load."""
    app = context.application
    db: Database = app.bot_data["db"]
    cards: dict = app.bot_data.get("status_cards", {})
    if not cards:
        return

    app.bot_data["pulse_idx"] = app.bot_data.get("pulse_idx", 0) + 1
    text = await _search_screen(context)

    from keyboards.buttons import main_menu_keyboard

    keyboard = main_menu_keyboard(is_searching=True)
    user_ids = list(cards.keys())
    user_states = await db.get_users_by_ids(user_ids)

    stale: list[int] = []
    sem = asyncio.Semaphore(_PULSE_CONCURRENCY)

    async def _edit_one(uid: int) -> None:
        record = user_states.get(uid)
        if not record or record.get("state") != STATE_SEARCHING:
            stale.append(uid)
            return
        chat_id, msg_id = cards[uid]
        async with sem:
            try:
                await app.bot.edit_message_text(
                    text,
                    chat_id=chat_id,
                    message_id=msg_id,
                    parse_mode="HTML",
                    reply_markup=keyboard,
                )
            except BadRequest as exc:
                msg = str(exc).lower()
                if "message is not modified" in msg:
                    return
                stale.append(uid)
            except Exception as exc:
                logger.debug("pulse edit %s: %s", uid, exc)

    await asyncio.gather(*(_edit_one(uid) for uid in user_ids))

    for uid in stale:
        cards.pop(uid, None)
