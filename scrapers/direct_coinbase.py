"""
Scrapes Coinbase's blog using Playwright.

Why Playwright: www.coinbase.com returns 403 to plain requests (Cloudflare).
Headless Chromium with stealth args bypasses the challenge.

Target: https://www.coinbase.com/en-sg/blog
Data: Article cards rendered client-side. No __NEXT_DATA__ or public API found.
      Extraction walks all non-category anchor tags with /blog/ hrefs, then
      parses the card text (title / author / date / summary preview).

URL normalisation: the page serves en-sg locale but article permalinks are
locale-neutral (coinbase.com/blog/slug), so we use those directly.
"""

import json
import logging
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from dateutil import parser as dateutil_parser
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger(__name__)

TARGET_URL  = "https://www.coinbase.com/en-sg/blog"
OUTPUT_PATH = Path(__file__).parent.parent / "data" / "direct_coinbase.json"
DEBUG_SHOT  = Path(__file__).parent.parent / "data" / "debug_coinbase.png"
USER_AGENT  = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)
MAX_ENTRIES = 20

_DATE_RE = re.compile(
    r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2},\s+\d{4}\b"
)


def parse_card(card: dict) -> dict:
    href  = card.get("href", "")
    text  = card.get("text", "")
    lines = [l.strip() for l in text.split("\n") if l.strip()]

    title = lines[0] if lines else ""

    # Find date line
    date_str, date_idx = "", None
    for i, line in enumerate(lines):
        if _DATE_RE.search(line):
            date_str = line
            date_idx = i
            break

    pub_date = None
    if date_str:
        try:
            pub_date = dateutil_parser.parse(date_str).replace(tzinfo=timezone.utc).isoformat()
        except Exception:
            pub_date = date_str

    # Summary: lines after the date line, up to 300 chars
    summary = ""
    if date_idx is not None and date_idx + 1 < len(lines):
        summary = " ".join(lines[date_idx + 1:])[:300]

    return {
        "competitor":     "Coinbase",
        "country":        [],
        "source":         "coinbase_direct",
        "title":          title,
        "url":            href,
        "published_date": pub_date,
        "summary":        summary,
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
            log.info("Loaded: %s  title: %s", page.url, page.title())

            cards = page.evaluate('''() => {
                const seen = new Set();
                const results = [];
                document.querySelectorAll("a[href*='/blog/']").forEach(a => {
                    const href = a.href;
                    if (seen.has(href)) return;
                    if (href.includes("/blog/landing/") ||
                        href.endsWith("/blog") ||
                        href.endsWith("/blog/")) return;
                    seen.add(href);
                    const container = a.closest("li, article") || a.parentElement;
                    const text = container ? container.innerText.trim() : a.innerText.trim();
                    results.push({ href, text: text.slice(0, 400) });
                });
                return results;
            }''')

            log.info("Found %d article cards", len(cards))
            browser.close()
            return cards

    except PWTimeout as exc:
        log.error("Page timed out: %s", exc)
    except Exception as exc:
        log.error("Scrape failed: %s", exc)

    if page_ref:
        try:
            DEBUG_SHOT.parent.mkdir(parents=True, exist_ok=True)
            page_ref.screenshot(path=str(DEBUG_SHOT))
            log.info("Debug screenshot saved to %s", DEBUG_SHOT)
        except Exception:
            pass
    return []


def main():
    cards = scrape()
    if not cards:
        sys.exit(1)

    entries = [parse_card(c) for c in cards[:MAX_ENTRIES]]

    output = {
        "competitor":       "Coinbase",
        "source":           "coinbase_direct",
        "scrape_timestamp": datetime.now(timezone.utc).isoformat(),
        "total_entries":    len(entries),
        "entries":          entries,
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(output, indent=2, ensure_ascii=False))
    log.info("Written to %s", OUTPUT_PATH)

    print(f"\nScraped {len(entries)} entries from Coinbase blog")


if __name__ == "__main__":
    main()
