"""
Fetches Bybit's official announcements page and extracts articles from the
server-side rendered __NEXT_DATA__ JSON block embedded in the HTML.

No Playwright needed: Bybit uses Next.js SSR, so the initial 20 articles are
fully baked into the HTML response. No browser automation or session required.

Note: Playwright fails on announcements.bybit.com with HTTP2 protocol errors
(confirmed during reconnaissance). requests works fine.

URL: https://announcements.bybit.com/en/
Data path: __NEXT_DATA__ > props.pageProps.articleInitEntity.list
"""

import json
import logging
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger(__name__)

PAGE_URL    = "https://announcements.bybit.com/en/"
OUTPUT_PATH = Path(__file__).parent.parent / "data" / "direct_bybit.json"
DEBUG_PATH  = Path(__file__).parent.parent / "data" / "debug_bybit.txt"
ARTICLE_BASE = "https://announcements.bybit.com/en"
MAX_ENTRIES = 20

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,*/*",
    "Accept-Language": "en-US,en;q=0.9",
}

_NEXT_DATA_RE = re.compile(
    r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
    re.DOTALL,
)


def fetch_page() -> str:
    try:
        resp = requests.get(PAGE_URL, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        return resp.text
    except requests.RequestException as exc:
        log.error("Failed to fetch page: %s", exc)
        return ""


def extract_articles(html: str) -> list:
    match = _NEXT_DATA_RE.search(html)
    if not match:
        log.error("__NEXT_DATA__ script block not found in page")
        return []

    try:
        nd = json.loads(match.group(1))
    except json.JSONDecodeError as exc:
        log.error("Failed to parse __NEXT_DATA__: %s", exc)
        return []

    entity = nd.get("props", {}).get("pageProps", {}).get("articleInitEntity", {})
    items  = entity.get("list", [])
    total  = entity.get("total", 0)
    log.info("Found %d articles in initial payload (site total: %d)", len(items), total)
    return items


def build_entry(item: dict) -> dict:
    pub_ts  = item.get("publish_time") or item.get("date_timestamp")
    pub_iso = (
        datetime.fromtimestamp(pub_ts, tz=timezone.utc).isoformat()
        if pub_ts else None
    )

    relative_url = item.get("url", "")
    url = ARTICLE_BASE + relative_url if relative_url.startswith("/") else relative_url

    title       = item.get("title", "").strip()
    description = item.get("description", "").strip()
    # description is often identical to title for promotional posts; skip when so
    summary = description[:300] if description.lower() != title.lower() else ""

    return {
        "competitor":     "Bybit",
        "country":        [],
        "source":         "bybit_direct",
        "title":          title,
        "url":            url,
        "published_date": pub_iso,
        "summary":        summary,
        "category":       item.get("category", {}).get("title", ""),
    }


def main():
    html = fetch_page()
    if not html:
        DEBUG_PATH.parent.mkdir(parents=True, exist_ok=True)
        DEBUG_PATH.write_text(f"Page fetch failed for {PAGE_URL}\n")
        sys.exit(1)

    items = extract_articles(html)
    if not items:
        DEBUG_PATH.parent.mkdir(parents=True, exist_ok=True)
        DEBUG_PATH.write_text(f"No articles extracted. HTML snippet:\n{html[:2000]}\n")
        log.error("Debug info written to %s", DEBUG_PATH)
        sys.exit(1)

    entries = [build_entry(item) for item in items[:MAX_ENTRIES]]

    output = {
        "competitor":       "Bybit",
        "source":           "bybit_direct",
        "scrape_timestamp": datetime.now(timezone.utc).isoformat(),
        "total_entries":    len(entries),
        "entries":          entries,
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(output, indent=2, ensure_ascii=False))
    log.info("Written to %s", OUTPUT_PATH)

    print(f"\nScraped {len(entries)} entries from Bybit announcements")


if __name__ == "__main__":
    main()
