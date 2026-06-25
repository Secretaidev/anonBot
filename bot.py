"""AnoyBot — entry point, job queue, handler registration.

Production-grade:
  • Concurrent updates enabled for high throughput
  • Tuned HTTP timeouts for Telegram API
  • Graceful shutdown with user notification
  • Bootstrap retries for transient network failures
  • Rate limiter cleanup on shutdown
"""

import logging

from telegram.error import NetworkError, TimedOut
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
)

from config import Config, load_config
from database import Database
from handlers.admin import admin_ban, admin_broadcast, admin_stats, admin_unban, admin_user
from handlers.callbacks import callback_handler, next_command
from handlers.panel import panel_callback, panel_command
from handlers.chat import link_command, relay_message, report_command
from handlers.errors import error_handler
from handlers.session import notify_matched
from handlers.start import help_command, menu_command, start_command
from handlers.stop import stop_command
from keyboards.buttons import main_menu_keyboard
from services.jobs import notify_startup, search_pulse_job, setup_bot_commands
from services.matcher import Matcher, STATE_IDLE
from services.message_buffer import MessageBuffer
from services.session_registry import SessionRegistry
from services.stats_cache import StatsCache
from utils.status_card import untrack_status_card, update_status_card
from utils.ratelimit import RateLimiter
from utils.texts import CHAT_PARTNER_LEFT, SEARCH_TIMEOUT

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("pymongo").setLevel(logging.WARNING)
logging.getLogger("motor").setLevel(logging.WARNING)
logger = logging.getLogger("anoybot")


async def post_init(application: Application) -> None:
    config = application.bot_data["config"]
    db: Database = application.bot_data["db"]
    matcher: Matcher = application.bot_data["matcher"]

    async def on_match(user_a: int, user_b: int, session_id: str) -> None:
        await notify_matched(application, user_a, user_b, session_id)

    async def on_timeout(user_id: int) -> None:
        await db.set_state(user_id, STATE_IDLE)
        untrack_status_card(application, user_id)
        stats_cache = application.bot_data.get("stats_cache")
        if stats_cache:
            stats_cache.invalidate()
        from keyboards.buttons import main_menu_keyboard
        from utils.texts import SEARCH_TIMEOUT

        await update_status_card(
            application,
            user_id,
            SEARCH_TIMEOUT,
            reply_markup=main_menu_keyboard(),
        )

    matcher.set_match_callback(on_match)
    matcher.set_timeout_callback(on_timeout)

    await db.connect()

    orphaned = await db.reset_chatting_sessions()
    if orphaned:
        logger.info("Reset %s orphaned chat session(s)", len(orphaned))
        for uid in orphaned:
            await update_status_card(
                application,
                uid,
                CHAT_PARTNER_LEFT,
                reply_markup=main_menu_keyboard(),
            )

    restored = await matcher.rehydrate_from_db()
    if restored:
        stats_cache = application.bot_data.get("stats_cache")
        if stats_cache:
            stats_cache.invalidate()

    application.bot_data["status_cards"] = {}
    application.bot_data["pulse_idx"] = 0
    application.bot_data["pending_feedback"] = {}

    application.job_queue.run_repeating(
        _timeout_job, interval=90, first=45, name="match_timeout_sweep"
    )
    application.job_queue.run_repeating(
        search_pulse_job,
        interval=config.search_pulse_seconds,
        first=config.search_pulse_seconds,
        name="search_pulse",
    )
    application.job_queue.run_repeating(
        _message_flush_job,
        interval=config.message_log_flush_seconds,
        first=config.message_log_flush_seconds,
        name="message_log_flush",
    )

    application.bot_data["session_registry"].clear()

    await setup_bot_commands(application)
    await notify_startup(application)

    me = await application.bot.get_me()
    logger.info("Bot online: @%s | queue=%s", me.username, await matcher.queue_size())


async def post_shutdown(application: Application) -> None:
    """Graceful shutdown — flush pending logs and close DB."""
    db: Database = application.bot_data["db"]
    config: Config = application.bot_data["config"]
    buffer: MessageBuffer | None = application.bot_data.get("message_buffer")
    if buffer:
        await buffer.flush()

    # Notify log channel
    try:
        me = await application.bot.get_me()
        await application.bot.send_message(
            config.log_channel_id,
            f"🔴 <b>{config.brand_name} Shutting Down</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"🤖 @{me.username}",
            parse_mode="HTML",
        )
    except Exception:
        pass

    await db.close()
    logger.info("Bot shutdown complete")


async def _timeout_job(context) -> None:
    matcher: Matcher = context.application.bot_data["matcher"]
    expired = await matcher.sweep_timeouts()
    if expired:
        logger.info("Timed out %s search(es)", len(expired))


async def _message_flush_job(context) -> None:
    buffer: MessageBuffer | None = context.application.bot_data.get("message_buffer")
    if buffer:
        await buffer.flush()


def _build_application(config) -> Application:
    db = Database(
        config.mongodb_url,
        config.mongodb_db_name,
        user_cache_seconds=float(config.user_cache_seconds),
        upsert_cooldown_seconds=float(config.upsert_cooldown_seconds),
    )
    matcher = Matcher(
        db=db,
        timeout_seconds=float(config.match_timeout_seconds),
        widen_after_seconds=float(config.match_widen_seconds),
    )
    rate_limiter = RateLimiter(max_events=config.rate_limit_per_minute)
    stats_cache = StatsCache(ttl_seconds=float(config.stats_cache_seconds))
    session_registry = SessionRegistry()
    message_buffer = MessageBuffer(db, max_batch=config.message_log_batch_size)

    builder = (
        Application.builder()
        .token(config.bot_token)
        .connect_timeout(15.0)
        .read_timeout(15.0)
        .write_timeout(15.0)
        .pool_timeout(10.0)
        .get_updates_connect_timeout(15.0)
        .get_updates_read_timeout(42.0)
        .get_updates_write_timeout(15.0)
        .concurrent_updates(True)
    )
    if config.telegram_api_base_url:
        builder = builder.base_url(config.telegram_api_base_url)
    if config.telegram_api_file_url:
        builder = builder.base_file_url(config.telegram_api_file_url)

    app = builder.post_init(post_init).post_shutdown(post_shutdown).build()

    app.bot_data["config"] = config
    app.bot_data["db"] = db
    app.bot_data["matcher"] = matcher
    app.bot_data["rate_limiter"] = rate_limiter
    app.bot_data["stats_cache"] = stats_cache
    app.bot_data["session_registry"] = session_registry
    app.bot_data["message_buffer"] = message_buffer

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("menu", menu_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("next", next_command))
    app.add_handler(CommandHandler("stop", stop_command))
    app.add_handler(CommandHandler("report", report_command))
    app.add_handler(CommandHandler("link", link_command))
    app.add_handler(CommandHandler("stats", admin_stats))
    app.add_handler(CommandHandler("user", admin_user))
    app.add_handler(CommandHandler("ban", admin_ban))
    app.add_handler(CommandHandler("unban", admin_unban))
    app.add_handler(CommandHandler("broadcast", admin_broadcast))
    app.add_handler(CommandHandler("panel", panel_command))
    # Panel callbacks (p: prefix) must be registered BEFORE general callback handler
    app.add_handler(CallbackQueryHandler(panel_callback, pattern=r"^p:"))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(
        MessageHandler(
            filters.ALL & ~filters.COMMAND & ~filters.StatusUpdate.ALL,
            relay_message,
        )
    )
    app.add_error_handler(error_handler)
    return app


def main() -> None:
    try:
        config = load_config()
    except ValueError as exc:
        logger.error("Config error: %s", exc)
        raise SystemExit(1) from exc

    app = _build_application(config)

    try:
        app.run_polling(
            drop_pending_updates=True,
            allowed_updates=["message", "callback_query"],
            close_loop=False,
            bootstrap_retries=5,
        )
    except (NetworkError, TimedOut, OSError) as exc:
        raise SystemExit(
            "Failed to connect to Telegram. Check internet, DNS, VPN, or TELEGRAM_API_BASE_URL in .env. "
            f"Error: {exc}"
        ) from exc


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as exc:
        logger.error("%s", exc)
        raise SystemExit(1) from exc
