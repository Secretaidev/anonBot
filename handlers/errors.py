"""Global error handler — classifies exceptions to reduce log noise.

Error tiers:
  • SILENT: Expected errors (message not modified, user blocked bot, etc.)
  • TRANSIENT: Network blips, flood control — logged at WARNING
  • BUG: Unexpected errors — logged at ERROR with full traceback
"""

import logging
import time

from telegram import Update
from telegram.error import (
    BadRequest,
    Forbidden,
    NetworkError,
    RetryAfter,
    TimedOut,
)
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)

# Suppress duplicate "something went wrong" messages to same user
_last_error_notify: dict[int, float] = {}
_NOTIFY_COOLDOWN = 30.0  # seconds


def _is_benign(exc: BaseException) -> bool:
    """Errors we expect in normal operation — don't log at ERROR level."""
    if isinstance(exc, Forbidden):
        return True  # User blocked the bot
    if isinstance(exc, TimedOut):
        return True  # Network timeout — transient
    if isinstance(exc, BadRequest):
        msg = str(exc).lower()
        if any(s in msg for s in (
            "message is not modified",
            "query is too old",
            "message to edit not found",
            "message can't be edited",
            "chat not found",
            "bot was blocked",
            "user is deactivated",
            "not enough rights",
            "have no rights",
        )):
            return True
    return False


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    exc = context.error
    if exc is None:
        return

    # ── Tier 1: Silent — expected, don't log ──
    if _is_benign(exc):
        logger.debug("benign error (suppressed): %s", exc)
        return

    # ── Tier 2: Transient — warn, don't traceback ──
    if isinstance(exc, (NetworkError, RetryAfter)):
        logger.warning("transient error: %s", exc)
        return

    # ── Tier 3: Bug — full traceback ──
    logger.exception("Unhandled exception", exc_info=exc)

    # Notify user (rate-limited to prevent spam)
    if isinstance(update, Update) and update.effective_chat:
        chat_id = update.effective_chat.id
        now = time.monotonic()
        last = _last_error_notify.get(chat_id, 0.0)
        if now - last >= _NOTIFY_COOLDOWN:
            _last_error_notify[chat_id] = now
            try:
                await context.bot.send_message(
                    chat_id,
                    "⚠️ Something went wrong. Please tap /menu to continue.",
                )
            except Exception:
                pass

        # GC stale entries periodically
        if len(_last_error_notify) > 1000:
            cutoff = now - _NOTIFY_COOLDOWN * 10
            stale = [k for k, v in _last_error_notify.items() if v < cutoff]
            for k in stale:
                del _last_error_notify[k]
