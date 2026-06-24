"""Owner & Admin Panel — complete in-bot management interface.

Architecture:
  • Owner (ADMIN_IDS in .env) → full access, can manage admins
  • Admin (added via panel) → permission-gated access
  • Text input for user ID/broadcast via user_data["panel_await"]
  • Permission editor with inline toggle buttons
"""

import asyncio
import logging
from html import escape

from telegram import Update
from telegram.ext import ContextTypes

from config import Config
from database import Database
from keyboards.buttons import (
    CB_PANEL,
    PA_MAIN, PA_STATS, PA_USERS, PA_USER_LOOKUP, PA_USER_BAN, PA_USER_UNBAN,
    PA_BROADCAST, PA_ADMINS, PA_ADMIN_ADD, PA_ADMIN_RM, PA_ADMIN_RM_YES,
    PA_ADMIN_EDIT, PA_PERM_TOGGLE, PA_SAVE_ADMIN, PA_REPORTS, PA_QUEUE,
    PA_FORCE_DC, PA_HOME,
    ALL_PERMISSIONS, PERM_LABELS,
    admin_list_keyboard, admin_panel_keyboard, confirm_remove_admin_keyboard,
    main_menu_keyboard, owner_panel_keyboard, panel_back_keyboard,
    panel_input_cancel_keyboard, permission_editor_keyboard,
    user_management_keyboard,
)
from services.matcher import Matcher, STATE_IDLE
from utils.helpers import home_screen, safe_edit, safe_send

logger = logging.getLogger(__name__)


# ─── Panel text strings ───

def _panel_header(name: str, is_owner: bool) -> str:
    role = "👑 Owner" if is_owner else "🛡 Admin"
    return (
        f"{'🔐' if is_owner else '🛡'} <b>{role} Panel</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Welcome, <b>{escape(name)}</b>."
    )


def _stats_text(stats: dict, queue: int, pairs: int) -> str:
    return (
        "📊 <b>Live Dashboard</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        f"👥 Total users: <b>{stats.get('users', 0)}</b>\n"
        f"🔍 Searching: <b>{stats.get('searching', 0)}</b>\n"
        f"💬 In chat: <b>{stats.get('chatting', 0)}</b>\n"
        f"📡 Queue: <b>{queue}</b>\n"
        f"🤝 Active pairs: <b>{pairs}</b>\n"
        f"🤝 Total sessions: <b>{stats.get('sessions', 0)}</b>\n"
        f"💬 Messages logged: <b>{stats.get('messages', 0)}</b>\n"
        f"🚫 Banned: <b>{stats.get('banned', 0)}</b>"
    )


def _user_profile_text(record: dict) -> str:
    avg = "—"
    if record.get("rating_count"):
        avg = f"{record['rating_sum'] / record['rating_count']:.1f} ⭐"

    banned_text = "No"
    if record.get("is_banned"):
        reason = escape(record.get("ban_reason") or "No reason")
        banned_text = f"🚫 Yes — {reason}"

    return (
        "👤 <b>User Profile</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🆔 ID: <code>{record.get('user_id', '?')}</code>\n"
        f"📛 Name: {escape(record.get('first_name') or '—')}\n"
        f"🏷 Username: @{escape(record.get('username') or '—')}\n"
        f"🎭 Gender: {escape(record.get('gender') or '—')}\n"
        f"💫 Looking for: {escape(record.get('looking_for') or '—')}\n"
        f"📍 State: {escape(record.get('state') or 'idle')}\n"
        f"🤝 Sessions: {record.get('total_sessions', 0)}\n"
        f"💬 Messages: {record.get('total_messages', 0)}\n"
        f"🚨 Reports: {record.get('reports_received', 0)}\n"
        f"⭐ Rating: {avg}\n"
        f"🚫 Banned: {banned_text}"
    )


# ─── Panel command ───

async def panel_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /panel command — show owner or admin panel."""
    if not update.effective_user or not update.message:
        return

    user = update.effective_user
    db: Database = context.bot_data["db"]
    config: Config = context.bot_data["config"]

    is_owner = user.id in config.admin_ids

    if not is_owner:
        admin = await db.get_admin(user.id)
        if not admin:
            return  # not staff — silently ignore
        perms = admin.get("permissions", [])
        text = _panel_header(user.first_name or "Admin", False)
        perm_display = "  ".join(
            f"{'✅' if p in perms else '❌'} {l}" for p, l in ALL_PERMISSIONS
        )
        text += f"\n\n{perm_display}"
        await update.message.reply_text(
            text, parse_mode="HTML",
            reply_markup=admin_panel_keyboard(perms),
        )
        return

    # Owner panel
    text = _panel_header(user.first_name or "Owner", True)
    text += "\n\n👑 Full access granted. All tools available."
    await update.message.reply_text(
        text, parse_mode="HTML",
        reply_markup=owner_panel_keyboard(),
    )


# ─── Panel callback handler ───

async def panel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle all p: callback data."""
    query = update.callback_query
    if not query or not query.data or not query.from_user:
        return

    await query.answer()
    data = query.data
    if not data.startswith(CB_PANEL):
        return

    action = data[len(CB_PANEL):]
    user = query.from_user
    db: Database = context.bot_data["db"]
    config: Config = context.bot_data["config"]
    matcher: Matcher = context.bot_data["matcher"]

    is_owner = user.id in config.admin_ids

    # Permission check
    if not is_owner:
        admin = await db.get_admin(user.id)
        if not admin:
            return
        perms = admin.get("permissions", [])
    else:
        perms = [p for p, _ in ALL_PERMISSIONS]  # owner has all

    # ── Main panel ──
    if action == PA_MAIN:
        if is_owner:
            text = _panel_header(user.first_name or "Owner", True)
            text += "\n\n👑 Full access granted. All tools available."
            await safe_edit(query, text, reply_markup=owner_panel_keyboard())
        else:
            text = _panel_header(user.first_name or "Admin", False)
            perm_display = "  ".join(
                f"{'✅' if p in perms else '❌'} {l}" for p, l in ALL_PERMISSIONS
            )
            text += f"\n\n{perm_display}"
            await safe_edit(query, text, reply_markup=admin_panel_keyboard(perms))
        # Clear any pending input state
        context.user_data.pop("panel_await", None)
        context.user_data.pop("panel_data", None)
        return

    # ── Home (back to bot) ──
    if action == PA_HOME:
        context.user_data.pop("panel_await", None)
        context.user_data.pop("panel_data", None)
        stats_cache = context.application.bot_data.get("stats_cache")
        stats = await stats_cache.get(db.get_stats) if stats_cache else None
        text, kb = await home_screen(db, matcher, user.id, brand=config.brand_name, stats=stats)
        await safe_edit(query, text, reply_markup=kb)
        return

    # ── Live Stats ──
    if action == PA_STATS:
        if "stats" not in perms:
            await query.answer("No permission.", show_alert=True)
            return
        stats = await db.get_stats()
        queue = await matcher.queue_size()
        pairs = len(await db.get_chatting_pairs())
        await safe_edit(
            query,
            _stats_text(stats, queue, pairs),
            reply_markup=panel_back_keyboard(),
        )
        return

    # ── User management sub-menu (owner only) ──
    if action == PA_USERS:
        if not is_owner:
            await query.answer("Owner only.", show_alert=True)
            return
        await safe_edit(
            query,
            "👥 <b>User Management</b>\n━━━━━━━━━━━━━━━━━━━━\n\nSelect an action:",
            reply_markup=user_management_keyboard(),
        )
        return

    # ── User Lookup ──
    if action == PA_USER_LOOKUP:
        if "user_lookup" not in perms:
            await query.answer("No permission.", show_alert=True)
            return
        context.user_data["panel_await"] = "lookup"
        await safe_edit(
            query,
            "👤 <b>User Lookup</b>\n━━━━━━━━━━━━━━━━━━━━\n\n"
            "Send the <b>User ID</b> to look up:",
            reply_markup=panel_input_cancel_keyboard(),
        )
        return

    # ── Ban User ──
    if action == PA_USER_BAN:
        if "ban" not in perms:
            await query.answer("No permission.", show_alert=True)
            return
        context.user_data["panel_await"] = "ban"
        await safe_edit(
            query,
            "🔨 <b>Ban User</b>\n━━━━━━━━━━━━━━━━━━━━\n\n"
            "Send the <b>User ID</b> to ban:",
            reply_markup=panel_input_cancel_keyboard(),
        )
        return

    # ── Unban User ──
    if action == PA_USER_UNBAN:
        if "unban" not in perms:
            await query.answer("No permission.", show_alert=True)
            return
        context.user_data["panel_await"] = "unban"
        await safe_edit(
            query,
            "🔓 <b>Unban User</b>\n━━━━━━━━━━━━━━━━━━━━\n\n"
            "Send the <b>User ID</b> to unban:",
            reply_markup=panel_input_cancel_keyboard(),
        )
        return

    # ── Broadcast ──
    if action == PA_BROADCAST:
        if "broadcast" not in perms:
            await query.answer("No permission.", show_alert=True)
            return
        context.user_data["panel_await"] = "broadcast"
        await safe_edit(
            query,
            "📢 <b>Broadcast</b>\n━━━━━━━━━━━━━━━━━━━━\n\n"
            "Type your broadcast message.\n"
            "It will be sent to <b>all non-banned users</b>.",
            reply_markup=panel_input_cancel_keyboard(),
        )
        return

    # ── Admin Management ──
    if action == PA_ADMINS:
        if not is_owner:
            await query.answer("Owner only.", show_alert=True)
            return
        admins = await db.list_admins()
        count = len([a for a in admins if a["user_id"] not in config.admin_ids])
        await safe_edit(
            query,
            f"👮 <b>Admin Management</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"📋 {count} admin(s) configured.\n"
            f"Tap an admin to edit permissions, or add a new one.",
            reply_markup=admin_list_keyboard(admins, config.admin_ids),
        )
        return

    # ── Add Admin ──
    if action == PA_ADMIN_ADD:
        if not is_owner:
            return
        context.user_data["panel_await"] = "add_admin"
        await safe_edit(
            query,
            "➕ <b>Add Admin</b>\n━━━━━━━━━━━━━━━━━━━━\n\n"
            "Send the <b>User ID</b> of the person to make admin.\n"
            "They must have started the bot.",
            reply_markup=panel_input_cancel_keyboard(),
        )
        return

    # ── Remove Admin (confirm) ──
    if action.startswith(f"{PA_ADMIN_RM}:") and not action.startswith(f"{PA_ADMIN_RM_YES}:"):
        if not is_owner:
            return
        target_uid = int(action.split(":")[-1])
        await safe_edit(
            query,
            f"🗑 <b>Remove Admin</b>\n━━━━━━━━━━━━━━━━━━━━\n\n"
            f"Remove admin <code>{target_uid}</code>?\n"
            f"They will lose all permissions immediately.",
            reply_markup=confirm_remove_admin_keyboard(target_uid),
        )
        return

    # ── Remove Admin (execute) ──
    if action.startswith(f"{PA_ADMIN_RM_YES}:"):
        if not is_owner:
            return
        target_uid = int(action.split(":")[-1])
        removed = await db.remove_admin(target_uid)
        if removed:
            await safe_send(context, target_uid, "⚠️ Your admin access has been revoked.")
        admins = await db.list_admins()
        count = len([a for a in admins if a["user_id"] not in config.admin_ids])
        await safe_edit(
            query,
            f"{'✅ Admin removed.' if removed else '❌ Admin not found.'}\n\n"
            f"👮 <b>Admin Management</b>\n━━━━━━━━━━━━━━━━━━━━\n\n"
            f"📋 {count} admin(s) configured.",
            reply_markup=admin_list_keyboard(admins, config.admin_ids),
        )
        return

    # ── Edit Admin Permissions ──
    if action.startswith(f"{PA_ADMIN_EDIT}:"):
        if not is_owner:
            return
        target_uid = int(action.split(":")[-1])
        admin_rec = await db.get_admin(target_uid)
        if not admin_rec:
            await query.answer("Admin not found.", show_alert=True)
            return
        current_perms = admin_rec.get("permissions", [])
        # Store in user_data for toggle mutations
        context.user_data["editing_perms"] = list(current_perms)
        context.user_data["editing_uid"] = target_uid
        user_rec = await db.get_user(target_uid)
        name = escape(user_rec.get("first_name", str(target_uid))) if user_rec else str(target_uid)
        await safe_edit(
            query,
            f"⚙️ <b>Permissions for {name}</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"ID: <code>{target_uid}</code>\n"
            f"Tap to toggle, then Save.",
            reply_markup=permission_editor_keyboard(target_uid, current_perms),
        )
        return

    # ── Toggle Permission ──
    if action.startswith(f"{PA_PERM_TOGGLE}:"):
        if not is_owner:
            return
        parts = action.split(":")
        if len(parts) < 3:
            return
        target_uid = int(parts[1])
        perm_key = parts[2]
        editing = context.user_data.get("editing_perms", [])
        if perm_key in editing:
            editing.remove(perm_key)
        else:
            editing.append(perm_key)
        context.user_data["editing_perms"] = editing
        user_rec = await db.get_user(target_uid)
        name = escape(user_rec.get("first_name", str(target_uid))) if user_rec else str(target_uid)
        await safe_edit(
            query,
            f"⚙️ <b>Permissions for {name}</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"ID: <code>{target_uid}</code>\n"
            f"Tap to toggle, then Save.",
            reply_markup=permission_editor_keyboard(target_uid, editing),
        )
        return

    # ── Save Admin Permissions ──
    if action.startswith(f"{PA_SAVE_ADMIN}:"):
        if not is_owner:
            return
        target_uid = int(action.split(":")[-1])
        new_perms = context.user_data.get("editing_perms", [])
        await db.update_admin_permissions(target_uid, new_perms)
        context.user_data.pop("editing_perms", None)
        context.user_data.pop("editing_uid", None)

        perm_display = ", ".join(PERM_LABELS.get(p, p) for p in new_perms) or "None"
        await safe_send(
            context, target_uid,
            f"🛡 <b>Your admin permissions updated</b>\n\n{perm_display}",
        )

        admins = await db.list_admins()
        count = len([a for a in admins if a["user_id"] not in config.admin_ids])
        await safe_edit(
            query,
            f"✅ Permissions saved for <code>{target_uid}</code>.\n\n"
            f"👮 <b>Admin Management</b>\n━━━━━━━━━━━━━━━━━━━━\n\n"
            f"📋 {count} admin(s) configured.",
            reply_markup=admin_list_keyboard(admins, config.admin_ids),
        )
        return

    # ── Reports ──
    if action == PA_REPORTS:
        if "view_reports" not in perms:
            await query.answer("No permission.", show_alert=True)
            return
        reports = await db.get_recent_reports(limit=10)
        if not reports:
            await safe_edit(
                query,
                "📋 <b>Recent Reports</b>\n━━━━━━━━━━━━━━━━━━━━\n\nNo reports yet.",
                reply_markup=panel_back_keyboard(),
            )
            return

        lines = ["📋 <b>Recent Reports</b>\n━━━━━━━━━━━━━━━━━━━━\n"]
        for i, r in enumerate(reports, 1):
            reporter = r.get("reporter_id", "?")
            reported = r.get("reported_id", "?")
            reason = escape(str(r.get("reason", "—"))[:80])
            created = str(r.get("created_at", ""))[:19]
            lines.append(
                f"<b>{i}.</b> {reporter} → {reported}\n"
                f"    📝 {reason}\n"
                f"    🕐 {created}"
            )
        text = "\n".join(lines)
        if len(text) > 3900:
            text = text[:3900] + "\n…"
        await safe_edit(query, text, reply_markup=panel_back_keyboard())
        return

    # ── Queue ──
    if action == PA_QUEUE:
        if "manage_search" not in perms and not is_owner:
            await query.answer("No permission.", show_alert=True)
            return
        searching = await db.get_users_searching()
        pairs = await db.get_chatting_pairs()
        queue = await matcher.queue_size()

        lines = [
            "🔍 <b>Search Queue & Active Chats</b>\n━━━━━━━━━━━━━━━━━━━━\n",
            f"📡 In-memory queue: <b>{queue}</b>",
            f"🔍 DB searching: <b>{len(searching)}</b>",
            f"💬 Active pairs: <b>{len(pairs)}</b>",
        ]

        if pairs:
            lines.append("\n<b>Active Chat Pairs:</b>")
            for a, b in pairs[:15]:
                lines.append(f"  💬 <code>{a}</code> ↔ <code>{b}</code>")
            if len(pairs) > 15:
                lines.append(f"  … and {len(pairs) - 15} more")

        text = "\n".join(lines)
        await safe_edit(query, text, reply_markup=panel_back_keyboard())
        return

    # ── Force Disconnect ──
    if action.startswith(f"{PA_FORCE_DC}:"):
        if not is_owner:
            return
        target_uid = int(action.split(":")[-1])
        from handlers.session import end_chat
        await end_chat(context, target_uid, reason="ended")
        await query.answer(f"Disconnected {target_uid}", show_alert=True)
        return


# ─── Panel text input handler ───

async def handle_panel_input(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> bool:
    """Process text input when panel is awaiting user input.

    Returns True if input was consumed, False if not in panel mode.
    Called from relay_message BEFORE chat relay.
    """
    awaiting = context.user_data.get("panel_await")
    if not awaiting:
        return False

    if not update.message or not update.message.text:
        return False

    user = update.effective_user
    if not user:
        return False

    text = update.message.text.strip()
    db: Database = context.bot_data["db"]
    config: Config = context.bot_data["config"]
    matcher: Matcher = context.bot_data["matcher"]
    is_owner = user.id in config.admin_ids

    # Clear state FIRST to prevent re-entry
    context.user_data.pop("panel_await", None)

    # ── Lookup ──
    if awaiting == "lookup":
        try:
            target_id = int(text)
        except ValueError:
            await update.message.reply_text(
                "❌ Invalid ID. Send a numeric User ID.",
                reply_markup=panel_back_keyboard(),
            )
            return True
        record = await db.get_user(target_id)
        if not record:
            await update.message.reply_text(
                f"❌ User <code>{target_id}</code> not found.",
                parse_mode="HTML",
                reply_markup=panel_back_keyboard(),
            )
            return True
        await update.message.reply_text(
            _user_profile_text(record),
            parse_mode="HTML",
            reply_markup=panel_back_keyboard(),
        )
        return True

    # ── Ban ──
    if awaiting == "ban":
        try:
            target_id = int(text)
        except ValueError:
            await update.message.reply_text(
                "❌ Invalid ID.",
                reply_markup=panel_back_keyboard(),
            )
            return True
        context.user_data["panel_await"] = f"ban_reason:{target_id}"
        await update.message.reply_text(
            f"🔨 Banning <code>{target_id}</code>.\n\nSend the <b>reason</b> (or type <code>-</code> for no reason):",
            parse_mode="HTML",
            reply_markup=panel_input_cancel_keyboard(),
        )
        return True

    # ── Ban Reason ──
    if awaiting.startswith("ban_reason:"):
        target_id = int(awaiting.split(":")[-1])
        reason = text if text != "-" else "Banned by admin"
        await db.ban_user(target_id, reason)
        await matcher.leave(target_id)
        await safe_send(context, target_id, f"🚫 You have been banned.\nReason: {reason}")
        await update.message.reply_text(
            f"✅ Banned <code>{target_id}</code>.\nReason: {escape(reason)}",
            parse_mode="HTML",
            reply_markup=panel_back_keyboard(),
        )
        from services.logger import log_to_channel
        try:
            await log_to_channel(
                context, config.log_channel_id, db,
                event="🔨 Panel Ban",
                user=user,
                extra=f"Target: {target_id} | {reason}",
                persist_message=False,
            )
        except Exception:
            pass
        return True

    # ── Unban ──
    if awaiting == "unban":
        try:
            target_id = int(text)
        except ValueError:
            await update.message.reply_text(
                "❌ Invalid ID.",
                reply_markup=panel_back_keyboard(),
            )
            return True
        await db.unban_user(target_id)
        await update.message.reply_text(
            f"✅ Unbanned <code>{target_id}</code>.",
            parse_mode="HTML",
            reply_markup=panel_back_keyboard(),
        )
        return True

    # ── Broadcast ──
    if awaiting == "broadcast":
        user_ids = await db.get_broadcast_user_ids()
        total = len(user_ids)
        if total == 0:
            await update.message.reply_text(
                "❌ No users to broadcast to.",
                reply_markup=panel_back_keyboard(),
            )
            return True

        progress_msg = await update.message.reply_text(
            f"📢 Broadcasting to {total} users…"
        )

        broadcast_text = f"📢 <b>Announcement</b>\n\n{text}"
        sem = asyncio.Semaphore(config.broadcast_concurrency)
        sent = 0
        failed = 0

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
                f"📢 <b>Broadcast complete!</b>\n\n✅ Sent: {sent} | ❌ Failed: {failed}",
                parse_mode="HTML",
            )
        except Exception:
            pass
        return True

    # ── Add Admin ──
    if awaiting == "add_admin":
        if not is_owner:
            return True
        try:
            target_id = int(text)
        except ValueError:
            await update.message.reply_text(
                "❌ Invalid ID. Send a numeric User ID.",
                reply_markup=panel_back_keyboard(),
            )
            return True

        if target_id in config.admin_ids:
            await update.message.reply_text(
                "⚠️ This user is already an owner (in ADMIN_IDS).",
                reply_markup=panel_back_keyboard(),
            )
            return True

        existing = await db.get_admin(target_id)
        if existing:
            await update.message.reply_text(
                f"⚠️ <code>{target_id}</code> is already an admin. Use the edit button to change permissions.",
                parse_mode="HTML",
                reply_markup=panel_back_keyboard(),
            )
            return True

        # Start with empty permissions — owner will toggle them
        default_perms: list[str] = []
        await db.add_admin(target_id, user.id, default_perms)
        context.user_data["editing_perms"] = list(default_perms)
        context.user_data["editing_uid"] = target_id

        user_rec = await db.get_user(target_id)
        name = escape(user_rec.get("first_name", str(target_id))) if user_rec else str(target_id)

        await update.message.reply_text(
            f"✅ <b>{name}</b> added as admin.\n\n"
            f"⚙️ <b>Set Permissions</b>\n━━━━━━━━━━━━━━━━━━━━\n\n"
            f"Tap to toggle permissions, then Save.",
            parse_mode="HTML",
            reply_markup=permission_editor_keyboard(target_id, default_perms),
        )
        await safe_send(
            context, target_id,
            "🛡 <b>You've been made an admin!</b>\n\n"
            "Use /panel to access the Admin Panel.",
        )
        return True

    return False
