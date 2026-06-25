"""Handler for /start and /menu — one status card, no clutter."""

from telegram import Update
from telegram.ext import ContextTypes

from config import Config
from database import Database
from keyboards.buttons import gender_keyboard, looking_for_keyboard, rules_keyboard
from services.logger import log_to_channel_bg
from services.matcher import Matcher
from utils.helpers import home_screen, is_banned
from utils.status_card import update_status_card
from utils.texts import BANNED, SETUP_GENDER, SETUP_LOOKING, WELCOME


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message:
        return

    db: Database = context.bot_data["db"]
    config: Config = context.bot_data["config"]
    matcher: Matcher = context.bot_data["matcher"]
    user = update.effective_user

    await db.upsert_user(
        user.id, user.username, user.first_name, user.last_name, force=True
    )

    if await is_banned(db, user.id):
        await update.message.reply_text(BANNED, parse_mode="HTML")
        return

    record = await db.get_user(user.id, fresh=True)

    log_to_channel_bg(
        context,
        config.log_channel_id,
        db,
        event="🟢 Bot Start",
        user=user,
        persist_message=False,
    )

    if not record or not record.get("accepted_rules"):
        await update_status_card(
            context,
            user.id,
            WELCOME.format(brand=config.brand_name),
            reply_markup=rules_keyboard(),
        )
        return

    if not record.get("gender"):
        await update_status_card(
            context, user.id, SETUP_GENDER, reply_markup=gender_keyboard()
        )
        return

    if not record.get("looking_for"):
        await update_status_card(
            context, user.id, SETUP_LOOKING, reply_markup=looking_for_keyboard()
        )
        return

    text, keyboard = await home_screen(db, matcher, user.id, brand=config.brand_name)
    await update_status_card(context, user.id, text, reply_markup=keyboard)


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
    await update_status_card(context, user.id, text, reply_markup=keyboard)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message:
        return
    from utils.texts import HELP
    from keyboards.buttons import main_menu_keyboard

    await update_status_card(
        context,
        update.effective_user.id,
        HELP,
        reply_markup=main_menu_keyboard(),
    )
