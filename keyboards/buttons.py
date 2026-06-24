"""Premium inline keyboards — clean, minimal, professional.

Regular users see ONLY what they need:
  • Idle: Find Partner + Settings
  • Searching: Cancel
  • Chatting: End/Next + Report/Block

Stats, Help, Admin tools are ONLY in /panel.
"""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import KeyboardButtonStyle as S

# ── User callback prefixes ──
CB_GENDER = "g:"
CB_LOOKING = "l:"
CB_ACTION = "a:"
CB_RATE = "r:"

# ── Panel callback prefix ──
CB_PANEL = "p:"

GENDER_MALE = "male"
GENDER_FEMALE = "female"
GENDER_OTHER = "other"

LOOK_MALE = "male"
LOOK_FEMALE = "female"
LOOK_ANY = "any"

ACT_ACCEPT_RULES = "accept_rules"
ACT_FIND = "find"
ACT_STOP_SEARCH = "stop_search"
ACT_END_CHAT = "end_chat"
ACT_NEXT = "next"
ACT_SETTINGS = "settings"
ACT_STATS = "stats"
ACT_HELP = "help"
ACT_BACK = "back"
ACT_CHANGE_GENDER = "change_gender"
ACT_CHANGE_LOOKING = "change_looking"
ACT_REPORT = "report"
ACT_REPORT_CONFIRM = "report_confirm"
ACT_BLOCK = "block"
ACT_SKIP_FEEDBACK = "skip_feedback"

# ── Panel actions ──
PA_MAIN = "main"
PA_STATS = "stats"
PA_USERS = "users"
PA_USER_LOOKUP = "ul"
PA_USER_BAN = "ub"
PA_USER_UNBAN = "uu"
PA_BROADCAST = "bc"
PA_ADMINS = "adm"
PA_ADMIN_ADD = "aa"
PA_ADMIN_RM = "ar"       # + :uid
PA_ADMIN_RM_YES = "ary"  # + :uid
PA_ADMIN_EDIT = "ae"     # + :uid
PA_PERM_TOGGLE = "pt"    # + :uid:perm
PA_SAVE_ADMIN = "sa"     # + :uid
PA_REPORTS = "rp"
PA_QUEUE = "qu"
PA_FORCE_DC = "fd"       # + :uid
PA_HOME = "home"

# ── Permission definitions ──
ALL_PERMISSIONS = [
    ("stats", "📊 Stats"),
    ("user_lookup", "👤 Lookup"),
    ("ban", "🔨 Ban"),
    ("unban", "🔓 Unban"),
    ("broadcast", "📢 Broadcast"),
    ("view_reports", "📋 Reports"),
    ("manage_search", "🔍 Queue"),
]

PERM_LABELS = {k: v for k, v in ALL_PERMISSIONS}


def _btn(text: str, data: str, *, style: str | None = None) -> InlineKeyboardButton:
    return InlineKeyboardButton(text, callback_data=data, style=style)


# ═══════════════════════════════════════════════════════════════
# User keyboards — clean, minimal, professional
# ═══════════════════════════════════════════════════════════════

def rules_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[_btn("✅ I Accept the Rules", f"{CB_ACTION}{ACT_ACCEPT_RULES}", style=S.SUCCESS)]]
    )


def gender_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            _btn("👨 Male", f"{CB_GENDER}{GENDER_MALE}", style=S.PRIMARY),
            _btn("👩 Female", f"{CB_GENDER}{GENDER_FEMALE}", style=S.PRIMARY),
        ],
        [_btn("🌈 Other", f"{CB_GENDER}{GENDER_OTHER}", style=S.PRIMARY)],
    ])


def looking_for_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            _btn("👨 Boys", f"{CB_LOOKING}{LOOK_MALE}", style=S.PRIMARY),
            _btn("👩 Girls", f"{CB_LOOKING}{LOOK_FEMALE}", style=S.PRIMARY),
        ],
        [_btn("🌍 Anyone", f"{CB_LOOKING}{LOOK_ANY}", style=S.SUCCESS)],
    ])


def main_menu_keyboard(
    is_searching: bool = False,
    is_chatting: bool = False,
) -> InlineKeyboardMarkup:
    """Clean main menu — users see ONLY what they need."""
    rows: list[list[InlineKeyboardButton]] = []

    if is_chatting:
        rows.append([
            _btn("🔴 End Chat", f"{CB_ACTION}{ACT_END_CHAT}", style=S.DANGER),
            _btn("⏭ Next", f"{CB_ACTION}{ACT_NEXT}", style=S.PRIMARY),
        ])
        rows.append([
            _btn("🚨 Report", f"{CB_ACTION}{ACT_REPORT}", style=S.DANGER),
            _btn("🚫 Block", f"{CB_ACTION}{ACT_BLOCK}", style=S.DANGER),
        ])
    elif is_searching:
        rows.append(
            [_btn("🛑 Cancel Search", f"{CB_ACTION}{ACT_STOP_SEARCH}", style=S.DANGER)]
        )
    else:
        rows.append(
            [_btn("🔍 Find Partner", f"{CB_ACTION}{ACT_FIND}", style=S.PRIMARY)]
        )
        rows.append(
            [_btn("⚙️ Settings", f"{CB_ACTION}{ACT_SETTINGS}", style=S.PRIMARY)]
        )

    return InlineKeyboardMarkup(rows)


def settings_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [_btn("🎭 Change Gender", f"{CB_ACTION}{ACT_CHANGE_GENDER}", style=S.PRIMARY)],
        [_btn("💫 Change Preference", f"{CB_ACTION}{ACT_CHANGE_LOOKING}", style=S.PRIMARY)],
        [_btn("⬅️ Back", f"{CB_ACTION}{ACT_BACK}", style=S.PRIMARY)],
    ])


def confirm_end_chat_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            _btn("✅ Yes, End Chat", f"{CB_ACTION}{ACT_END_CHAT}:confirm", style=S.DANGER),
            _btn("❌ Cancel", f"{CB_ACTION}{ACT_BACK}", style=S.SUCCESS),
        ]
    ])


def report_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            _btn("🚨 Submit Report", f"{CB_ACTION}{ACT_REPORT_CONFIRM}", style=S.DANGER),
            _btn("❌ Cancel", f"{CB_ACTION}{ACT_BACK}", style=S.PRIMARY),
        ]
    ])


def feedback_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            _btn("⭐", f"{CB_RATE}1", style=S.PRIMARY),
            _btn("⭐⭐", f"{CB_RATE}2", style=S.PRIMARY),
            _btn("⭐⭐⭐", f"{CB_RATE}3", style=S.SUCCESS),
        ],
        [
            _btn("⭐⭐⭐⭐", f"{CB_RATE}4", style=S.SUCCESS),
            _btn("⭐⭐⭐⭐⭐", f"{CB_RATE}5", style=S.SUCCESS),
        ],
        [_btn("Skip", f"{CB_ACTION}{ACT_SKIP_FEEDBACK}", style=S.DANGER)],
    ])


# ═══════════════════════════════════════════════════════════════
# Panel keyboards (Owner + Admin)
# ═══════════════════════════════════════════════════════════════

def _pbtn(text: str, action: str, *, style: str | None = None) -> InlineKeyboardButton:
    return _btn(text, f"{CB_PANEL}{action}", style=style)


def owner_panel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            _pbtn("📊 Live Stats", PA_STATS, style=S.SUCCESS),
            _pbtn("👥 Users", PA_USERS, style=S.PRIMARY),
        ],
        [
            _pbtn("📢 Broadcast", PA_BROADCAST, style=S.PRIMARY),
            _pbtn("👮 Admins", PA_ADMINS, style=S.PRIMARY),
        ],
        [
            _pbtn("📋 Reports", PA_REPORTS, style=S.DANGER),
            _pbtn("🔍 Queue", PA_QUEUE, style=S.SUCCESS),
        ],
        [_pbtn("🏠 Back to Bot", PA_HOME, style=S.PRIMARY)],
    ])


def admin_panel_keyboard(permissions: list[str]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []

    row1 = []
    if "stats" in permissions:
        row1.append(_pbtn("📊 Stats", PA_STATS, style=S.SUCCESS))
    if "user_lookup" in permissions:
        row1.append(_pbtn("👤 Lookup", PA_USER_LOOKUP, style=S.PRIMARY))
    if row1:
        rows.append(row1)

    row2 = []
    if "ban" in permissions:
        row2.append(_pbtn("🔨 Ban", PA_USER_BAN, style=S.DANGER))
    if "unban" in permissions:
        row2.append(_pbtn("🔓 Unban", PA_USER_UNBAN, style=S.SUCCESS))
    if row2:
        rows.append(row2)

    row3 = []
    if "broadcast" in permissions:
        row3.append(_pbtn("📢 Broadcast", PA_BROADCAST, style=S.PRIMARY))
    if "view_reports" in permissions:
        row3.append(_pbtn("📋 Reports", PA_REPORTS, style=S.DANGER))
    if row3:
        rows.append(row3)

    if "manage_search" in permissions:
        rows.append([_pbtn("🔍 Queue", PA_QUEUE, style=S.SUCCESS)])

    rows.append([_pbtn("🏠 Back to Bot", PA_HOME, style=S.PRIMARY)])
    return InlineKeyboardMarkup(rows)


def user_management_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [_pbtn("👤 Lookup User", PA_USER_LOOKUP, style=S.PRIMARY)],
        [
            _pbtn("🔨 Ban User", PA_USER_BAN, style=S.DANGER),
            _pbtn("🔓 Unban User", PA_USER_UNBAN, style=S.SUCCESS),
        ],
        [_pbtn("⬅️ Back", PA_MAIN, style=S.PRIMARY)],
    ])


def admin_list_keyboard(
    admins: list[dict],
    owner_ids: frozenset[int],
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for adm in admins:
        uid = adm["user_id"]
        if uid in owner_ids:
            continue
        perms = adm.get("permissions", [])
        label = f"👮 {uid} ({len(perms)} perms)"
        rows.append([
            _pbtn(label, f"{PA_ADMIN_EDIT}:{uid}", style=S.PRIMARY),
            _pbtn("🗑", f"{PA_ADMIN_RM}:{uid}", style=S.DANGER),
        ])

    rows.append([_pbtn("➕ Add Admin", PA_ADMIN_ADD, style=S.SUCCESS)])
    rows.append([_pbtn("⬅️ Back", PA_MAIN, style=S.PRIMARY)])
    return InlineKeyboardMarkup(rows)


def permission_editor_keyboard(
    target_uid: int,
    current_perms: list[str],
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for perm_key, perm_label in ALL_PERMISSIONS:
        is_on = perm_key in current_perms
        icon = "✅" if is_on else "❌"
        rows.append([
            _pbtn(
                f"{icon} {perm_label}",
                f"{PA_PERM_TOGGLE}:{target_uid}:{perm_key}",
                style=S.SUCCESS if is_on else S.DANGER,
            )
        ])

    rows.append([
        _pbtn("💾 Save", f"{PA_SAVE_ADMIN}:{target_uid}", style=S.SUCCESS),
        _pbtn("❌ Cancel", PA_ADMINS, style=S.DANGER),
    ])
    return InlineKeyboardMarkup(rows)


def confirm_remove_admin_keyboard(target_uid: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            _pbtn("✅ Yes, Remove", f"{PA_ADMIN_RM_YES}:{target_uid}", style=S.DANGER),
            _pbtn("❌ Cancel", PA_ADMINS, style=S.SUCCESS),
        ]
    ])


def panel_back_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [_pbtn("⬅️ Back to Panel", PA_MAIN, style=S.PRIMARY)],
    ])


def panel_input_cancel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [_pbtn("❌ Cancel", PA_MAIN, style=S.DANGER)],
    ])
