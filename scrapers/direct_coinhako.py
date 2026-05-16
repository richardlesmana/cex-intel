"""
Scrapes Coinhako's official press page (press.coinhako.com) using Playwright.

Why Playwright: coinhako.com is behind Cloudflare, which blocks plain HTTP
requests. Headless Chromium with stealth args (disable webdriver fingerprint)
passes the challenge without requiring a visible browser window.

Target: press.coinhako.com - official company announcements and press coverage.
Note: blog.coinhako.com (educational content) has a public RSS feed at
blog.coinhako.com/rss/ and can be added to news_aggregator.py instead.
"""

import json
import logging
import random
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from dateutil import parser as dateutil_parser
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger(__name__)

TARGET_URL   = "https://press.coinhako.com/"
OUTPUT_PATH  = Path(__file__).parent.parent / "data" / "direct_coinhako.json"
DEBUG_SHOT   = Path(__file__).parent.parent / "data" / "debug_coinhako.png"
USER_AGENT   = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)
MAX_ENTRIES = 20
BASE_URL    = "https://press.coinhako.com"

# Matches "MAY 18, 2023" or "MAY 2023"
_DATE_RE = re.compile(r"\b[A-Z]{3}\s+\d{1,2},\s+\d{4}\b|\b[A-Z]{3}\s+\d{4}\b")


def parse_post(post) -> dict:
    # Title
    try:
        title = post.locator("h3").first.inner_text().strip()
    except Exception:
        title = ""

    # URL (first anchor, href is relative)
    try:
        href = post.locator("a").first.get_attribute("href") or ""
        url  = BASE_URL + href if href.startswith("/") else href
    except Exception:
        url = ""

    # Parse inner text lines to find date and optional summary
    raw_lines = [l.strip() for l in post.inner_text().split("\n") if l.strip()]

    date_str = ""
    coinhako_idx = None
    for i, line in enumerate(raw_lines):
        if line.upper() == "COINHAKO":
            coinhako_idx = i
        if _DATE_RE.match(line):
            date_str = line

    # Summary: text between the title line and the "COINHAKO" publisher label
    summary = ""
    if coinhako_idx and coinhako_idx > 1:
        candidate = " ".join(raw_lines[1:coinhako_idx])
        # Skip if it's just the title repeated or empty
        if candidate and candidate.lower() != title.lower():
            summary = candidate[:300]

    # Parse date to ISO-8601
    pub_date = None
    if date_str:
        try:
            pub_date = dateutil_parser.parse(date_str).replace(tzinfo=timezone.utc).isoformat()
        except Exception:
            pub_date = date_str  # keep raw if parse fails

    return {
        "competitor":        "Coinhako",
        "country":           ["Singapore"],
        "source":            "coinhako_direct",
        "title":             title,
        "url":               url,
        "published_date":    pub_date,
        "summary":           summary,
    }


def scrape(page) -> list:
    log.info("Navigating to %s", TARGET_URL)

    # Polite delay before hitting the server
    time.sleep(random.uniform(1.5, 2.5))

    page.goto(TARGET_URL, timeout=15000, wait_until="networkidle")

    posts = page.locator(".post").all()
    log.info("Found %d .post elements on page", len(posts))

    entries = []
    for post in posts[:MAX_ENTRIES]:
        parsed = parse_post(post)
        if parsed["title"]:  # skip any empty cards
            entries.append(parsed)

    return entries


def main():
    page = None
    browser = None

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
            # Remove webdriver fingerprint that Cloudflare detects
            page.add_init_script(
                "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
            )

            entries = scrape(page)
            browser.close()

    except PWTimeout as exc:
        log.error("Page timed out: %s", exc)
        if page:
            try:
                DEBUG_SHOT.parent.mkdir(parents=True, exist_ok=True)
                page.screenshot(path=str(DEBUG_SHOT))
                log.info("Debug screenshot saved to %s", DEBUG_SHOT)
            except Exception:
                pass
        sys.exit(1)
    except Exception as exc:
        log.error("Scrape failed: %s", exc)
        if page:
            try:
                DEBUG_SHOT.parent.mkdir(parents=True, exist_ok=True)
                page.screenshot(path=str(DEBUG_SHOT))
                log.info("Debug screenshot saved to %s", DEBUG_SHOT)
            except Exception:
                pass
        sys.exit(1)

    output = {
        "competitor":      "Coinhako",
        "source":          "coinhako_direct",
        "scrape_timestamp": datetime.now(timezone.utc).isoformat(),
        "total_entries":   len(entries),
        "entries":         entries,
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(output, indent=2, ensure_ascii=False))
    log.info("Written to %s", OUTPUT_PATH)

    print(f"\nScraped {len(entries)} entries from Coinhako press page")


if __name__ == "__main__":
    main()
