"""Lightweight spam detection — blocks links & usernames in anonymous chat."""

import re

# @username (4+ chars — skips @yes, @the)
_AT_USER = re.compile(r"@[a-zA-Z][a-zA-Z0-9_]{3,}")
# Telegram / social links
_TG_LINK = re.compile(
    r"(t\.me/|telegram\.me/|telegram\.dog/|wa\.me/|whatsapp\.com/|instagram\.com/|snapchat\.com/)",
    re.IGNORECASE,
)
_HTTP = re.compile(r"https?://", re.IGNORECASE)
# Raw phone numbers (10+ digits)
_PHONE = re.compile(r"(?<!\d)\+?\d{10,14}(?!\d)")


def contains_spam(text: str | None) -> bool:
    """True if message text looks like self-promo / contact sharing."""
    if not text or not text.strip():
        return False
    t = text.strip()
    if _HTTP.search(t):
        return True
    if _TG_LINK.search(t):
        return True
    if _AT_USER.search(t):
        return True
    if _PHONE.search(t):
        return True
    return False
