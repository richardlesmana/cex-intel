"""
Scrapes Revolut's blog for crypto-category posts using Playwright.

Why Playwright: revolut.com is behind Cloudflare; plain requests returns 403.
blog.revolut.com redirects to www.revolut.com/blog/ when opened in a browser.

Data source: __NEXT_DATA__ SSR JSON embedded in the blog page. The widget data
contains all 537 blog posts. We filter to the 'crypto' category (native Revolut
taxonomy, 24 posts as of May 2026) which cleanly removes banking basics,
emigration guides, HR posts, etc.

No RSS alternative: blog.revolut.com/rss/ is also Cloudflare-blocked (403).
Not added to news_aggregator.py for the same reason.

No summary available: the listing JSON only has title, slug, categories,
and publishedAt. Individual article pages would be needed for body text.
"""

import json
import logging
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger(__name__)

TARGET_URL  = "https://www.revolut.com/blog/"
OUTPUT_PATH = Path(__file__).parent.parent / "data" / "direct_revolut.json"
DEBUG_SHOT  = Path(__file__).parent.parent / "data" / "debug_revolut.png"
ARTICLE_BASE = "https://www.revolut.com/blog/"
USER_AGENT  = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)
MAX_ENTRIES      = 20
CRYPTO_CATEGORY  = "crypto"

_NEXT_DATA_RE = re.compile(
    r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
    re.DOTALL,
)


def extract_posts(html: str) -> list:
    match = _NEXT_DATA_RE.search(html)
    if not match:
        log.error("__NEXT_DATA__ not found in page")
        return []
    try:
        nd = json.loads(match.group(1))
    except json.JSONDecodeError as exc:
        log.error("Failed to parse __NEXT_DATA__: %s", exc)
        return []

    posts = (
        nd.get("props", {})
          .get("pageProps", {})
          .get("widgetData", {})
          .get("blog-posts-list-widget", {})
          .get("posts", [])
    )
    log.info("Total posts in feed: %d", len(posts))

    crypto = [p for p in posts if CRYPTO_CATEGORY in p.get("categories", [])]
    log.info("Crypto-category posts: %d", len(crypto))

    # Sort newest first
    crypto.sort(key=lambda p: p.get("publishedAt", 0), reverse=True)
    return crypto


def to_iso(epoch_ms: int) -> Optional[str]:
    try:
        return datetime.fromtimestamp(epoch_ms / 1000, tz=timezone.utc).isoformat()
    except (ValueError, TypeError):
        return None


def build_entry(post: dict) -> dict:
    slug = post.get("slug", "")
    return {
        "competitor":     "Revolut",
        "country":        [],
        "source":         "revolut_direct",
        "title":          post.get("title", "").strip(),
        "url":            ARTICLE_BASE + slug if slug else ARTICLE_BASE,
        "published_date": to_iso(post.get("publishedAt")),
        "summary":        "",
        "category":       ", ".join(post.get("categories", [])),
    }


def scrape() -> list:
    page_ref = None
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
            )
            ctx = browser.new_context(
                user_agent=USER_AGENT,
                locale="en-US",
                viewport={"width": 1280, "height": 800},
            )
            page = ctx.new_page()
            page_ref = page
            page.add_init_script(
                "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
            )
            page.goto(TARGET_URL, timeout=25000, wait_until="networkidle")
            log.info("Loaded: %s", page.url)

            posts = extract_posts(page.content())
            browser.close()
            return posts

    except PWTimeout as exc:
        log.error("Page timed out: %s", exc)
    except Exception as exc:
        log.error("Scrape failed: %s", exc)

    # Save debug screenshot on failure
    if page_ref:
        try:
            DEBUG_SHOT.parent.mkdir(parents=True, exist_ok=True)
            page_ref.screenshot(path=str(DEBUG_SHOT))
            log.info("Debug screenshot saved to %s", DEBUG_SHOT)
        except Exception:
            pass
    return []


def main():
    posts = scrape()
    if not posts:
        sys.exit(1)

    entries = [build_entry(p) for p in posts[:MAX_ENTRIES]]

    output = {
        "competitor":       "Revolut",
        "source":           "revolut_direct",
        "scrape_timestamp": datetime.now(timezone.utc).isoformat(),
        "total_entries":    len(entries),
        "entries":          entries,
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(output, indent=2, ensure_ascii=False))
    log.info("Written to %s", OUTPUT_PATH)

    print(f"\nScraped {len(entries)} crypto-category entries from Revolut blog")


if __name__ == "__main__":
    main()
