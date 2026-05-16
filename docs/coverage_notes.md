# Competitor Coverage Notes

## Coverage by Competitor

| Competitor | Direct Scraper | News Aggregator | Notes |
|---|---|---|---|
| Binance | `direct_binance.py` (API) | Yes | 20 entries/run via bapi JSON |
| Bybit | `direct_bybit.py` (SSR) | Yes | 20 entries/run via `__NEXT_DATA__` |
| OKX | `direct_okx.py` (API) | Yes | 20 entries/run via public REST API |
| Coinbase | `direct_coinbase.py` (Playwright) | Yes | 20 entries/run via Playwright DOM scrape |
| Crypto.com | `direct_crypto_com.py` (static JSON) | Yes | 397 total entries in CDN JSON |
| Coinhako | news_aggregator (blog RSS) | Yes (auto-tagged) | Press page stale - see below |
| Revolut | `direct_revolut.py` (Playwright) | No | Cloudflare blocks RSS; crypto filter applied |
| MooMoo | — | Yes (low-signal) | No direct scraper; rare mentions in trade press |

## Known Limitations and Filter Recommendations

### Coinspot and Swyftx — deferred to v2
Regional Australian exchanges not tracked in v1. Both have minimal coverage in
international crypto press. Require dedicated direct scrapers with custom
Playwright handling (both sites have strong bot protection). Removed from
competitor detection list to reduce noise.

### Crypto.com — delist skew
`direct_crypto_com.py` sorts by `announcedAt` descending. The most recent
20 entries frequently skew toward delisting announcements (high volume).
**Dashboard recommendation**: filter or deprioritise `category == "delist"`;
prioritise `product` and `list` categories for strategic signal.

### Bybit — promotions skew
`direct_bybit.py` pulls from the initial 20 articles in `__NEXT_DATA__`,
which skews toward the "Latest Activities" category (trading competitions,
airdrops). **Dashboard recommendation**: filter for `category == "Latest Bybit
News"` for product/regulatory signal; surface activities separately as
engagement-tier content.

### Coinhako — press page stale
`direct_coinhako.py` scrapes `press.coinhako.com`, which was last updated
May 2023. Kept as a historical reference scraper. Active Coinhako signal
comes from `news_aggregator.py` via `blog.coinhako.com/rss/` (auto-tagged
with `competitor=Coinhako, country=Singapore`).

### Australia coverage gap
The Apr 8, 2026 Coinbase AFSL licence story (first crypto exchange to receive
retail derivatives authorisation from ASIC) was missed in initial runs because:
1. No direct Coinbase scraper existed at the time.
2. RSS feed windows (20-57 articles) had aged out the story by scrape time.
3. "AFSL" keyword was not in country detection patterns.

`direct_coinbase.py` now captures this article. Consider adding `AFSL` and
`ASIC` to the Australia country detection patterns in `news_aggregator.py`.

### MooMoo — low signal
Valid fintech competitor in Singapore. Appears infrequently in international
crypto press. No direct scraper. Retained in detection list; treat any mention
as moderate signal given rarity.
