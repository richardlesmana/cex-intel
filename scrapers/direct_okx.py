"""
Fetches OKX announcements via their public REST API.

No Playwright or browser needed: OKX exposes a clean public endpoint at
/api/v5/support/announcements that returns the 20 most recent announcements
with no authentication or session required.

API schema per article: {annType, title, url, pTime (epoch ms str), businessPTime}
- pTime: precise publish timestamp (milliseconds, as string)
- businessPTime: the announced effective date
- url: absolute but geo-localised (en-sg); locale prefix is stripped here
"""

import json
import logging
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import requests

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger(__name__)

API_URL     = "https://www.okx.com/api/v5/support/announcements"
OUTPUT_PATH = Path(__file__).parent.parent / "data" / "direct_okx.json"
DEBUG_PATH  = Path(__file__).parent.parent / "data" / "debug_okx.txt"
MAX_ENTRIES = 20

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
}

# Strip locale prefix like /en-sg/ or /zh-hans/ from OKX URLs
_LOCALE_RE = re.compile(r"(https://www\.okx\.com)/[a-z]{2}(?:-[a-z]{2,4})?(/)")


def normalise_url(url: str) -> str:
    return _LOCALE_RE.sub(r"\1\2", url)


def fetch_announcements() -> list:
    try:
        resp = requests.get(API_URL, headers=HEADERS, timeout=15)
        resp.raise_for_status()
    except requests.RequestException as exc:
        log.error("Request failed: %s", exc)
        return []

    data = resp.json()
    if data.get("code") != "0":
        log.error("API error: code=%s msg=%s", data.get("code"), data.get("msg"))
        return []

    outer = data.get("data", [])
    if not outer:
        log.error("Empty data array in response")
        return []

    articles = outer[0].get("details", [])
    log.info("Fetched %d announcements", len(articles))
    return articles


def to_iso(epoch_ms_str: str) -> Optional[str]:
    try:
        return datetime.fromtimestamp(int(epoch_ms_str) / 1000, tz=timezone.utc).isoformat()
    except (ValueError, TypeError):
        return None


def build_entry(article: dict) -> dict:
    return {
        "competitor":     "OKX",
        "country":        [],
        "source":         "okx_direct",
        "title":          article.get("title", "").strip(),
        "url":            normalise_url(article.get("url", "")),
        "published_date": to_iso(article.get("pTime")),
        "summary":        "",
        "category":       article.get("annType", ""),
    }


def main():
    articles = fetch_announcements()
    if not articles:
        DEBUG_PATH.parent.mkdir(parents=True, exist_ok=True)
        DEBUG_PATH.write_text(f"No articles returned from {API_URL}\n")
        log.error("Debug info written to %s", DEBUG_PATH)
        sys.exit(1)

    entries = [build_entry(a) for a in articles[:MAX_ENTRIES]]

    output = {
        "competitor":       "OKX",
        "source":           "okx_direct",
        "scrape_timestamp": datetime.now(timezone.utc).isoformat(),
        "total_entries":    len(entries),
        "entries":          entries,
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(output, indent=2, ensure_ascii=False))
    log.info("Written to %s", OUTPUT_PATH)

    print(f"\nScraped {len(entries)} entries from OKX announcements")


if __name__ == "__main__":
    main()
