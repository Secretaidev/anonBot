"""Premium UI copy — single source for every user-facing string."""

BRAND = "AnoyBot"

WELCOME = (
    "🎭 <b>Welcome to {brand}</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n\n"
    "The most private way to meet strangers on Telegram.\n\n"
    "🔒 <b>100% Anonymous</b> — partners never see your profile\n"
    "⚡ <b>Instant Matching</b> — connect in seconds\n"
    "🛡 <b>Safe & Monitored</b> — every chat is protected\n"
    "💎 <b>Premium UI</b> — colorful buttons, zero friction\n\n"
    "📜 <b>Rules:</b> Be respectful · No spam · 18+ only · Report abuse instantly"
)

RULES = (
    "📜 <b>Community Rules</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n\n"
    "1. Be respectful — no harassment or hate\n"
    "2. No spam, ads, or illegal content\n"
    "3. Never share personal info unless you choose to\n"
    "4. Report bad behavior via 🚨 Report button\n"
    "5. Must be 18+ to use this bot\n\n"
    "Violations result in a permanent ban."
)

SETUP_GENDER = (
    "🎭 <b>Step 1 — Your Gender</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n\n"
    "Used only for matching. Your partner <b>never</b> sees this."
)

SETUP_LOOKING = (
    "💫 <b>Step 2 — Chat Preference</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n\n"
    "Who would you like to be matched with?"
)

READY = (
    "✅ <b>Ready to Connect</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n\n"
    "🎭 Gender: {gender}\n"
    "💫 Looking for: {looking}\n"
    "📡 Live queue: <b>{online}</b>\n\n"
    "Tap the blue button when you're ready."
)

SEARCHING = (
    "🔍 <b>Finding Your Partner…</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n\n"
    "{pulse} Scanning live queue…\n"
    "👥 Waiting: <b>{online}</b>\n"
    "💬 Active chats: <b>{chatting}</b>\n\n"
    "Hang tight — connection is instant when someone joins."
)

MATCHED = (
    "🎉 <b>Partner Connected!</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n\n"
    "You're now chatting <b>100% anonymously</b>.\n"
    "Say hi 👋 — text, photos, voice, stickers & video all work.\n\n"
    "🔴 End · ⏭ Next · 🚨 Report · 🚫 Block"
)

CHAT_ENDED = "🔴 Chat ended. Tap below to find someone new."
CHAT_PARTNER_LEFT = "👋 Your partner disconnected."
CHAT_NEXT = "⏭ Finding your next partner…"
SEARCH_CANCELLED = "🛑 Search cancelled."
PARTNER_FOUND_HINT = "🎉 Connected! Check the message above."
SEARCH_BLOCKED_RETRY = (
    "🔄 Previous match was blocked.\n"
    "Searching again for a new partner…"
)
SEARCH_TIMEOUT = "⏱ No partner found in time. Tap 🔍 Find Partner to try again."

CONFIRM_END = (
    "⚠️ <b>End This Chat?</b>\n\n"
    "Your partner will be notified immediately."
)

SETTINGS = (
    "⚙️ <b>Settings</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n\n"
    "🎭 Gender: {gender}\n"
    "💫 Preference: {looking}"
)

STATS = (
    "📊 <b>Live Dashboard</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n\n"
    "👥 Total users: <b>{users}</b>\n"
    "🔍 Searching: <b>{searching}</b>\n"
    "💬 In chat: <b>{chatting}</b>\n"
    "🤝 Sessions: <b>{sessions}</b>\n"
    "📡 Queue: <b>{queue}</b>\n"
    "🚫 Banned: <b>{banned}</b>\n\n"
    "<b>Your activity</b>\n"
    "Sessions: {my_sessions} · Messages: {my_messages}"
)

HELP = (
    "❓ <b>How It Works</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n\n"
    "1️⃣ Set gender & preference in ⚙️ Settings\n"
    "2️⃣ Tap <b>🔍 Find Partner</b> (blue)\n"
    "3️⃣ Chat anonymously — all media works\n"
    "4️⃣ <b>🔴 End</b> or <b>⏭ Next</b> anytime\n"
    "5️⃣ <b>🚨 Report</b> or <b>🚫 Block</b> if needed\n"
    "6️⃣ /menu — open main menu anytime\n"
    "7️⃣ /stop — end chat or cancel search\n\n"
    "🔒 Hidden identity · ⚡ Instant relay · 🛡 Monitored"
)

FEEDBACK = (
    "⭐ <b>Rate this chat</b>\n\n"
    "How was your partner? (optional — helps us improve matching)"
)

FEEDBACK_THANKS = "⭐ Thanks for your feedback!"

BANNED = "🚫 Your access has been restricted. Contact support if this is a mistake."
NOT_IN_CHAT = "💡 Find a partner first — tap the blue button below."
RATE_LIMITED = "⏳ Slow down — you're sending messages too fast."
REPORT_SENT = (
    "🚨 <b>Report submitted.</b>\n\n"
    "Our team will review it. If you feel unsafe, end the chat now."
)
REPORT_PROMPT = "Tap below to submit a report. You can also use /report reason here."

STOP_IDLE = "💡 You're not in a chat or search. Use /menu."
STOP_SEARCH = "🛑 Search stopped."
STOP_CHAT = "🔴 Chat ended."

GENDER_LABELS = {"male": "👨 Male", "female": "👩 Female", "other": "🌈 Other"}
LOOKING_LABELS = {"male": "👨 Boys", "female": "👩 Girls", "any": "🌍 Anyone"}

PULSE_FRAMES = ("⏳", "🔎", "📡", "✨")


def gender_label(value: str | None) -> str:
    return GENDER_LABELS.get(value or "", value or "—")


def looking_label(value: str | None) -> str:
    return LOOKING_LABELS.get(value or "", value or "—")
