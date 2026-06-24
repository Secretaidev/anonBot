"""Professional UI copy — clean, minimal, no clutter.

Regular users see ZERO stats or admin info.
Every message is short and purposeful.
"""

BRAND = "AnoyBot"

WELCOME = (
    "🎭 <b>Welcome to {brand}</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n\n"
    "Connect with strangers anonymously.\n\n"
    "🔒 <b>100% Anonymous</b> — your identity is hidden\n"
    "⚡ <b>Instant Matching</b> — connect in seconds\n"
    "🛡 <b>Safe & Monitored</b> — report abuse anytime\n\n"
    "📜 <i>By continuing, you agree to be respectful,\n"
    "18+, and follow our community rules.</i>"
)

SETUP_GENDER = (
    "🎭 <b>Select Your Gender</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n\n"
    "This is used only for matching.\n"
    "Your partner <b>never</b> sees this."
)

SETUP_LOOKING = (
    "💫 <b>Who do you want to chat with?</b>\n"
    "━━━━━━━━━━━━━━━━━━━━"
)

READY = (
    "✅ <b>Ready to Connect</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n\n"
    "🎭 {gender}  ·  💫 {looking}\n\n"
    "Tap below to find someone new."
)

SEARCHING = (
    "🔍 <b>Searching…</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n\n"
    "{pulse} Looking for your match…\n\n"
    "<i>Hang tight — connection is instant.</i>"
)

MATCHED = (
    "🎉 <b>Connected!</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n\n"
    "You're chatting <b>anonymously</b>.\n"
    "Say hi 👋 — text, photos, voice & stickers all work."
)

CHAT_ENDED = "🔴 Chat ended."
CHAT_PARTNER_LEFT = "👋 Your partner left the chat."
CHAT_NEXT = "⏭ Finding your next partner…"
SEARCH_CANCELLED = "🛑 Search cancelled."
PARTNER_FOUND_HINT = "🎉 Connected!"
SEARCH_BLOCKED_RETRY = "🔄 Searching for a new partner…"
SEARCH_TIMEOUT = "⏱ No one found. Tap 🔍 to try again."

CONFIRM_END = (
    "⚠️ <b>End this chat?</b>\n\n"
    "Your partner will be notified."
)

SETTINGS = (
    "⚙️ <b>Settings</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n\n"
    "🎭 Gender: {gender}\n"
    "💫 Preference: {looking}"
)

HELP = (
    "❓ <b>How It Works</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n\n"
    "1️⃣ Set gender & preference\n"
    "2️⃣ Tap <b>🔍 Find Partner</b>\n"
    "3️⃣ Chat anonymously\n"
    "4️⃣ <b>🔴 End</b> or <b>⏭ Next</b> anytime\n"
    "5️⃣ <b>🚨 Report</b> if needed"
)

FEEDBACK = (
    "⭐ <b>Rate this chat</b>\n\n"
    "How was your partner?"
)

FEEDBACK_THANKS = "⭐ Thanks for your feedback!"

BANNED = "🚫 Your account has been restricted."
NOT_IN_CHAT = "💡 You're not in a chat. Tap 🔍 to find someone."
RATE_LIMITED = "⏳ Slow down — too many messages."
REPORT_SENT = "🚨 <b>Report submitted.</b> We'll review it."
REPORT_PROMPT = "Tap below to submit a report."

STOP_IDLE = "💡 Nothing to stop. Use /start."
STOP_SEARCH = "🛑 Search stopped."
STOP_CHAT = "🔴 Chat ended."

GENDER_LABELS = {"male": "👨 Male", "female": "👩 Female", "other": "🌈 Other"}
LOOKING_LABELS = {"male": "👨 Boys", "female": "👩 Girls", "any": "🌍 Anyone"}

PULSE_FRAMES = ("⏳", "🔎", "📡", "✨")


def gender_label(value: str | None) -> str:
    return GENDER_LABELS.get(value or "", value or "—")


def looking_label(value: str | None) -> str:
    return LOOKING_LABELS.get(value or "", value or "—")
