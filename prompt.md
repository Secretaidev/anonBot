# AnoyBot — Master AI Prompt

Use this when extending, fixing, or rebuilding this Telegram anonymous chat bot. Target: **world-class production bot** — zero errors, minimal server load, premium UX, MongoDB persistence.

---

## Project Identity

**AnoyBot** — Telegram anonymous stranger-chat bot. Users pick gender + preference, get matched instantly, chat anonymously (all media), every action logged to a private admin channel with full metadata.

**Stack:** Python 3.11+, `python-telegram-bot` ≥22.7 (async), `motor` + `pymongo`, `python-dotenv`.

**Never** add user-facing text mentioning "updates", "versions", or "changelog".

---

## Environment (.env)

```
BOT_TOKEN=
LOG_CHANNEL_ID=          # negative channel id, bot must be admin
ADMIN_IDS=               # comma-separated Telegram user ids
MONGODB_URL=             # mongodb://localhost:27017 or Atlas URI
MONGODB_DB_NAME=anoybot
MATCH_TIMEOUT_SECONDS=300
MAX_MESSAGE_LENGTH=4096
RATE_LIMIT_PER_MINUTE=25
BRAND_NAME=AnoyBot
AUTO_BAN_REPORTS=3
```

---

## Architecture

```
bot.py                  → entry, job queue, handler registration
config.py               → env Config dataclass
database.py             → MongoDB via motor (users, sessions, logs, blocks, reports)
services/matcher.py     → in-memory match queue, bucket hints, timeout sweep
services/logger.py      → HTML logs to private channel + MongoDB message_logs
services/jobs.py        → search pulse animation, startup notify, bot commands
keyboards/buttons.py    → ALL inline keyboards (styled: blue/green/red)
utils/texts.py          → ALL user-facing strings
utils/helpers.py        → safe_send, safe_edit, search card tracking
utils/ratelimit.py      → per-user sliding window limiter
handlers/start.py       → /start, /menu
handlers/callbacks.py   → all button callbacks + star ratings
handlers/chat.py        → message relay, /report
handlers/session.py     → match notify, end chat, feedback
handlers/stop.py        → /stop
handlers/admin.py       → /stats /user /ban /unban /broadcast
handlers/errors.py      → global error handler
```

---

## MongoDB Collections

**users** — `user_id` (unique), profile, gender, looking_for, state, partner_id, session_id, totals, accepted_rules, is_banned, ban_reason, reports_received, rating_sum, rating_count, timestamps

**sessions** — session_id (unique), user_a_id, user_b_id, started_at, ended_at, message_count, rating_a, rating_b

**message_logs** — session_id, sender_id, receiver_id, message_type, content_preview, created_at

**blocks** — user_id + blocked_id (compound unique)

**reports** — reporter_id, reported_id, session_id, reason, created_at

Indexes created on connect in `Database._ensure_indexes()`.

---

## Button UI (mandatory)

| Style | Color | Use |
|-------|-------|-----|
| `S.PRIMARY` | Blue | Find Partner, Next, gender/preference |
| `S.SUCCESS` | Green | Accept rules, Stats, safe confirms |
| `S.DANGER` | Red | End, Report, Block, Cancel search |

```python
from telegram.constants import KeyboardButtonStyle as S
InlineKeyboardButton("🔍 Find Partner", callback_data="...", style=S.PRIMARY)
```

---

## User Flow

1. `/start` → Welcome → Accept Rules (green)
2. Gender (blue) → Preference (blue/green)
3. **Find Partner** (blue) → live search screen with pulse animation
4. Matched → chat: End (red), Next (blue), Report/Block (red)
5. After chat → optional star rating (1–5)
6. `/menu` main menu · `/stop` end/cancel · `/report reason`

---

## Matchmaking

- States: `idle` | `searching` | `chatting`
- Bidirectional gender compatibility (`any` matches all)
- In-memory queue; match callback **outside** lock
- Block list checked before connect
- Search timeout via job queue (60s sweep)
- Search pulse job updates waiting screen every 12s
- Restart clears stale states via `reset_active_sessions()`

---

## Logging (admin channel)

HTML formatted: event, UTC time, user ID, name, @username, profile link, language, premium, session ID, partner info, message type + content preview.

Persist message relays to `message_logs` collection.

Startup posts online notice to log channel.

---

## Performance

- Async everywhere (motor, python-telegram-bot)
- MongoDB connection pool (max 20)
- Rate limit chat messages (default 25/min)
- `safe_send` with RetryAfter backoff
- Global error handler
- Indexed MongoDB queries
- Job queue: timeout sweep (60s), search pulse (12s)
- In-memory matcher — no DB hit per match scan

---

## Admin Commands (ADMIN_IDS only)

| Command | Action |
|---------|--------|
| `/stats` | Live dashboard |
| `/user <id>` | Full user profile from DB |
| `/ban <id> [reason]` | Ban + notify |
| `/unban <id>` | Remove ban |
| `/broadcast <msg>` | Message all non-banned users |

Auto-ban when `reports_received >= AUTO_BAN_REPORTS`.

---

## Code Rules

1. All UI strings → `utils/texts.py`
2. All keyboards → `keyboards/buttons.py`
3. All DB access → `database.py` methods (never raw motor in handlers)
4. Secrets only in `.env`
5. Handle: partner left, bot blocked, flood wait, duplicate callbacks
6. Message relay via `msg.copy(chat_id=partner_id)`
7. Rating callbacks use `pending_feedback` dict — never embed UUID in callback_data

---

## Run

```bash
pip install -r requirements.txt
# Start MongoDB locally OR set MONGODB_URL to Atlas cluster
python bot.py
```

**MongoDB Atlas:** create free cluster → Database Access user → Network Access 0.0.0.0/0 → copy connection string → set `MONGODB_URL=mongodb+srv://user:pass@cluster/anoybot`

Bot must be **admin** in log channel.

---

## Quality Bar

- Instant `query.answer()` on every button
- No tracebacks to users
- Separator lines: `━━━━━━━━━━━━━━━━━━━━`
- Context-aware keyboards (idle / searching / chatting)
- Professional admin forensics in log channel
- World-class anonymous chat — complete, stable, scalable on MongoDB
