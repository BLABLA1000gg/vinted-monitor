"""Zero-delay Vinted monitor.

Polls the Vinted JSON API as fast as it responds (no fixed sleep between
scans). Set VINTED_POLL_DELAY to a float (seconds) to add a courtesy pause
between requests; defaults to 3 s to stay well under Vinted's rate limit.
Set it to 0 for truly back-to-back requests (risks 429s).

Environment variables (shared with the main monitor where applicable):
  EBAY_URL / EBAY_URLS      — pipe-separated Vinted catalog URLs
  DISCORD_WEBHOOK_URL       — Discord webhook for notifications
  DATABASE_PATH             — SQLite path (default: ebay_monitor.db)
  VINTED_POLL_DELAY         — seconds between polls (default: 3, min: 0)
  NOTIFY_EXISTING           — notify on listings already seen at startup
  NOTIFY_PRICE_INCREASES    — notify on price increases (default: false)
  INCLUDE_KEYWORDS          — comma-separated keyword filter
  EXCLUDE_KEYWORDS          — comma-separated keyword exclusion list
  MIN_PRICE / MAX_PRICE     — price range filter
  CURRENCY                  — e.g. EUR
  LOG_LEVEL                 — Python logging level (default: INFO)
"""
from __future__ import annotations

import logging
import os
import time
from decimal import Decimal
from pathlib import Path

import requests

from filters import ListingFilter, parse_csv_words
from marketplaces import fetch_vinted_listings_api
from monitor import (
    DEFAULT_TIMEOUT_SECONDS,
    bool_env,
    decimal_env,
    event_should_notify,
    send_to_discord,
    validate_url,
)
from storage import MonitorStore

LOGGER = logging.getLogger(__name__)
DEFAULT_POLL_DELAY = 3.0


def run(once: bool = False) -> None:
    raw_urls = os.environ.get("EBAY_URLS") or os.environ.get("EBAY_URL")
    if not raw_urls:
        raise ValueError("Set EBAY_URL or EBAY_URLS to one or more Vinted catalog URLs")

    vinted_urls = [
        validate_url("EBAY_URL", u.strip(), ("vinted.de",))
        for u in raw_urls.split("|")
        if u.strip()
    ]
    if not vinted_urls:
        raise ValueError("No valid vinted.de URLs found in EBAY_URL / EBAY_URLS")

    webhook = os.getenv("DISCORD_WEBHOOK_URL")
    if webhook:
        webhook = validate_url(
            "DISCORD_WEBHOOK_URL", webhook, ("discord.com", "discordapp.com")
        )

    poll_delay = float(os.getenv("VINTED_POLL_DELAY", str(DEFAULT_POLL_DELAY)))
    if poll_delay < 0:
        poll_delay = 0.0

    currency = os.getenv("CURRENCY")
    listing_filter = ListingFilter(
        include_keywords=parse_csv_words(os.getenv("INCLUDE_KEYWORDS")),
        exclude_keywords=parse_csv_words(os.getenv("EXCLUDE_KEYWORDS")),
        min_price=decimal_env("MIN_PRICE"),
        max_price=decimal_env("MAX_PRICE"),
        currency=currency.upper() if currency else None,
    )

    db_path = Path(os.getenv("DATABASE_PATH", "ebay_monitor.db"))
    notify_existing = bool_env("NOTIFY_EXISTING")
    notify_price_increases = bool_env("NOTIFY_PRICE_INCREASES")

    LOGGER.info(
        "Vinted zero-delay monitor started | urls=%d poll_delay=%.1fs",
        len(vinted_urls),
        poll_delay,
    )

    initial_scan = True
    with requests.Session() as session, MonitorStore(db_path) as store:
        while True:
            scan_start = time.monotonic()
            try:
                all_listings = []
                for url in vinted_urls:
                    try:
                        fetched = fetch_vinted_listings_api(
                            url, timeout=DEFAULT_TIMEOUT_SECONDS
                        )
                        filtered = [l for l in fetched if listing_filter.matches(l)]
                        all_listings.extend(filtered)
                    except requests.RequestException as err:
                        LOGGER.warning("Vinted fetch failed for %s: %s", url, err)

                # Deduplicate by link (same item across multiple URLs).
                by_link = {l.link: l for l in all_listings}

                events = store.record_scan(list(by_link.values()))
                for event in events:
                    if event_should_notify(event, _Cfg(notify_existing, notify_price_increases), initial_scan):
                        LOGGER.info(
                            "[%s] %s — %s", event.type.name, event.listing.title, event.listing.link
                        )
                        if webhook:
                            try:
                                send_to_discord(session, webhook, event)
                            except requests.RequestException as err:
                                LOGGER.error("Discord notify failed: %s", err)

                LOGGER.debug(
                    "Scan: %d listings seen, %d events (%.2fs)",
                    len(by_link),
                    len(events),
                    time.monotonic() - scan_start,
                )
                initial_scan = False
            except Exception:
                LOGGER.exception("Unexpected error during Vinted scan")

            if once:
                return

            elapsed = time.monotonic() - scan_start
            wait = max(0.0, poll_delay - elapsed)
            if wait > 0:
                time.sleep(wait)


class _Cfg:
    """Minimal config shim so event_should_notify() works without a full Config."""
    def __init__(self, notify_existing: bool, notify_price_increases: bool) -> None:
        self.notify_existing = notify_existing
        self.notify_price_increases = notify_price_increases


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Zero-delay Vinted monitor")
    parser.add_argument("--once", action="store_true", help="Run one scan and exit")
    args = parser.parse_args()

    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(message)s",
    )
    run(once=args.once)
