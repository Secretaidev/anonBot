"""Message relay — fastest possible hot path.

Hot-path optimizations:
  • Single get_user() for ban+state+partner check (was 3 separate)
  • Zero-await rate limiter
  • Fire-and-forget for ALL logging (channel + DB)
  • Panel interception only checked if panel_await is set
"""

import asyncio
import logging

from telegram import Update
from telegram.ext import ContextTypes

from config import Config
from database import Database
from handlers.panel import handle_panel_input
from handlers.session import end_chat
from services.logger import log_to_channel_bg
from services.relay import copy_to_partner, forward_typing
from utils.helpers import get_message_type
from utils.ratelimit import RateLimiter
from utils.texts import BANNED, NOT_IN_CHAT, RATE_LIMITED, REPORT_SENT

logger = logging.getLogger(__name__)


def _task_error_cb(task: asyncio.Task) -> None:
    if task.cancelled():
        return
    exc = task.exception()
    if exc:
        logger.debug("background task failed: %s", exc)


async def relay_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message:
        return

    # ── Panel input — only check if a panel flow is pending ──
    if context.user_data.get("panel_await"):
        if await handle_panel_input(update, context):
            return

    user = update.effective_user
    db: Database = context.bot_data["db"]
    config: Config = context.bot_data["config"]
    limiter: RateLimiter = context.bot_data["rate_limiter"]

    # ── Single DB read for ban + state + partner (was 3 reads) ──
    record = await db.get_user(user.id)
    if not record:
        return

    if record.get("is_banned"):
        await update.message.reply_text(BANNED, parse_mode="HTML")
        return

    state = record.get("state")
    partner_id = record.get("partner_id")
    session_id = record.get("session_id")

    if state != "chatting" or not partner_id:
        await update.message.reply_text(NOT_IN_CHAT, parse_mode="HTML")
        return

    # Synchronous rate limiter — zero await
    if not limiter.allow(user.id):
        await update.message.reply_text(RATE_LIMITED, parse_mode="HTML")
        return

    msg = update.message
    msg_type = get_message_type(msg)
    content = msg.text or msg.caption or f"[{msg_type}]"

    if len(content) > config.max_message_length:
        await update.message.reply_text(
            f"⚠️ Message too long (max {config.max_message_length} chars)."
        )
        return

    # ── Typing indicator + Relay (concurrent for zero latency) ──
    typing_task = asyncio.create_task(forward_typing(context, partner_id, msg))
    typing_task.add_done_callback(_task_error_cb)

    ok = await copy_to_partner(context, msg, partner_id, sender_id=user.id)
    if not ok:
        logger.warning("relay failed %s -> %s", user.id, partner_id)
        await update.message.reply_text("❌ Partner unavailable.")
        await end_chat(context, user.id, reason="partner_left")
        return

    # ── Fire-and-forget logging — ZERO blocking ──
    if session_id and config.log_channel_id and config.log_chat_messages:
        log_to_channel_bg(
            context,
            config.log_channel_id,
            db,
            event="💬 Message",
            user=user,
            partner=None,
            session_id=session_id,
            message_type=msg_type,
            content=content,
            extra=f"Partner ID: {partner_id}",
            persist_message=False,
        )

    if session_id:
        task = asyncio.create_task(
            db.log_message(
                session_id=session_id,
                sender_id=user.id,
                receiver_id=partner_id,
                message_type=msg_type,
                content_preview=content[:500],
            )
        )
        task.add_done_callback(_task_error_cb)


async def report_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message:
        return

    user = update.effective_user
    db: Database = context.bot_data["db"]
    config: Config = context.bot_data["config"]

    record = await db.get_user(user.id, fresh=True)
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

    from services.logger import log_to_channel
    from keyboards.buttons import main_menu_keyboard

    log_to_channel_bg(
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
