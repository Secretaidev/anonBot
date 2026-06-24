import logging

from telegram import BotCommand
from telegram.error import BadRequest
from telegram.ext import Application, ContextTypes

from database import Database
from handlers.callbacks import _search_screen
from services.matcher import Matcher
from utils.texts import SEARCHING, PULSE_FRAMES

logger = logging.getLogger(__name__)


async def setup_bot_commands(application: Application) -> None:
    await application.bot.set_my_commands(
        [
            BotCommand("start", "Open AnoyBot"),
            BotCommand("menu", "Main menu"),
            BotCommand("stop", "End chat or cancel search"),
            BotCommand("report", "Report abuse"),
        ]
    )


async def notify_startup(application: Application) -> None:
    config = application.bot_data["config"]
    db: Database = application.bot_data["db"]
    stats = await db.get_stats()
    me = await application.bot.get_me()
    try:
        await application.bot.send_message(
            config.log_channel_id,
            f"🟢 <b>{config.brand_name} Online</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"🤖 @{me.username}\n"
            f"👥 Users: {stats['users']}\n"
            f"🤝 Sessions: {stats['sessions']}\n"
            f"💬 Messages: {stats['messages']}",
            parse_mode="HTML",
        )
    except Exception as exc:
        logger.warning("startup notify failed: %s", exc)


async def search_pulse_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    app = context.application
    db: Database = app.bot_data["db"]
    matcher: Matcher = app.bot_data["matcher"]
    cards: dict = app.bot_data.get("search_cards", {})
    if not cards:
        return

    app.bot_data["pulse_idx"] = app.bot_data.get("pulse_idx", 0) + 1
    text = await _search_screen(context, matcher, db)

    from keyboards.buttons import main_menu_keyboard

    for uid, (chat_id, msg_id) in list(cards.items()):
        record = await db.get_user(uid)
        if not record or record.get("state") != "searching":
            cards.pop(uid, None)
            continue
        try:
            await app.bot.edit_message_text(
                text,
                chat_id=chat_id,
                message_id=msg_id,
                parse_mode="HTML",
                reply_markup=main_menu_keyboard(is_searching=True),
            )
        except BadRequest:
            cards.pop(uid, None)
        except Exception as exc:
            logger.debug("pulse edit %s: %s", uid, exc)
