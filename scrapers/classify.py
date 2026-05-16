"""
LLM-based signal classification for published_data/dashboard.json.

For each entry:
- Has competitors → ask Claude Haiku to classify into one of 6 signal types
- No competitors  → auto-tag as "industry_context" (no LLM call)

Results are written back in-place to published_data/dashboard.json.
Requires ANTHROPIC_API_KEY in .env (copy from .env.example).
"""

import json
import logging
import os
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import anthropic
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger(__name__)

load_dotenv()
_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

if not _API_KEY or _API_KEY == "your-api-key-here":
    print(
        "\nError: ANTHROPIC_API_KEY is not set.\n\n"
        "  1. Open .env in the project root\n"
        "  2. Replace 'your-api-key-here' with your key from https://console.anthropic.com/\n"
        "  3. Re-run:  python scrapers/classify.py\n"
    )
    sys.exit(1)

DASHBOARD_PATH = Path(__file__).parent.parent / "published_data" / "dashboard.json"
MODEL          = "claude-haiku-4-5-20251001"

# User-specified pricing for cost estimate (not official rates)
INPUT_COST_PER_M  = 0.80   # $ per 1M input tokens
OUTPUT_COST_PER_M = 4.00   # $ per 1M output tokens

SYSTEM_PROMPT = """You are a competitive intelligence analyst classifying crypto industry signals about CRYPTO EXCHANGES specifically.

Classify each entry into ONE category based on what the EXCHANGE itself is doing:

- product_launch: the exchange is launching a new product, feature, or service THEY operate (NOT new token listings - those go to "other"; NOT third-party token price movements)
- market_expansion: the exchange is entering a new country, region, or market with their own operations
- regulatory: the exchange obtained a license, regulatory approval, government engagement, compliance milestone, or is subject to regulatory action
- partnership: the exchange announced a business partnership, integration with another company, M&A, or investment
- operational: delisting, fee change, maintenance, security incident, internal policy update, or platform-level operational change
- other: anything that doesn't fit - including token price news, general industry commentary, third-party news that only mentions the exchange tangentially, market analysis, ecosystem news not specific to the exchange's own actions

CRITICAL RULES:
- If the article is primarily about a cryptocurrency TOKEN's price movement or performance (not the exchange's actions), classify as "other" even if the exchange is mentioned
- If the article is about a DIFFERENT company's actions with only tangential mention of this exchange, classify as "other"
- Only classify as product_launch / market_expansion / regulatory / partnership when the EXCHANGE ITSELF is the subject taking the action

Return only a single word: the category. No explanation."""

VALID_CATEGORIES = frozenset({
    "product_launch", "market_expansion", "regulatory",
    "partnership", "operational", "other",
})

client = anthropic.Anthropic(api_key=_API_KEY, max_retries=0)


def call_llm(title: str, summary: str) -> tuple:
    """Classify one entry via Haiku. Returns (signal_type, usage | None)."""
    user_msg = f"Title: {title}\n\nSummary: {summary}"

    for attempt in range(2):
        try:
            resp = client.messages.create(
                model=MODEL,
                max_tokens=20,
                temperature=0,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_msg}],
            )
            raw = resp.content[0].text.strip().lower().rstrip(".")
            category = raw if raw in VALID_CATEGORIES else "other"
            return category, resp.usage
        except Exception as exc:
            if attempt == 0:
                log.warning("LLM call failed (%s) — retrying in 2s...", exc)
                time.sleep(2)
            else:
                log.error("LLM call failed after retry: %s", exc)
                return "unclassified", None

    return "unclassified", None


def main():
    if not DASHBOARD_PATH.exists():
        log.error("Input not found: %s  — run scrapers/unify.py first", DASHBOARD_PATH)
        sys.exit(1)

    data    = json.loads(DASHBOARD_PATH.read_text())
    entries = data.get("entries", [])
    total   = len(entries)

    needs_llm = sum(1 for e in entries if e.get("competitors"))
    log.info(
        "%d entries: %d need LLM, %d auto-tagged as industry_context",
        total, needs_llm, total - needs_llm,
    )

    llm_count       = 0
    auto_count      = 0
    failed_count    = 0
    total_input_tk  = 0
    total_output_tk = 0
    signal_counts: Counter = Counter()

    for i, entry in enumerate(entries, 1):
        if entry.get("competitors"):
            category, usage = call_llm(entry["title"], entry.get("summary", ""))
            entry["signal_type"] = category
            llm_count += 1
            if category == "unclassified":
                failed_count += 1
            if usage:
                total_input_tk  += usage.input_tokens
                total_output_tk += usage.output_tokens
        else:
            entry["signal_type"] = "industry_context"
            auto_count += 1

        signal_counts[entry["signal_type"]] += 1

        if i % 5 == 0 or i == total:
            print(f"  Classifying {i}/{total}...")

    data["classification_run_at"] = datetime.now(timezone.utc).isoformat()

    DASHBOARD_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    log.info("Written to %s", DASHBOARD_PATH)

    input_cost  = (total_input_tk  / 1_000_000) * INPUT_COST_PER_M
    output_cost = (total_output_tk / 1_000_000) * OUTPUT_COST_PER_M
    total_cost  = input_cost + output_cost

    W = 54
    print(f"\n{'='*W}")
    print(f"  Classification Summary")
    print(f"{'='*W}")
    print(f"  Classified by LLM:         {llm_count:>4}")
    print(f"  Auto-tagged (no signal):   {auto_count:>4}")
    print(f"  Failed / unclassified:     {failed_count:>4}")
    print(f"\n  Signal type breakdown:")
    for cat, count in sorted(signal_counts.items(), key=lambda x: -x[1]):
        print(f"    {cat:<24} {count:>4}")
    print(f"\n  Tokens used:")
    print(f"    Input:   {total_input_tk:>8,}")
    print(f"    Output:  {total_output_tk:>8,}")
    print(f"\n  Estimated API cost:   ${total_cost:.4f}")
    print(f"{'='*W}\n")


if __name__ == "__main__":
    main()
