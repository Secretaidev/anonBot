# Railway Deploy

1. Push repo to GitHub
2. [railway.app](https://railway.app) → New Project → Deploy from GitHub
3. Add variables (same as `.env`):

```
BOT_TOKEN=
LOG_CHANNEL_ID=
ADMIN_IDS=
MONGODB_URL=          # Atlas URI or Railway MongoDB plugin URI
MONGODB_DB_NAME=anoybot
BRAND_NAME=AnoyBot
```

4. Railway auto-runs `python bot.py` via `railway.toml`

## MongoDB on Railway

Option A — **MongoDB Atlas** (free): whitelist `0.0.0.0/0`, paste `mongodb+srv://...` in `MONGODB_URL`

Option B — **Railway MongoDB plugin**: add MongoDB service → copy `MONGO_URL` into `MONGODB_URL`

## Local

```bash
pip install -r requirements.txt
python bot.py
```

Use `mongodb://127.0.0.1:27017/anoybot` if MongoDB is installed locally.
