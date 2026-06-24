import asyncio
import logging

from telegram import Update
from telegram.ext import ContextTypes

from config import Config
from database import Database
from keyboards.buttons import main_menu_keyboard
from services.logger import log_to_channel
from services.matcher import STATE_CHATTING
from handlers.session import end_chat
from utils.helpers import is_banned, menu_for_user
from utils.ratelimit import RateLimiter
from utils.texts import BANNED, NOT_IN_CHAT, RATE_LIMITED, REPORT_SENT

logger = logging.getLogger(__name__)


async def _persist_message_log(
    db: Database,
    *,
    session_id: str,
    sender_id: int,
    receiver_id: int,
    message_type: str,
    content: str,
) -> None:
    try:
        await db.log_message(
            session_id=session_id,
            sender_id=sender_id,
            receiver_id=receiver_id,
            message_type=message_type,
            content_preview=content,
        )
    except Exception as exc:
        logger.debug("async log_message failed: %s", exc)


async def relay_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message:
        return

    user = update.effective_user
    db: Database = context.bot_data["db"]
    config: Config = context.bot_data["config"]
    limiter: RateLimiter = context.bot_data["rate_limiter"]

    if await is_banned(db, user.id):
        await update.message.reply_text(BANNED, parse_mode="HTML")
        return

    record = await db.get_user(user.id)
    if not record or record.get("state") != STATE_CHATTING:
        await update.message.reply_text(
            NOT_IN_CHAT,
            parse_mode="HTML",
            reply_markup=await menu_for_user(db, user.id),
        )
        return

    if not await limiter.allow(user.id):
        await update.message.reply_text(RATE_LIMITED, parse_mode="HTML")
        return

    partner_id = record.get("partner_id")
    session_id = record.get("session_id")
    if not partner_id:
        await update.message.reply_text(NOT_IN_CHAT, reply_markup=main_menu_keyboard())
        return

    msg = update.message
    content = msg.text or msg.caption or f"[{msg.content_type}]"

    if len(content) > config.max_message_length:
        await update.message.reply_text(
            f"⚠️ Message too long (max {config.max_message_length} chars)."
        )
        return

    try:
        await msg.copy(chat_id=partner_id)
    except Exception:
        await update.message.reply_text("❌ Partner unavailable.")
        await end_chat(context, user.id, reason="partner_left")
        return

    if session_id and config.log_channel_id:
        asyncio.create_task(
            log_to_channel(
                context,
                config.log_channel_id,
                db,
                event="💬 Message",
                user=user,
                partner=None,
                session_id=session_id,
                message_type=msg.content_type,
                content=content,
                extra=f"Partner ID: {partner_id}",
                persist_message=False,
            )
        )
        asyncio.create_task(
            _persist_message_log(
                db,
                session_id=session_id,
                sender_id=user.id,
                receiver_id=partner_id,
                message_type=msg.content_type,
                content=content,
            )
        )


async def report_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message:
        return

    user = update.effective_user
    db: Database = context.bot_data["db"]
    config: Config = context.bot_data["config"]

    record = await db.get_user(user.id)
    partner_id = record.get("partner_id") if record else None
    session_id = record.get("session_id") if record else None
    reason = " ".join(context.args) if context.args else "No details provided"

    if partner_id:
        try:
            await db.add_report(user.id, partner_id, session_id, reason)
            count = await db.increment_reports(partner_id)
            if count >= config.auto_ban_reports:
                await db.ban_user(partner_id, f"Auto-ban after {count} reports")
        except Exception:
            pass

    await log_to_channel(
        context,
        config.log_channel_id,
        db,
        event="🚨 ABUSE REPORT",
        user=user,
        partner=None,
        session_id=session_id,
        extra=f"Partner: {partner_id} | Reason: {reason}" if partner_id else f"Reason: {reason}",
        persist_message=False,
    )

    await update.message.reply_text(
        REPORT_SENT,
        parse_mode="HTML",
        reply_markup=main_menu_keyboard(is_chatting=bool(partner_id)),
    )
