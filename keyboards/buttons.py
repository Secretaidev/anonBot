"""Premium inline keyboards — primary=blue, success=green, danger=red."""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import KeyboardButtonStyle as S

CB_GENDER = "g:"
CB_LOOKING = "l:"
CB_ACTION = "a:"
CB_RATE = "r:"

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


def _btn(text: str, data: str, *, style: str | None = None) -> InlineKeyboardButton:
    return InlineKeyboardButton(text, callback_data=data, style=style)


def rules_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[_btn("✅ I Accept the Rules", f"{CB_ACTION}{ACT_ACCEPT_RULES}", style=S.SUCCESS)]]
    )


def gender_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                _btn("👨 Male", f"{CB_GENDER}{GENDER_MALE}", style=S.PRIMARY),
                _btn("👩 Female", f"{CB_GENDER}{GENDER_FEMALE}", style=S.PRIMARY),
            ],
            [_btn("🌈 Other", f"{CB_GENDER}{GENDER_OTHER}", style=S.PRIMARY)],
        ]
    )


def looking_for_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                _btn("👨 Boys", f"{CB_LOOKING}{LOOK_MALE}", style=S.PRIMARY),
                _btn("👩 Girls", f"{CB_LOOKING}{LOOK_FEMALE}", style=S.PRIMARY),
            ],
            [_btn("🌍 Anyone", f"{CB_LOOKING}{LOOK_ANY}", style=S.SUCCESS)],
            [_btn("⬅️ Back", f"{CB_ACTION}{ACT_BACK}", style=S.PRIMARY)],
        ]
    )


def main_menu_keyboard(
    is_searching: bool = False,
    is_chatting: bool = False,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []

    if is_chatting:
        rows.append(
            [
                _btn("🔴 End Chat", f"{CB_ACTION}{ACT_END_CHAT}", style=S.DANGER),
                _btn("⏭ Next", f"{CB_ACTION}{ACT_NEXT}", style=S.PRIMARY),
            ]
        )
        rows.append(
            [
                _btn("🚨 Report", f"{CB_ACTION}{ACT_REPORT}", style=S.DANGER),
                _btn("🚫 Block", f"{CB_ACTION}{ACT_BLOCK}", style=S.DANGER),
            ]
        )
    elif is_searching:
        rows.append(
            [_btn("🛑 Cancel Search", f"{CB_ACTION}{ACT_STOP_SEARCH}", style=S.DANGER)]
        )
    else:
        rows.append(
            [_btn("🔍 Find Partner", f"{CB_ACTION}{ACT_FIND}", style=S.PRIMARY)]
        )

    rows.append(
        [
            _btn("⚙️ Settings", f"{CB_ACTION}{ACT_SETTINGS}", style=S.PRIMARY),
            _btn("📊 Stats", f"{CB_ACTION}{ACT_STATS}", style=S.SUCCESS),
        ]
    )
    rows.append([_btn("❓ Help", f"{CB_ACTION}{ACT_HELP}", style=S.SUCCESS)])

    return InlineKeyboardMarkup(rows)


def settings_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [_btn("🎭 Change Gender", f"{CB_ACTION}{ACT_CHANGE_GENDER}", style=S.PRIMARY)],
            [_btn("💫 Change Preference", f"{CB_ACTION}{ACT_CHANGE_LOOKING}", style=S.PRIMARY)],
            [_btn("🏠 Main Menu", f"{CB_ACTION}{ACT_BACK}", style=S.SUCCESS)],
        ]
    )


def confirm_end_chat_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                _btn("✅ Yes, End Chat", f"{CB_ACTION}{ACT_END_CHAT}:confirm", style=S.DANGER),
                _btn("❌ Cancel", f"{CB_ACTION}{ACT_BACK}", style=S.SUCCESS),
            ]
        ]
    )


def report_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                _btn("🚨 Submit Report", f"{CB_ACTION}{ACT_REPORT_CONFIRM}", style=S.DANGER),
                _btn("❌ Cancel", f"{CB_ACTION}{ACT_BACK}", style=S.PRIMARY),
            ]
        ]
    )


def feedback_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
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
        ]
    )
