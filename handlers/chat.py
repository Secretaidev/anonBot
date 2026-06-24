"""Message relay handler — routes user messages to their chat partner.

Improvements over original:
  • Uses services/relay.py (copy_to_partner) with 3-retry + RetryAfter backoff
    (was: raw msg.copy() with no retry, no Forbidden handling)
  • Fire-and-forget tasks have proper error callbacks (no silent exception loss)
  • Conditional message logging via config.log_chat_messages
  • Rate limiter is now synchronous (no await overhead)
"""

import asyncio
import logging

from telegram import Update
from telegram.ext import ContextTypes

from config import Config
from database import Database
from handlers.session import end_chat
from services.logger import log_to_channel_bg
from services.relay import copy_to_partner
from utils.helpers import get_message_type, home_screen, is_banned, is_valid_chat_session
from utils.ratelimit import RateLimiter
from utils.texts import BANNED, RATE_LIMITED, REPORT_SENT

logger = logging.getLogger(__name__)


def _task_error_cb(task: asyncio.Task) -> None:
    """Log exceptions from fire-and-forget tasks."""
    if task.cancelled():
        return
    exc = task.exception()
    if exc:
        logger.debug("background task failed: %s", exc)


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

    # Cached read on hot path — no fresh DB hit per message
    if not await is_valid_chat_session(db, user.id):
        matcher = context.bot_data["matcher"]
        stats_cache = context.application.bot_data.get("stats_cache")
        stats = None
        if stats_cache:
            stats = await stats_cache.get(db.get_stats)
        text, keyboard = await home_screen(
            db, matcher, user.id, brand=config.brand_name, stats=stats
        )
        await update.message.reply_text(text, parse_mode="HTML", reply_markup=keyboard)
        return

    # Synchronous rate limiter — zero await overhead
    if not limiter.allow(user.id):
        await update.message.reply_text(RATE_LIMITED, parse_mode="HTML")
        return

    record = await db.get_user(user.id)
    partner_id = record.get("partner_id") if record else None
    session_id = record.get("session_id") if record else None
    if not partner_id:
        return

    msg = update.message
    msg_type = get_message_type(msg)
    content = msg.text or msg.caption or f"[{msg_type}]"

    if len(content) > config.max_message_length:
        await update.message.reply_text(
            f"⚠️ Message too long (max {config.max_message_length} chars)."
        )
        return

    # ── Use relay service with proper retry/backoff ──
    ok = await copy_to_partner(context, msg, partner_id, sender_id=user.id)
    if not ok:
        logger.warning("relay failed %s -> %s", user.id, partner_id)
        await update.message.reply_text("❌ Partner unavailable.")
        await end_chat(context, user.id, reason="partner_left")
        return

    # ── Fire-and-forget logging (with error callbacks) ──
    if session_id and config.log_channel_id:
        if config.log_chat_messages:
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

        task = asyncio.create_task(
            _persist_message_log(
                db,
                session_id=session_id,
                sender_id=user.id,
                receiver_id=partner_id,
                message_type=msg_type,
                content=content,
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

    from keyboards.buttons import main_menu_keyboard
    from services.logger import log_to_channel

    await update.message.reply_text(
        REPORT_SENT,
        parse_mode="HTML",
        reply_markup=main_menu_keyboard(is_chatting=bool(partner_id)),
    )
