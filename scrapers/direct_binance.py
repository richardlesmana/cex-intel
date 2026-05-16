"""
Fetches Binance's official announcements via their internal JSON API.

Unlike direct_coinhako.py (which needs Playwright to bypass Cloudflare),
Binance exposes a public API endpoint that works with plain HTTP requests
using a small set of static headers discovered by intercepting browser traffic.

Source: Latest Binance News category (catalogId=49) on the announcements board.
Add more catalogIds to CATALOG_IDS to pull listings, API updates, etc.

API schema per article: {id, code, title, type, releaseDate (epoch ms)}
No summary is returned by the API listing endpoint - would require fetching
individual article pages, which is skipped to keep this lightweight.
"""

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger(__name__)

API_URL     = "https://www.binance.com/bapi/apex/v1/public/apex/cms/article/list/query"
OUTPUT_PATH = Path(__file__).parent.parent / "data" / "direct_binance.json"
DEBUG_SHOT  = Path(__file__).parent.parent / "data" / "debug_binance.txt"

# catalogId=49 = Latest Binance News (general announcements)
# catalogId=48 = New Cryptocurrency Listing
# catalogId=161 = Delisting
CATALOG_IDS = [49, 48]
MAX_PER_CATEGORY = 10  # total target ~20 across categories

ARTICLE_BASE_URL = "https://www.binance.com/en/support/announcement/detail/"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "csrftoken":    "d41d8cd98f00b204e9800998ecf8427e",  # md5(""), static
    "lang":         "en",
    "x-host":       "www.binance.com",
    "content-type": "application/json",
    "referer":      "https://www.binance.com/en/support/announcement",
}


def fetch_category(catalog_id: int, page_size: int) -> list:
    try:
        resp = requests.get(
            API_URL,
            params={"type": 1, "pageNo": 1, "pageSize": page_size, "catalogId": catalog_id},
            headers=HEADERS,
            timeout=15,
        )
        resp.raise_for_status()
    except requests.RequestException as exc:
        log.warning("[catalogId=%d] Request failed: %s", catalog_id, exc)
        return []

    data = resp.json()
    if data.get("code") != "000000":
        log.warning("[catalogId=%d] API error: %s", catalog_id, data.get("message"))
        return []

    catalogs = data.get("data", {}).get("catalogs", [])
    if not catalogs:
        log.warning("[catalogId=%d] No catalogs in response", catalog_id)
        return []

    articles = catalogs[0].get("articles", [])
    log.info("[catalogId=%d] %s: %d articles", catalog_id, catalogs[0].get("catalogName", "?"), len(articles))
    return articles


def to_iso(epoch_ms: int) -> str:
    return datetime.fromtimestamp(epoch_ms / 1000, tz=timezone.utc).isoformat()


def build_entry(article: dict) -> dict:
    return {
        "competitor": "Binance",
        "country":    [],
        "source":     "binance_direct",
        "title":      article.get("title", "").strip(),
        "url":        ARTICLE_BASE_URL + article.get("code", ""),
        "published_date": to_iso(article["releaseDate"]) if article.get("releaseDate") else None,
        "summary":    "",
    }


def main():
    all_entries = []
    seen_codes  = set()

    for catalog_id in CATALOG_IDS:
        raw = fetch_category(catalog_id, MAX_PER_CATEGORY)
        for article in raw:
            code = article.get("code", "")
            if code and code not in seen_codes:
                seen_codes.add(code)
                all_entries.append(build_entry(article))

    if not all_entries:
        log.error("No entries fetched. Writing diagnostics to %s", DEBUG_SHOT)
        DEBUG_SHOT.parent.mkdir(parents=True, exist_ok=True)
        DEBUG_SHOT.write_text(
            f"Attempted catalog IDs: {CATALOG_IDS}\n"
            f"Headers sent: {json.dumps(HEADERS, indent=2)}\n"
        )
        sys.exit(1)

    output = {
        "competitor":       "Binance",
        "source":           "binance_direct",
        "scrape_timestamp": datetime.now(timezone.utc).isoformat(),
        "total_entries":    len(all_entries),
        "entries":          all_entries,
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(output, indent=2, ensure_ascii=False))
    log.info("Written to %s", OUTPUT_PATH)

    print(f"\nScraped {len(all_entries)} entries from Binance announcements")


if __name__ == "__main__":
    main()
