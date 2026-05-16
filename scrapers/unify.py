"""
ETL layer: reads all scraper outputs and produces a single clean
published_data/dashboard.json for the dashboard.

Transformations applied:
- Unified schema across direct scrapers and news aggregator
- Deterministic ID from URL hash
- Deduplication by URL
- Date filtering: skip unparseable dates; drop entries older than 12 months
- Sort by published_date descending
"""

import hashlib
import json
import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from dateutil import parser as dateutil_parser

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger(__name__)

ROOT        = Path(__file__).parent.parent
OUTPUT_PATH = ROOT / "published_data" / "dashboard.json"
CUTOFF_DAYS = 365

INPUT_FILES = [
    {"path": ROOT / "data/news_signals.json",     "source_type": "news"},
    {"path": ROOT / "data/direct_binance.json",   "source_type": "direct"},
    {"path": ROOT / "data/direct_bybit.json",     "source_type": "direct"},
    {"path": ROOT / "data/direct_okx.json",       "source_type": "direct"},
    {"path": ROOT / "data/direct_crypto_com.json","source_type": "direct"},
    {"path": ROOT / "data/direct_coinhako.json",  "source_type": "direct"},
    {"path": ROOT / "data/direct_revolut.json",   "source_type": "direct"},
    {"path": ROOT / "data/direct_coinbase.json",  "source_type": "direct"},
]

# Human-readable names for direct scraper source fields
SOURCE_DISPLAY = {
    "binance_direct":    "Binance Blog (Direct)",
    "bybit_direct":      "Bybit Blog (Direct)",
    "okx_direct":        "OKX Blog (Direct)",
    "crypto_com_direct": "Crypto.com Blog (Direct)",
    "coinhako_direct":   "Coinhako Press (Direct)",
    "revolut_direct":    "Revolut Blog (Direct)",
    "coinbase_direct":   "Coinbase Blog (Direct)",
}

# Competitors that imply a country when the country field is empty
COMPETITOR_COUNTRY_MAP = {
    "Coinhako": ["Singapore"],
}


def make_id(url: str) -> str:
    return hashlib.sha256(url.encode()).hexdigest()[:16]


def parse_dt(s: str) -> Optional[datetime]:
    if not s:
        return None
    try:
        dt = dateutil_parser.parse(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def source_name(entry: dict, source_type: str) -> str:
    raw = entry.get("source", "")
    if source_type == "direct":
        return SOURCE_DISPLAY.get(raw, raw)
    # For news aggregator, the source field IS the outlet name
    return raw


def get_competitors(entry: dict, source_type: str) -> list:
    if source_type == "direct":
        comp = entry.get("competitor", "")
        return [comp] if comp else []
    return entry.get("mentioned_competitors", [])


def get_countries(entry: dict, source_type: str) -> list:
    if source_type == "direct":
        countries = entry.get("country", [])
        if not countries:
            comp = entry.get("competitor", "")
            countries = COMPETITOR_COUNTRY_MAP.get(comp, [])
        return countries
    return entry.get("mentioned_countries", [])


def load_entries(file_cfg: dict) -> list:
    path = file_cfg["path"]
    source_type = file_cfg["source_type"]

    if not path.exists():
        log.warning("Missing input file: %s — skipping", path)
        return []

    try:
        data = json.loads(path.read_text())
    except Exception as exc:
        log.warning("Failed to parse %s: %s — skipping", path, exc)
        return []

    raw_entries = data.get("articles", data.get("entries", []))
    results = []
    for e in raw_entries:
        url = e.get("url", "").strip()
        results.append({
            "_url":         url,
            "_published_dt": parse_dt(e.get("published_date", "")),
            "_raw":         e,
            "_source_type": source_type,
        })
    return results


def transform(item: dict) -> dict:
    e           = item["_raw"]
    source_type = item["_source_type"]
    url         = item["_url"]
    dt          = item["_published_dt"]

    return {
        "id":           make_id(url) if url else make_id(e.get("title", "")),
        "title":        e.get("title", "").strip(),
        "summary":      e.get("summary", "").strip(),
        "url":          url,
        "published_date": dt.isoformat() if dt else None,
        "source_name":  source_name(e, source_type),
        "source_type":  source_type,
        "competitors":  get_competitors(e, source_type),
        "countries":    get_countries(e, source_type),
        "signal_type":  "pending",
    }


def main():
    cutoff = datetime.now(timezone.utc) - timedelta(days=CUTOFF_DAYS)
    now    = datetime.now(timezone.utc)

    # --- Load ---
    all_items = []
    for cfg in INPUT_FILES:
        items = load_entries(cfg)
        log.info("%-35s %d entries", cfg["path"].name, len(items))
        all_items.extend(items)

    total_raw = len(all_items)

    # --- Deduplicate by URL ---
    seen_urls, deduped = set(), []
    for item in all_items:
        key = item["_url"] or item["_raw"].get("title", "")
        if key not in seen_urls:
            seen_urls.add(key)
            deduped.append(item)
    duplicates_removed = total_raw - len(deduped)

    # --- Date filter ---
    no_date, too_old, kept = 0, 0, []
    for item in deduped:
        dt = item["_published_dt"]
        if dt is None:
            no_date += 1
            continue
        if dt < cutoff:
            too_old += 1
            continue
        kept.append(item)

    # --- Transform and sort ---
    entries = [transform(item) for item in kept]
    entries.sort(key=lambda e: e["published_date"] or "", reverse=True)

    # --- Build output ---
    dates = [e["published_date"] for e in entries if e["published_date"]]
    competitors = sorted({c for e in entries for c in e["competitors"]})
    countries   = sorted({c for e in entries for c in e["countries"]})

    output = {
        "generated_at":       now.isoformat(),
        "version":            "1.0",
        "total_entries":      len(entries),
        "date_range":         {
            "earliest": dates[-1] if dates else None,
            "latest":   dates[0]  if dates else None,
        },
        "competitors_covered": competitors,
        "countries_covered":   countries,
        "entries":             entries,
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(output, indent=2, ensure_ascii=False))
    log.info("Written to %s", OUTPUT_PATH)

    # --- Summary table ---
    source_counts: dict[str, int] = {}
    for e in entries:
        source_counts[e["source_name"]] = source_counts.get(e["source_name"], 0) + 1

    W = 60
    print(f"\n{'='*W}")
    print(f"  Unify Summary")
    print(f"{'='*W}")
    print(f"  Total raw entries:      {total_raw}")
    print(f"  Duplicates removed:     {duplicates_removed}")
    print(f"  Skipped (no date):      {no_date}")
    print(f"  Skipped (>12 months):   {too_old}")
    print(f"  Final entry count:      {len(entries)}")
    print(f"\n  {'Source':<32} {'Entries':>7}")
    print(f"  {'-'*(W-2)}")
    for name, count in sorted(source_counts.items(), key=lambda x: -x[1]):
        print(f"  {name:<32} {count:>7}")
    print(f"{'='*W}\n")


if __name__ == "__main__":
    main()
