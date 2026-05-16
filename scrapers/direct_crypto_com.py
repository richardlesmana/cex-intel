"""
Fetches Crypto.com Exchange announcements from their public static JSON file.

No Playwright needed: Crypto.com serves a pre-built JSON snapshot at
static2.crypto.com/exchange/announcements_en.json. It is fully public
(no auth required) and contains the full HTML content of each announcement.

Data note: the file contains ~400 announcements with full HTML bodies.
We take the 20 most recent (sorted by announcedAt desc) and strip the
HTML to produce a plain-text summary.

Article URL pattern: https://crypto.com/exchange/announcements/{category}/{id}
Categories: list, delist, product, event, system
"""

import json
import logging
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import requests
from bs4 import BeautifulSoup

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger(__name__)

JSON_URL    = "https://static2.crypto.com/exchange/announcements_en.json"
OUTPUT_PATH = Path(__file__).parent.parent / "data" / "direct_crypto_com.json"
DEBUG_PATH  = Path(__file__).parent.parent / "data" / "debug_crypto_com.txt"
ARTICLE_BASE = "https://crypto.com/exchange/announcements"
MAX_ENTRIES  = 20
SUMMARY_MAX  = 300

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
}


def fetch_announcements() -> list:
    try:
        resp = requests.get(JSON_URL, headers=HEADERS, timeout=20)
        resp.raise_for_status()
    except requests.RequestException as exc:
        log.error("Request failed: %s", exc)
        return []

    data = resp.json()
    if not isinstance(data, list):
        log.error("Unexpected response shape: %s", type(data))
        return []

    log.info("Fetched %d total announcements", len(data))
    # Sort by announcedAt descending, take most recent
    sorted_data = sorted(data, key=lambda x: x.get("announcedAt", 0), reverse=True)
    return sorted_data


def to_iso(epoch_ms: int) -> Optional[str]:
    try:
        return datetime.fromtimestamp(epoch_ms / 1000, tz=timezone.utc).isoformat()
    except (ValueError, TypeError):
        return None


def extract_summary(html: str) -> str:
    if not html:
        return ""
    text = BeautifulSoup(html, "html.parser").get_text(separator=" ").strip()
    text = re.sub(r"\s+", " ", text)
    return text[:SUMMARY_MAX]


def build_entry(item: dict) -> dict:
    category = item.get("category", "")
    item_id  = item.get("id", "")
    url = f"{ARTICLE_BASE}/{category}/{item_id}" if category and item_id else ARTICLE_BASE

    return {
        "competitor":     "Crypto.com",
        "country":        [],
        "source":         "crypto_com_direct",
        "title":          item.get("title", "").strip(),
        "url":            url,
        "published_date": to_iso(item.get("announcedAt")),
        "summary":        extract_summary(item.get("content", "")),
        "category":       category,
    }


def main():
    data = fetch_announcements()
    if not data:
        DEBUG_PATH.parent.mkdir(parents=True, exist_ok=True)
        DEBUG_PATH.write_text(f"No data returned from {JSON_URL}\n")
        log.error("Debug info written to %s", DEBUG_PATH)
        sys.exit(1)

    entries = [build_entry(item) for item in data[:MAX_ENTRIES]]

    output = {
        "competitor":       "Crypto.com",
        "source":           "crypto_com_direct",
        "scrape_timestamp": datetime.now(timezone.utc).isoformat(),
        "total_entries":    len(entries),
        "entries":          entries,
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(output, indent=2, ensure_ascii=False))
    log.info("Written to %s", OUTPUT_PATH)

    print(f"\nScraped {len(entries)} entries from Crypto.com announcements")


if __name__ == "__main__":
    main()
