import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Config:
    bot_token: str
    log_channel_id: int
    admin_ids: frozenset[int]
    mongodb_url: str
    mongodb_db_name: str
    telegram_api_base_url: str | None
    telegram_api_file_url: str | None
    match_timeout_seconds: int
    max_message_length: int
    rate_limit_per_minute: int
    brand_name: str
    auto_ban_reports: int


def load_config() -> Config:
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token:
        raise ValueError("BOT_TOKEN is required in .env")

    channel_raw = os.getenv("LOG_CHANNEL_ID", "").strip()
    if not channel_raw:
        raise ValueError("LOG_CHANNEL_ID is required in .env")

    mongo_url = os.getenv("MONGODB_URL", "").strip()
    if not mongo_url:
        raise ValueError("MONGODB_URL is required in .env")

    admin_raw = os.getenv("ADMIN_IDS", "").strip()
    admin_ids = frozenset(int(x.strip()) for x in admin_raw.split(",") if x.strip())

    return Config(
        bot_token=token,
        log_channel_id=int(channel_raw),
        admin_ids=admin_ids,
        mongodb_url=mongo_url,
        mongodb_db_name=os.getenv("MONGODB_DB_NAME", "anoybot"),
        telegram_api_base_url=os.getenv("TELEGRAM_API_BASE_URL", "").strip() or None,
        telegram_api_file_url=os.getenv("TELEGRAM_API_FILE_URL", "").strip() or None,
        match_timeout_seconds=int(os.getenv("MATCH_TIMEOUT_SECONDS", "300")),
        max_message_length=int(os.getenv("MAX_MESSAGE_LENGTH", "4096")),
        rate_limit_per_minute=int(os.getenv("RATE_LIMIT_PER_MINUTE", "25")),
        brand_name=os.getenv("BRAND_NAME", "AnoyBot"),
        auto_ban_reports=int(os.getenv("AUTO_BAN_REPORTS", "3")),
    )
