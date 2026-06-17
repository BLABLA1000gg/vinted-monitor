# Vinted Monitor

Zero-delay Vinted listing monitor with Discord notifications.

Polls the Vinted JSON API continuously and sends a Discord embed whenever a new listing appears or a price drops.

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env
# edit .env with your URLs and webhook
```

## Run

```bash
# continuous monitoring
python vinted_monitor.py

# single scan (for testing)
python vinted_monitor.py --once
```

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `EBAY_URL` | required | Vinted catalog URL (pipe-separate multiple) |
| `DISCORD_WEBHOOK_URL` | — | Discord webhook for notifications |
| `VINTED_POLL_DELAY` | `3` | Seconds between polls (0 = back-to-back) |
| `NOTIFY_EXISTING` | `false` | Notify on listings seen at startup |
| `NOTIFY_PRICE_INCREASES` | `false` | Notify on price increases |
| `INCLUDE_KEYWORDS` | — | Comma-separated keyword filter |
| `EXCLUDE_KEYWORDS` | — | Comma-separated exclusion list |
| `MIN_PRICE` / `MAX_PRICE` | — | Price range filter |
| `CURRENCY` | — | e.g. `EUR` |
| `DATABASE_PATH` | `vinted_monitor.db` | SQLite path |
| `LOG_LEVEL` | `INFO` | Python logging level |
