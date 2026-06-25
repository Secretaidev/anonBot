"""Premium UI copy — clean chat, polished status card."""

BRAND = "AnoyBot"

WELCOME = (
    "🎭 <b>Welcome to {brand}</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n\n"
    "Talk to strangers — 100% anonymous.\n\n"
    "🔒 Private  ·  ⚡ Instant  ·  🛡 Safe\n\n"
    "<i>18+ only · Be kind · No spam</i>"
)

SETUP_GENDER = (
    "🎭 <b>Your gender</b>\n\n"
    "<i>Only for matching — partner never sees this.</i>"
)

SETUP_LOOKING = "💫 <b>Who do you want to meet?</b>"

READY = (
    "✅ <b>You're ready!</b>\n\n"
    "{gender}  ·  {looking}\n\n"
    "Tap the green button to connect 👇"
)

SEARCHING = "🔍 <b>Searching</b>{pulse}\n\n<i>Hang tight — auto-connects when found.</i>"

MATCHED = (
    "🟢 <b>Connected!</b>\n\n"
    "Chat below 👇 — text, photos, voice & stickers work.\n"
    "<i>Share profile safely: /link</i>"
)

CHAT_ENDED = "Chat ended."
CHAT_PARTNER_LEFT = "Partner left."
CHAT_NEXT = "🔍 Finding next partner…{pulse}"
SEARCH_CANCELLED = "Search cancelled."
PARTNER_FOUND_HINT = "🟢 <b>Connected!</b> — say hi below 👇"
SEARCH_BLOCKED_RETRY = "🔍 <b>Searching</b>{pulse}"
SEARCH_TIMEOUT = "⏱ No one online right now.\n\nTap 🔍 Find Partner to retry."

CONFIRM_END = "⚠️ <b>End this chat?</b>\n\nYour partner will be notified."

SETTINGS = (
    "⚙️ <b>Settings</b>\n\n"
    "🎭 {gender}\n"
    "💫 {looking}"
)

HELP = (
    "❓ <b>How it works</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n\n"
    "1️⃣ Set gender & preference\n"
    "2️⃣ Tap <b>🔍 Find Partner</b> (green)\n"
    "3️⃣ Chat anonymously below\n"
    "4️⃣ <b>End</b> or <b>Next</b> anytime\n"
    "5️⃣ <b>Report / Block</b> if needed\n"
    "6️⃣ <b>/link</b> to share profile safely"
)

FEEDBACK = "⭐ <b>Rate this chat</b>"
FEEDBACK_THANKS = "⭐ Thanks for your feedback!"

BANNED = "🚫 Your account has been restricted."
NOT_IN_CHAT = ""
RATE_LIMITED = "⏳ Slow down — too many messages."
REPORT_SENT = "🚨 Report submitted. We'll review it."
REPORT_PROMPT = "🚨 Submit a report?"

SPAM_BLOCKED = "⚠️ Links & @usernames blocked. Use /link instead."
LINK_SHARED = "Profile shared ✓"
LINK_RECEIVED = "🔗 Partner shared their profile:\n{link}"
LINK_NO_USERNAME = "Set a @username first, then /link"
LINK_NOT_IN_CHAT = "You're not in a chat."

STOP_IDLE = "Nothing to stop."
STOP_SEARCH = "Search stopped."
STOP_CHAT = "Chat ended."

GENDER_LABELS = {"male": "👨 Male", "female": "👩 Female", "other": "🌈 Other"}
LOOKING_LABELS = {"male": "👨 Boys", "female": "👩 Girls", "any": "🌍 Anyone"}

PULSE_FRAMES = ("", " ·", " ··", " ···", " ····")


def gender_label(value: str | None) -> str:
    return GENDER_LABELS.get(value or "", value or "—")


def looking_label(value: str | None) -> str:
    return LOOKING_LABELS.get(value or "", value or "—")
