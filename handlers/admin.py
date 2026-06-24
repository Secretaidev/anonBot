"""Admin commands — /stats, /user, /ban, /unban, /broadcast.

Now uses granular permission system:
  • Owner (ADMIN_IDS) → all commands
  • DB Admin → permission-gated
"""

import asyncio
from html import escape

from telegram import Update
from telegram.ext import ContextTypes

from database import Database
from services.logger import log_to_channel
from utils.helpers import safe_send


async def _has_perm(context: ContextTypes.DEFAULT_TYPE, user_id: int, perm: str) -> bool:
    """Check if user is owner or has specific DB admin permission."""
    config = context.bot_data["config"]
    if user_id in config.admin_ids:
        return True
    db: Database = context.bot_data["db"]
    return await db.has_permission(user_id, perm, config.admin_ids)


async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message:
        return
    if not await _has_perm(context, update.effective_user.id, "stats"):
        return

    db: Database = context.bot_data["db"]
    matcher = context.bot_data["matcher"]
    stats = await db.get_stats()
    queue = await matcher.queue_size()

    await update.message.reply_text(
        f"📊 <b>Admin Dashboard</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"👥 Users: <b>{stats['users']}</b>\n"
        f"🔍 Searching: <b>{stats['searching']}</b> (queue: {queue})\n"
        f"💬 In chat: <b>{stats['chatting']}</b>\n"
        f"🤝 Sessions: <b>{stats['sessions']}</b>\n"
        f"💬 Messages logged: <b>{stats['messages']}</b>\n"
        f"🚫 Banned: <b>{stats['banned']}</b>",
        parse_mode="HTML",
    )


async def admin_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message:
        return
    if not await _has_perm(context, update.effective_user.id, "user_lookup"):
        return

    if not context.args:
        await update.message.reply_text("Usage: /user <user_id>")
        return

    try:
        target_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Invalid user ID.")
        return

    db: Database = context.bot_data["db"]
    record = await db.get_user(target_id)
    if not record:
        await update.message.reply_text("User not found in database.")
        return

    avg = "—"
    if record.get("rating_count"):
        avg = f"{record['rating_sum'] / record['rating_count']:.1f} ⭐"

    await update.message.reply_text(
        f"👤 <b>User Profile</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"ID: <code>{target_id}</code>\n"
        f"Name: {escape(record.get('first_name') or '—')}\n"
        f"Username: @{escape(record.get('username') or '—')}\n"
        f"Gender: {escape(record.get('gender') or '—')}\n"
        f"Looking: {escape(record.get('looking_for') or '—')}\n"
        f"State: {escape(record.get('state') or 'idle')}\n"
        f"Sessions: {record.get('total_sessions', 0)}\n"
        f"Messages: {record.get('total_messages', 0)}\n"
        f"Reports: {record.get('reports_received', 0)}\n"
        f"Rating: {avg}\n"
        f"Banned: {'Yes — ' + escape(record.get('ban_reason') or '') if record.get('is_banned') else 'No'}",
        parse_mode="HTML",
    )


async def admin_ban(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message:
        return
    if not await _has_perm(context, update.effective_user.id, "ban"):
        return

    if not context.args:
        await update.message.reply_text("Usage: /ban <user_id> [reason]")
        return

    try:
        target_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Invalid user ID.")
        return

    reason = " ".join(context.args[1:]) or "Banned by admin"
    db: Database = context.bot_data["db"]
    matcher = context.bot_data["matcher"]

    await db.ban_user(target_id, reason)
    await matcher.leave(target_id)

    await safe_send(context, target_id, f"🚫 You have been banned.\nReason: {reason}")
    await update.message.reply_text(f"✅ Banned {target_id}")

    await log_to_channel(
        context,
        context.bot_data["config"].log_channel_id,
        db,
        event="🔨 Admin Ban",
        user=update.effective_user,
        extra=f"Target: {target_id} | {reason}",
        persist_message=False,
    )


async def admin_unban(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message:
        return
    if not await _has_perm(context, update.effective_user.id, "unban"):
        return

    if not context.args:
        await update.message.reply_text("Usage: /unban <user_id>")
        return

    try:
        target_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Invalid user ID.")
        return

    db: Database = context.bot_data["db"]
    await db.unban_user(target_id)
    await update.message.reply_text(f"✅ Unbanned {target_id}")


async def admin_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Broadcast to all non-banned users with concurrent sends + progress reports."""
    if not update.effective_user or not update.message:
        return
    if not await _has_perm(context, update.effective_user.id, "broadcast"):
        return

    if not context.args:
        await update.message.reply_text("Usage: /broadcast <message>")
        return

    text = " ".join(context.args)
    db: Database = context.bot_data["db"]
    config = context.bot_data["config"]

    user_ids = await db.get_broadcast_user_ids()
    total = len(user_ids)

    if total == 0:
        await update.message.reply_text("No users to broadcast to.")
        return

    progress_msg = await update.message.reply_text(
        f"📢 Broadcasting to {total} users…"
    )

    sem = asyncio.Semaphore(config.broadcast_concurrency)
    sent = 0
    failed = 0
    broadcast_text = f"📢 <b>Announcement</b>\n\n{text}"

    async def _send_one(uid: int) -> bool:
        async with sem:
            return await safe_send(context, uid, broadcast_text)

    batch_size = max(total // 5, 50)
    for i in range(0, total, batch_size):
        batch = user_ids[i:i + batch_size]
        results = await asyncio.gather(*[_send_one(uid) for uid in batch])
        sent += sum(1 for r in results if r)
        failed += sum(1 for r in results if not r)

        try:
            pct = int((i + len(batch)) / total * 100)
            await progress_msg.edit_text(
                f"📢 Broadcasting… {pct}% ({sent} sent, {failed} failed)"
            )
        except Exception:
            pass

    try:
        await progress_msg.edit_text(
            f"📢 Broadcast complete!\n\n✅ Sent: {sent} | ❌ Failed: {failed}"
        )
    except Exception:
        await update.message.reply_text(f"📢 Sent: {sent} | Failed: {failed}")
