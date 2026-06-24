"""Handler for /start and /menu commands.

Speed: fire-and-forget logging, no blocking on channel log.
"""

from telegram import Update
from telegram.ext import ContextTypes

from config import Config
from database import Database
from keyboards.buttons import gender_keyboard, looking_for_keyboard, rules_keyboard
from services.logger import log_to_channel_bg
from services.matcher import Matcher
from utils.helpers import home_screen, is_banned
from utils.texts import BANNED, SETUP_GENDER, SETUP_LOOKING, WELCOME


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message:
        return

    db: Database = context.bot_data["db"]
    config: Config = context.bot_data["config"]
    matcher: Matcher = context.bot_data["matcher"]
    user = update.effective_user

    await db.upsert_user(user.id, user.username, user.first_name, user.last_name)

    if await is_banned(db, user.id):
        await update.message.reply_text(BANNED, parse_mode="HTML")
        return

    record = await db.get_user(user.id, fresh=True)

    # Fire-and-forget — don't block the /start response
    log_to_channel_bg(
        context,
        config.log_channel_id,
        db,
        event="🟢 Bot Start",
        user=user,
        persist_message=False,
    )

    if not record or not record.get("accepted_rules"):
        await update.message.reply_text(
            WELCOME.format(brand=config.brand_name),
            parse_mode="HTML",
            reply_markup=rules_keyboard(),
        )
        return

    if not record.get("gender"):
        await update.message.reply_text(
            SETUP_GENDER, parse_mode="HTML", reply_markup=gender_keyboard()
        )
        return

    if not record.get("looking_for"):
        await update.message.reply_text(
            SETUP_LOOKING, parse_mode="HTML", reply_markup=looking_for_keyboard()
        )
        return

    text, keyboard = await home_screen(db, matcher, user.id, brand=config.brand_name)
    await update.message.reply_text(text, parse_mode="HTML", reply_markup=keyboard)


async def menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message:
        return

    db: Database = context.bot_data["db"]
    config: Config = context.bot_data["config"]
    matcher: Matcher = context.bot_data["matcher"]
    user = update.effective_user

    if await is_banned(db, user.id):
        await update.message.reply_text(BANNED, parse_mode="HTML")
        return

    record = await db.get_user(user.id, fresh=True)
    if not record or not record.get("gender") or not record.get("looking_for"):
        await start_command(update, context)
        return

    text, keyboard = await home_screen(db, matcher, user.id, brand=config.brand_name)
    await update.message.reply_text(text, parse_mode="HTML", reply_markup=keyboard)
