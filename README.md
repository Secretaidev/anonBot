# AnoyBot

World-class anonymous Telegram chat bot — MongoDB, styled buttons, full admin panel.

## Setup

1. Bot via [@BotFather](https://t.me/BotFather)
2. Private log channel → bot as **admin**
3. MongoDB running locally or [MongoDB Atlas](https://www.mongodb.com/atlas) free tier
4. Copy `.env.example` → `.env` and fill values
5. `pip install -r requirements.txt`
6. `python bot.py`

## .env

| Key | Description |
|-----|-------------|
| `BOT_TOKEN` | From BotFather |
| `LOG_CHANNEL_ID` | e.g. `-1004390107750` |
| `ADMIN_IDS` | Your Telegram user id |
| `MONGODB_URL` | `mongodb://localhost:27017` or Atlas URI |
| `TELEGRAM_API_BASE_URL` | Optional custom Bot API base URL |
| `TELEGRAM_API_FILE_URL` | Optional custom file API base URL |
| `MONGODB_DB_NAME` | Database name (default: `anoybot`) |

## Commands

**Users:** `/start` `/menu` `/stop` `/report`

**Admin:** `/stats` `/user <id>` `/ban` `/unban` `/broadcast`

## Features

- Styled buttons: blue / green / red
- Gender-based anonymous matching
- All media relay
- Star ratings after chat
- Block, report, auto-ban
- Full message logging to private channel
- MongoDB persistence with indexes
- Live search pulse + rate limiting

See `prompt.md` for full AI development guide.
