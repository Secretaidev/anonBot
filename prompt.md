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
MATCH_WIDEN_SECONDS=90
SEARCH_PULSE_SECONDS=25
STATS_CACHE_SECONDS=30
USER_CACHE_SECONDS=8
MAX_MESSAGE_LENGTH=4096
RATE_LIMIT_PER_MINUTE=25
BRAND_NAME=AnoyBot
AUTO_BAN_REPORTS=3
LOG_CHAT_MESSAGES=true
BROADCAST_CONCURRENCY=20
FLOOD_NOTIFY_COOLDOWN=30
```

---

## Architecture

```
bot.py                  → entry, job queue, handler registration, graceful shutdown
config.py               → env Config dataclass (all fields populated, no crashes)
database.py             → MongoDB via motor — compound indexes, $facet stats, TTL logs,
                          parallel writes, cache GC, batch user fetch
services/matcher.py     → in-memory match queue, bucket hints, timeout sweep
                          DB reads OUTSIDE lock, match callback outside lock
services/logger.py      → HTML logs to channel + MongoDB persistence
                          log_to_channel_bg() for fire-and-forget on hot paths
                          Message length truncation (4000 char safety)
services/relay.py       → 3-retry copy_to_partner with RetryAfter, Forbidden handling
services/jobs.py        → search pulse with batch $in user fetch (N→1 DB calls)
services/stats_cache.py → TTL cache with jitter + stale-while-revalidate
keyboards/buttons.py    → ALL inline keyboards (styled: blue/green/red)
utils/texts.py          → ALL user-facing strings
utils/helpers.py        → safe_send, safe_edit, search card tracking
                          is_banned() uses cached reads (no fresh hit per msg)
                          is_valid_chat_session() cached on relay, fresh on mutations
utils/ratelimit.py      → deque-based sliding window, periodic GC, zero-lock sync
utils/mongo.py          → normalize MongoDB connection URL
handlers/start.py       → /start, /menu, /help
handlers/callbacks.py   → all button callbacks + star ratings (null-safe)
handlers/chat.py        → message relay + typing indicator forwarding
                          panel input interception, fire-and-forget logging
handlers/session.py     → match notify (parallel), end chat (parallel resets)
handlers/stop.py        → /stop
handlers/admin.py       → /stats /user /ban /unban /broadcast (permission-gated)
handlers/panel.py       → Owner & Admin in-bot panel (/panel + callbacks)
                          Select All permissions, admin names, detailed queue view
handlers/errors.py      → 3-tier error classification (silent/transient/bug)
```

---

## Owner & Admin Panel System

### Roles
- **Owner** (ADMIN_IDS in .env): Full access to everything + can manage admins
- **Admin** (added via panel): Permission-gated access, managed by owners

### Permissions (granular, per-admin)
| Key | Label | Grants |
|-----|-------|--------|
| `stats` | 📊 Stats | View live dashboard |
| `user_lookup` | 👤 Lookup | Look up user profiles |
| `ban` | 🔨 Ban | Ban users |
| `unban` | 🔓 Unban | Unban users |
| `broadcast` | 📢 Broadcast | Send broadcasts |
| `view_reports` | 📋 Reports | View abuse reports |
| `manage_search` | 🔍 Queue | View search queue & active chats |

### Panel UX Flow
1. `/panel` → Owner sees full panel, Admin sees permission-gated panel
2. Inline button navigation for all actions
3. Text input mode for user IDs and broadcast messages (via `user_data["panel_await"]`)
4. Permission editor with toggle buttons (✅/❌)
5. Panel input intercepted in `chat.py` before message relay

---

## MongoDB Collections

**users** — `user_id` (unique), profile, gender, looking_for, state, partner_id, session_id, totals, accepted_rules, is_banned, ban_reason, reports_received, rating_sum, rating_count, timestamps

**sessions** — session_id (unique), user_a_id, user_b_id, started_at, ended_at, message_count, rating_a, rating_b

**message_logs** — session_id, sender_id, receiver_id, message_type, content_preview, created_at (**TTL: auto-expire after 30 days**)

**blocks** — user_id + blocked_id (compound unique), blocked_id indexed for reverse lookup

**reports** — reporter_id, reported_id, session_id, reason, created_at (indexed for sorting)

**admins** — user_id (unique), permissions (list of permission keys), added_by, created_at, updated_at

### Indexes (created on connect)

| Collection | Index | Purpose |
|------------|-------|---------|
| users | `user_id` (unique) | Primary lookup |
| users | `state` | State queries |
| users | `is_banned` | Ban checks |
| users | `partner_id` | Partner lookup |
| users | `(state, is_banned, gender, looking_for)` | Match compound query |
| users | `(state, is_banned, updated_at)` | Match sort query |
| sessions | `session_id` (unique) | Session lookup |
| message_logs | `created_at` (TTL 30d) | Auto-expire |
| blocks | `(user_id, blocked_id)` (unique) | Block lookup |
| blocks | `blocked_id` | Reverse block check |

---

## Performance Architecture

### Hot Path (every message relay)
1. `is_banned()` → **cached** read (no DB hit if cache valid)
2. `is_valid_chat_session()` → **cached** read (both user + partner)
3. `RateLimiter.allow()` → **synchronous** (no await, deque-based)
4. `copy_to_partner()` → 3-retry with RetryAfter backoff
5. Channel log → **fire-and-forget** via `log_to_channel_bg()`
6. Message persistence → **fire-and-forget** with error callback

### Database Optimization
- **$facet aggregation**: `get_stats()` does 1 pipeline instead of 6 `count_documents()`
- **`estimated_document_count()`** for sessions/messages (O(1) vs O(N))
- **Parallel writes**: `asyncio.gather()` for session creation, rating saves, message logging
- **Batch fetch**: `get_users_by_ids()` for search pulse (1 query for N users)
- **TTL index**: message_logs auto-expire after 30 days
- **Compound indexes**: match queries use covered index scans
- **Connection pool**: 25 max, 2 min, zstd compression, retry reads+writes

### Memory Management
- User cache: periodic GC every 120s prunes expired entries
- Rate limiter: GC every 500 calls prunes inactive users
- Search cards: stale entries cleaned on every pulse tick
- Error handler: notification dedup map cleaned at 1000 entries

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
- In-memory queue with bucket hints for O(1) candidate lookup
- DB reads (get_user, get_block_set) happen **OUTSIDE** the asyncio lock
- Match callback fires **OUTSIDE** the lock to prevent deadlocks
- Block list checked bidirectionally before connect
- Search timeout via job queue (90s sweep interval)
- Search pulse job updates waiting screen every 25s (batch $in query)
- Restart rehydrates search queue from MongoDB
- Restart clears stale chatting states via `reset_chatting_sessions()`

---

## Error Handling

Three-tier classification prevents log floods:

| Tier | Level | Examples |
|------|-------|---------|
| **Silent** | DEBUG | "message is not modified", Forbidden (user blocked bot), TimedOut, "query is too old" |
| **Transient** | WARNING | NetworkError, RetryAfter |
| **Bug** | ERROR + traceback | Everything else |

User notification rate-limited (30s cooldown per chat).

---

## Logging (admin channel)

HTML formatted: event, UTC time, user ID, name, @username, profile link, language, premium, session ID, partner info, message type + content preview.

- **Hot path**: `log_to_channel_bg()` (fire-and-forget, never blocks relay)
- **Critical path**: `await log_to_channel()` (match connect, reports, bans)
- **Safety**: total message truncated at 4000 chars
- **Error callbacks**: fire-and-forget tasks have `add_done_callback` for exception logging

---

## Admin Commands (ADMIN_IDS only)

| Command | Action |
|---------|--------|
| `/stats` | Live dashboard ($facet aggregation) |
| `/user <id>` | Full user profile from DB |
| `/ban <id> [reason]` | Ban + notify + leave matcher |
| `/unban <id>` | Remove ban |
| `/broadcast <msg>` | Concurrent sends (Semaphore), progress reports |

Auto-ban when `reports_received >= AUTO_BAN_REPORTS`.

---

## Code Rules

1. All UI strings → `utils/texts.py`
2. All keyboards → `keyboards/buttons.py`
3. All DB access → `database.py` methods (never raw motor in handlers)
4. Secrets only in `.env`
5. Handle: partner left, bot blocked, flood wait, duplicate callbacks
6. Message relay via `services/relay.py` → `copy_to_partner()` (never raw `msg.copy()`)
7. Rating callbacks use `pending_feedback` dict — never embed UUID in callback_data
8. Hot path DB reads use **cached** (`fresh=False`); state mutations use `fresh=True`
9. Fire-and-forget tasks MUST have `add_done_callback` for error logging
10. Rate limiter is **synchronous** — never `await` it
11. Never hold asyncio lock during DB calls (matcher pattern)
12. Channel logging on hot path uses `log_to_channel_bg()` (fire-and-forget)

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
- No tracebacks to users (3-tier error handler)
- Separator lines: `━━━━━━━━━━━━━━━━━━━━`
- Context-aware keyboards (idle / searching / chatting)
- Professional admin forensics in log channel
- Graceful shutdown with log channel notification
- Zero memory leaks (cache GC, rate limiter GC, error map GC)
- World-class anonymous chat — complete, stable, scalable on MongoDB
