"""Message relay — clean chat, no prefixes, smart spam filter."""

import asyncio
import logging
import time

from telegram import Update
from telegram.ext import ContextTypes

from config import Config
from database import Database
from handlers.panel import handle_panel_input
from handlers.session import end_chat
from services.logger import log_to_channel_bg
from services.message_buffer import MessageLogEntry
from services.relay import copy_to_partner, forward_typing
from services.session_registry import SessionRegistry
from utils.helpers import get_message_type
from utils.ratelimit import RateLimiter
from utils.spam_filter import contains_spam
from utils.texts import BANNED, RATE_LIMITED, REPORT_SENT, SPAM_BLOCKED

logger = logging.getLogger(__name__)
_spam_warn_at: dict[int, float] = {}
_SPAM_WARN_COOLDOWN = 25.0


def _task_error_cb(task: asyncio.Task) -> None:
    if task.cancelled():
        return
    exc = task.exception()
    if exc:
        logger.debug("background task failed: %s", exc)


async def _warn_spam(update: Update) -> None:
    """One short warning — delete the spam message to keep chat clean."""
    user_id = update.effective_user.id
    now = time.monotonic()
    if now - _spam_warn_at.get(user_id, 0.0) < _SPAM_WARN_COOLDOWN:
        return
    _spam_warn_at[user_id] = now
    try:
        await update.message.delete()
    except Exception:
        pass
    try:
        warn = await update.message.reply_text(SPAM_BLOCKED)
        asyncio.create_task(_delete_later(warn, 6.0))
    except Exception:
        pass


async def _delete_later(message, delay: float) -> None:
    await asyncio.sleep(delay)
    try:
        await message.delete()
    except Exception:
        pass


async def relay_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message:
        return

    if context.user_data.get("panel_await"):
        if await handle_panel_input(update, context):
            return

    user = update.effective_user
    db: Database = context.bot_data["db"]
    config: Config = context.bot_data["config"]
    limiter: RateLimiter = context.bot_data["rate_limiter"]
    registry: SessionRegistry = context.bot_data["session_registry"]

    active = registry.get(user.id)
    if active:
        partner_id = active.partner_id
        session_id = active.session_id
    else:
        record = await db.get_user(user.id)
        if not record:
            return
        if record.get("is_banned"):
            return
        state = record.get("state")
        partner_id = record.get("partner_id")
        session_id = record.get("session_id")
        if state != "chatting" or not partner_id or not session_id:
            return
        registry.connect(user.id, partner_id, session_id)

    if not limiter.allow(user.id):
        return

    msg = update.message
    msg_type = get_message_type(msg)
    content = msg.text or msg.caption or ""

    if msg_type == "text" or msg.caption:
        if contains_spam(content):
            await _warn_spam(update)
            return

    if content and len(content) > config.max_message_length:
        return

    typing_task = asyncio.create_task(
        forward_typing(
            context,
            partner_id,
            msg,
            cooldown_seconds=config.typing_cooldown_seconds,
        )
    )
    typing_task.add_done_callback(_task_error_cb)

    ok = await copy_to_partner(context, msg, partner_id, sender_id=user.id)
    if not ok:
        logger.warning("relay failed %s -> %s", user.id, partner_id)
        await end_chat(context, user.id, reason="partner_left")
        return

    preview = content or f"[{msg_type}]"
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
            content=preview,
            extra=f"Partner ID: {partner_id}",
            persist_message=False,
        )

    if session_id:
        buffer = context.bot_data.get("message_buffer")
        entry = MessageLogEntry(
            session_id=session_id,
            sender_id=user.id,
            receiver_id=partner_id,
            message_type=msg_type,
            content_preview=preview[:500],
        )
        if buffer:
            task = asyncio.create_task(buffer.enqueue(entry))
            task.add_done_callback(_task_error_cb)
        else:
            task = asyncio.create_task(
                db.log_message(
                    session_id=session_id,
                    sender_id=user.id,
                    receiver_id=partner_id,
                    message_type=msg_type,
                    content_preview=preview[:500],
                )
            )
            task.add_done_callback(_task_error_cb)


async def link_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Safely share Telegram profile with chat partner — no spam in chat."""
    if not update.effective_user or not update.message:
        return

    user = update.effective_user
    registry: SessionRegistry = context.bot_data["session_registry"]
    active = registry.get(user.id)

    if not active:
        return

    if not user.username:
        warn = await update.message.reply_text(
            "Set a @username in Telegram settings first."
        )
        asyncio.create_task(_delete_later(warn, 5.0))
        return

    link = f"https://t.me/{user.username}"
    name = user.first_name or user.username
    from utils.texts import LINK_RECEIVED

    try:
        await context.bot.send_message(
            active.partner_id,
            LINK_RECEIVED.format(link=f'<a href="{link}">{name}</a>'),
            parse_mode="HTML",
            disable_web_page_preview=True,
        )
    except Exception:
        pass

    try:
        await update.message.delete()
    except Exception:
        pass
    confirm = await update.message.reply_text("Profile shared ✓")
    asyncio.create_task(_delete_later(confirm, 4.0))


async def report_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message:
        return

    user = update.effective_user
    db: Database = context.bot_data["db"]
    config: Config = context.bot_data["config"]
    registry: SessionRegistry = context.bot_data["session_registry"]

    active = registry.get(user.id)
    if active:
        partner_id = active.partner_id
        session_id = active.session_id
    else:
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
                registry.disconnect(partner_id)
        except Exception:
            pass

    from utils.status_card import update_status_card
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

    await update_status_card(
        context,
        user.id,
        REPORT_SENT,
        reply_markup=main_menu_keyboard(is_chatting=bool(partner_id)),
    )
