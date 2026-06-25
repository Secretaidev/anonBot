"""Ultra-clean UI copy — one status card, zero chat clutter."""

BRAND = "AnoyBot"

WELCOME = (
    "🎭 <b>{brand}</b>\n\n"
    "Anonymous stranger chat.\n"
    "18+ · Be respectful · No spam."
)

SETUP_GENDER = "🎭 Pick your gender <i>(private, for matching only)</i>"
SETUP_LOOKING = "💫 Who do you want to meet?"

READY = (
    "✅ Ready · {gender} · {looking}\n\n"
    "Tap below to connect."
)

SEARCHING = "🔍 Finding someone… {pulse}"

MATCHED = "🟢 <b>Connected</b> — chat below. Media works too."

CHAT_ENDED = "Chat ended."
CHAT_PARTNER_LEFT = "Partner left."
CHAT_NEXT = "🔍 Finding next partner… {pulse}"
SEARCH_CANCELLED = "Search stopped."
PARTNER_FOUND_HINT = "🟢 Connected — chat below."
SEARCH_BLOCKED_RETRY = "🔍 Finding someone… {pulse}"
SEARCH_TIMEOUT = "No one online. Tap 🔍 to retry."

CONFIRM_END = "End this chat?"

SETTINGS = "⚙️ {gender} · {looking}"

HELP = (
    "<b>How it works</b>\n"
    "1. Set gender & preference\n"
    "2. Tap 🔍 Find Partner\n"
    "3. Chat anonymously\n"
    "4. End / Next / Report / Block anytime\n"
    "5. Share profile safely with /link"
)

FEEDBACK = "Rate this chat:"
FEEDBACK_THANKS = "Thanks!"

BANNED = "🚫 Account restricted."
NOT_IN_CHAT = ""  # silent — no spam when idle
RATE_LIMITED = "Slow down a bit."
REPORT_SENT = "Report sent. We'll review it."
REPORT_PROMPT = "Submit report?"

SPAM_BLOCKED = "Links & @usernames blocked. Use /link to share your profile."
LINK_SHARED = "Profile shared with your partner."
LINK_RECEIVED = "Your partner shared their profile:\n{link}"
LINK_NO_USERNAME = "Set a Telegram @username first, then use /link."
LINK_NOT_IN_CHAT = "You're not in a chat."

STOP_IDLE = "Nothing to stop."
STOP_SEARCH = "Search stopped."
STOP_CHAT = "Chat ended."

GENDER_LABELS = {"male": "👨 Male", "female": "👩 Female", "other": "🌈 Other"}
LOOKING_LABELS = {"male": "👨 Boys", "female": "👩 Girls", "any": "🌍 Anyone"}

PULSE_FRAMES = ("", "·", "··", "···")


def gender_label(value: str | None) -> str:
    return GENDER_LABELS.get(value or "", value or "—")


def looking_label(value: str | None) -> str:
    return LOOKING_LABELS.get(value or "", value or "—")
