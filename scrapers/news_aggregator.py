"""
Aggregates crypto industry news from multiple RSS feeds, detects competitor
and country mentions, deduplicates by URL, and writes to data/news_signals.json.

Signal sources: CoinDesk, Decrypt, Cointelegraph, Cryptonews, CryptoSlate,
BeInCrypto, U.Today, Cryptopotato.

Matching notes:
- All patterns are case-insensitive.
- "COIN" (Coinbase ticker) only matches as "$COIN" or "COIN stock/shares" to
  avoid the extreme noise of bare "coin" in crypto headlines.
- "CZ" (Binance founder) only fires when Binance/BNB context is also present.
- "Cronos" is Crypto.com's L1 brand; Crypto.com matches as a literal string.
- "MAS" (Monetary Authority of Singapore) may have rare false positives in
  non-SG financial contexts.
"""

import json
import logging
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import feedparser
import requests
from bs4 import BeautifulSoup
from dateutil import parser as dateutil_parser

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger(__name__)

FEEDS = [
    {"name": "Coindesk",       "url": "https://www.coindesk.com/arc/outboundfeeds/rss/"},
    {"name": "Decrypt",        "url": "https://decrypt.co/feed"},
    {"name": "Cointelegraph",  "url": "https://cointelegraph.com/rss"},
    {"name": "Cryptonews",     "url": "https://cryptonews.com/news/feed/"},
    {"name": "CryptoSlate",    "url": "https://cryptoslate.com/feed/"},
    {"name": "BeInCrypto",     "url": "https://beincrypto.com/feed/"},
    {"name": "U.Today",        "url": "https://u.today/rss"},
    {"name": "Cryptopotato",   "url": "https://cryptopotato.com/feed/"},
    {"name": "Coinhako Blog",  "url": "https://blog.coinhako.com/rss/",
     "auto_competitors": ["Coinhako"], "auto_countries": ["Singapore"]},
]

OUTPUT_PATH = Path(__file__).parent.parent / "data" / "news_signals.json"
SUMMARY_MAX_CHARS = 500

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/rss+xml, application/xml, text/xml, */*",
}

# Aliases per competitor. All patterns ORed, all case-insensitive.
# Order matters for display; canonical name is the dict key.
COMPETITOR_PATTERNS: dict[str, list[str]] = {
    "Binance":    [r"\bBinance\b", r"\bBNB Chain\b"],
    "Bybit":      [r"\bBybit\b"],
    "OKX":        [r"\bOKX\b"],
    "Coinbase":   [r"\bCoinbase\b", r"\$COIN\b", r"\bCOIN\s+(?:stock|shares)\b"],
    "Coinhako":   [r"\bCoinhako\b"],
    "Crypto.com": [r"\bCrypto\.com\b", r"\bCronos\b"],
    "Revolut":    [r"\bRevolut\b"],
    "MooMoo":     [r"\bMooMoo\b"],  # low-signal but valid SG fintech competitor
}

# CZ: Binance founder. Only tag Binance if CZ appears AND Binance/BNB is also present.
# (avoids false positives on "CZ" in non-crypto contexts)
_CZ_RE = re.compile(r"\bCZ\b", re.IGNORECASE)
_BINANCE_CONTEXT_RE = re.compile(r"\bBinance\b|\bBNB\b", re.IGNORECASE)

_COMPETITOR_RE = {
    name: re.compile("|".join(patterns), re.IGNORECASE)
    for name, patterns in COMPETITOR_PATTERNS.items()
}

COUNTRY_PATTERNS: dict[str, str] = {
    # \bSingapore\b already matches "Singapore-based" (hyphen = word boundary)
    "Singapore": r"\bSingapore(?:an)?\b|\bMAS\b",
    "Australia":  r"\bAustrali(?:a|an)\b|\bAUSTRAC\b|\bAussie\b|\bAFSL\b|\bASIC\b",
}

_COUNTRY_RE = {
    name: re.compile(pattern, re.IGNORECASE)
    for name, pattern in COUNTRY_PATTERNS.items()
}


def fetch_feed(feed_cfg: dict) -> Optional[feedparser.FeedParserDict]:
    name, url = feed_cfg["name"], feed_cfg["url"]
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
    except requests.RequestException as exc:
        log.warning("[%s] Fetch failed: %s", name, exc)
        return None

    parsed = feedparser.parse(resp.content)
    if not parsed.entries:
        log.warning("[%s] No entries returned (bozo=%s)", name, parsed.bozo)
        return None

    log.info("[%s] %d entries fetched", name, len(parsed.entries))
    return parsed


def parse_date(entry) -> Optional[datetime]:
    for attr in ("published", "updated"):
        raw = getattr(entry, attr, None)
        if raw:
            try:
                dt = dateutil_parser.parse(raw)
                return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
            except Exception:
                continue
    return None


def extract_summary(entry) -> str:
    raw = getattr(entry, "summary", "") or getattr(entry, "description", "") or ""
    if not raw:
        return ""
    text = BeautifulSoup(raw, "html.parser").get_text(separator=" ").strip()
    return re.sub(r"\s+", " ", text)[:SUMMARY_MAX_CHARS]


def detect_competitors(text: str) -> list[str]:
    found = [name for name, rx in _COMPETITOR_RE.items() if rx.search(text)]
    # CZ contextual rule: only add Binance signal if not already matched
    if "Binance" not in found and _CZ_RE.search(text) and _BINANCE_CONTEXT_RE.search(text):
        found.append("Binance")
    return found


def detect_countries(text: str) -> list[str]:
    return [name for name, rx in _COUNTRY_RE.items() if rx.search(text)]


def parse_articles(feed: feedparser.FeedParserDict, feed_cfg: dict) -> list:
    source_name     = feed_cfg["name"]
    auto_competitors = feed_cfg.get("auto_competitors", [])
    auto_countries   = feed_cfg.get("auto_countries", [])

    articles = []
    for entry in feed.entries:
        title   = entry.get("title", "").strip()
        url     = entry.get("link", "").strip()
        pub     = parse_date(entry)
        summary = extract_summary(entry)
        scan    = f"{title} {summary}"

        competitors = list(dict.fromkeys(auto_competitors + detect_competitors(scan)))
        countries   = list(dict.fromkeys(auto_countries   + detect_countries(scan)))

        articles.append({
            "source":                source_name,
            "title":                 title,
            "url":                   url,
            "published_date":        pub.isoformat() if pub else None,
            "summary":               summary,
            "mentioned_competitors": competitors,
            "mentioned_countries":   countries,
        })
    return articles


def deduplicate(articles: list) -> list:
    seen, out = set(), []
    for a in articles:
        if a["url"] and a["url"] not in seen:
            seen.add(a["url"])
            out.append(a)
    return out


def print_summary(articles: list, source_statuses: dict):
    competitor_counts = {c: 0 for c in COMPETITOR_PATTERNS}
    country_counts    = {c: 0 for c in COUNTRY_PATTERNS}

    for a in articles:
        for c in a["mentioned_competitors"]:
            competitor_counts[c] += 1
        for c in a["mentioned_countries"]:
            country_counts[c] += 1

    n_ok     = sum(1 for s in source_statuses.values() if s["status"] == "OK")
    n_total  = len(source_statuses)
    n_arts   = len(articles)
    n_mentions = sum(1 for a in articles if a["mentioned_competitors"] or a["mentioned_countries"])

    W = 58
    print(f"\n{'='*W}")
    print(f"  News Aggregator  —  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*W}")
    print(f"  Sources: {n_ok}/{n_total} OK   |   Articles: {n_arts} total, {n_mentions} with mentions")

    print(f"\n  {'Source':<16} {'Status':<8} {'Articles':>8}")
    print(f"  {'-'*(W-2)}")
    for name, s in source_statuses.items():
        status_label = "OK" if s["status"] == "OK" else "FAILED"
        count_str    = str(s["count"]) if s["status"] == "OK" else "-"
        print(f"  {name:<16} {status_label:<8} {count_str:>8}")

    print(f"\n  Competitor mentions (sorted by frequency):")
    print(f"  {'Name':<16} {'Count':>5}  Bar")
    print(f"  {'-'*(W-2)}")
    for name, count in sorted(competitor_counts.items(), key=lambda x: -x[1]):
        bar = "█" * min(count, 30)
        print(f"  {name:<16} {count:>5}  {bar}")

    print(f"\n  Country mentions:")
    for name, count in country_counts.items():
        bar = "█" * min(count, 30)
        print(f"  {name:<16} {count:>5}  {bar}")

    # Top 5 articles with any mention for spot-checking
    matched = [a for a in articles if a["mentioned_competitors"] or a["mentioned_countries"]]
    if matched:
        print(f"\n  Top {min(5, len(matched))} articles with mentions (spot-check for false positives):")
        print(f"  {'-'*(W-2)}")
        for i, a in enumerate(matched[:5], 1):
            title_short = a["title"][:70] + ("…" if len(a["title"]) > 70 else "")
            tags = " | ".join(a["mentioned_competitors"] + a["mentioned_countries"])
            print(f"  {i}. [{a['source']}] {title_short}")
            print(f"     Tags: {tags}")

    print(f"{'='*W}\n")


def main():
    source_statuses: dict[str, dict] = {}
    all_articles: list = []

    for feed_cfg in FEEDS:
        name = feed_cfg["name"]
        feed = fetch_feed(feed_cfg)
        if feed is None:
            source_statuses[name] = {"status": "FAILED", "count": 0}
            continue
        articles = parse_articles(feed, feed_cfg)
        source_statuses[name] = {"status": "OK", "count": len(articles)}
        all_articles.extend(articles)

    if not all_articles:
        log.error("No articles collected from any source.")
        sys.exit(1)

    all_articles = deduplicate(all_articles)
    articles_with_mentions = sum(
        1 for a in all_articles if a["mentioned_competitors"] or a["mentioned_countries"]
    )

    output = {
        "scrape_timestamp":                  datetime.now(timezone.utc).isoformat(),
        "sources_attempted":                 len(FEEDS),
        "sources_successful":                sum(1 for s in source_statuses.values() if s["status"] == "OK"),
        "total_articles":                    len(all_articles),
        "articles_with_competitor_mentions": articles_with_mentions,
        "articles":                          all_articles,
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(output, indent=2, ensure_ascii=False))
    log.info("Written to %s", OUTPUT_PATH)

    print_summary(all_articles, source_statuses)


if __name__ == "__main__":
    main()
