"""Professional UI copy — clean, minimal, world-class stranger-chat UX.

Regular users see ZERO stats or admin info.
Every message is short, warm, and purposeful.
"""

BRAND = "AnoyBot"

WELCOME = (
    "🎭 <b>Welcome to {brand}</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n\n"
    "Talk to strangers — completely anonymous.\n\n"
    "🔒 <b>Private</b> — no names, no profiles shared\n"
    "⚡ <b>Instant</b> — matched in seconds\n"
    "🛡 <b>Safe</b> — report or block anytime\n\n"
    "📜 <i>18+ only. Be respectful. No spam or harassment.</i>"
)

SETUP_GENDER = (
    "🎭 <b>Your Gender</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n\n"
    "Used only for matching — your partner never sees this."
)

SETUP_LOOKING = (
    "💫 <b>Who would you like to meet?</b>\n"
    "━━━━━━━━━━━━━━━━━━━━"
)

READY = (
    "✅ <b>You're all set</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n\n"
    "🎭 {gender}  ·  💫 {looking}\n\n"
    "Tap below when you're ready to connect."
)

SEARCHING = (
    "🔍 <b>Finding someone…</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n\n"
    "{pulse} Scanning for a match…\n\n"
    "<i>Stay on this screen — you'll connect automatically.</i>"
)

MATCHED = (
    "🎉 <b>You're connected!</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n\n"
    "You're chatting <b>anonymously</b> with a stranger.\n"
    "Say hi 👋 — text, photos, voice & stickers all work.\n\n"
    "💡 <i>Tip: Ask an open question to break the ice.</i>\n"
    "🛡 Use <b>Report</b> or <b>Block</b> if anything feels off."
)

CHAT_ENDED = "🔴 Chat ended."
CHAT_PARTNER_LEFT = "👋 Your partner left the chat."
CHAT_NEXT = "⏭ Finding your next partner…"
SEARCH_CANCELLED = "🛑 Search cancelled."
PARTNER_FOUND_HINT = "🎉 Connected!"
SEARCH_BLOCKED_RETRY = "🔄 Searching for a new partner…"
SEARCH_TIMEOUT = (
    "⏱ <b>No match found</b>\n\n"
    "Nobody's available right now. Tap 🔍 to try again."
)

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
    "1️⃣ Set gender & who you want to meet\n"
    "2️⃣ Tap <b>🔍 Find Partner</b>\n"
    "3️⃣ Chat anonymously — all media works\n"
    "4️⃣ <b>🔴 End</b> or <b>⏭ Next</b> anytime\n"
    "5️⃣ <b>🚨 Report</b> or <b>🚫 Block</b> if needed\n\n"
    "🔒 Your identity is never shared with your partner."
)

FEEDBACK = (
    "⭐ <b>Rate this chat</b>\n\n"
    "How was your conversation?"
)

FEEDBACK_THANKS = "⭐ Thanks — your feedback helps keep the community great."

BANNED = "🚫 Your account has been restricted."
NOT_IN_CHAT = "💡 You're not in a chat. Tap 🔍 to find someone."
RATE_LIMITED = "⏳ Slow down — you're sending messages too fast."
REPORT_SENT = "🚨 <b>Report submitted.</b> Our team will review it."
REPORT_PROMPT = "Submit a report? We'll look into it right away."

STOP_IDLE = "💡 Nothing to stop. Use /start."
STOP_SEARCH = "🛑 Search stopped."
STOP_CHAT = "🔴 Chat ended."

GENDER_LABELS = {"male": "👨 Male", "female": "👩 Female", "other": "🌈 Other"}
LOOKING_LABELS = {"male": "👨 Boys", "female": "👩 Girls", "any": "🌍 Anyone"}

PULSE_FRAMES = ("⏳", "🔎", "📡", "✨", "🌐")


def gender_label(value: str | None) -> str:
    return GENDER_LABELS.get(value or "", value or "—")


def looking_label(value: str | None) -> str:
    return LOOKING_LABELS.get(value or "", value or "—")
