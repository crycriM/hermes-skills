---
name: alphasent-rss-ingest
description: Survivorship-bias-free crypto news data pipeline with RSS feeds, GDELT BigQuery, per-month perimeter ticker pre-filter, LLM event extraction, and feature building.
---

# AlphaSent Crypto News Data Pipeline

Combines RSS forward-ingest (live, ~500 items/day) with GDELT BigQuery
historical backfill (~340K records for 1 year) into a unified parquet store
for LLM-based event extraction and feature engineering.

## Pipeline Architecture

```
                    +------------------+
                    |  GDELT BigQuery  |
                    |  (historical)    |  data/news/*.parquet
                    +--------+---------+
                             |
                    +--------v---------+
                    |  RSS Feeds (17)  |
                    |  (forward, live) |  data/crypto_rss/normalized/*.parquet
                    +--------+---------+
                             |
                    +--------v---------+
                    | read_all_raw_news|  batch_etl.py merges all sources
                    +--------+---------+
                             |
                    +--------v---------+
                    |  LLM Extraction  |  llama3-8b -> EventRecords
                    |  (per-item,      |
                    |   content-hash   |
                    |   cache)         |
                    +--------+---------+
                             |
                    +--------v---------+
                    |  Feature Builder |  polarity, magnitude, novelty
                    +------------------+
```

## Active RSS Feeds (17 working, 1 broken)

| Source | URL | Items/run | Notes |
|--------|-----|-----------|-------|
| coindesk | coindesk.com/arc/outboundfeeds/rss/ | ~25 | |
| cointelegraph | cointelegraph.com/rss | ~30 | |
| decrypt | decrypt.co/feed | ~34 | |
| theblock | theblock.co/rss.xml | ~20 | |
| bitcoinmagazine | bitcoinmagazine.com/feed | ~10 | |
| newsbtc | newsbtc.com/feed/ | ~10 | |
| bitcoincom | news.bitcoin.com/feed/ | ~10 | |
| utoday | u.today/rss | ~89 | |
| cryptonews | crypto.news/feed/ | ~50 | Added Jul 2026 |
| cryptopotato | cryptopotato.com/feed/ | ~15 | Added Jul 2026 |
| zycrypto | zycrypto.com/feed/ | ~14 | Added Jul 2026 |
| beincrypto | beincrypto.com/feed/ | ~12 | Added Jul 2026 |
| ambcrypto | ambcrypto.com/feed/ | ~16 | Added Jul 2026 |
| dailycoin | dailycoin.com/feed/ | ~10 | Added Jul 2026 |
| blockonomi | blockonomi.com/feed/ | ~10 | Added Jul 2026 |
| bitcoinist | bitcoinist.com/feed/ | ~8 | Added Jul 2026 |
| cryptobriefing | cryptobriefing.com/feed/ | ~30 | Added Jul 2026 |
| cryptoslate | cryptoslate.com/feed/ | ? | 403 Forbidden behind Cloudflare |

**Total daily volume:** ~400-500 items (after Jul 2026 additions).

## Cron Job

```bash
hermes cron create --name alphasent-rss-ingest \
  --schedule 15m \
  --script alphasent_rss_ingest.sh \
  --no-agent \
  --deliver local \
  --workdir /home/cricri/projects/alphasent
```

Script at `~/.hermes/scripts/alphasent_rss_ingest.sh`:
```bash
cd /home/cricri/projects/alphasent
source .venv/bin/activate
python snippets/crypto_rss_ingest.py 2>&1
```

## Data Layout

```
data/
  crypto_rss/
    state.json                     # Per-feed recent_ids + last_published_at
    normalized/YYYY-MM-DD.parquet  # RSS news items (titles, summaries)
    raw_json/...json.gz            # Unprocessed per-run RSS archives
  news/
    YYYY-MM-DD.parquet            # GDELT records (no titles or body text)
  cache/
    extractions/<hash>/...parquet  # LLM extraction cache
  features/
    <asset>/YYYY-MM-DD.parquet     # Feature store from EventRecords
```

RSS schema: item_id, source, feed_name, published_at, ingested_at, title,
summary, url, source_domain, author, asset_mentions, feed_categories

GDELT schema: item_id, source, url, source_domain, published_at, ingested_at,
doc_tone, asset_mentions, raw_tone (no title or body).

## GDELT BigQuery Backfill

RSS feeds are forward-only (no archive). For depth beyond 2-3 days, use the
GDELT pipeline in `src/ingest/gdelt_fetcher.py`.
See `references/gdelt-backfill.md` for full setup.

### Body Fetch Gap (Critical)

GDELT BigQuery stores metadata only: URL, domain, GKG themes, and doc_tone.
The `title` and `body` columns in `data/news/*.parquet` are **empty strings**
for all records - the trafilatura fetch was never executed. Every GDELT
record is silently skipped by batch_etl.py (filters on non-empty title).
GDELT contributes 0 EventRecords to the feature store.

To recover GDELT bodies: use src/ingest/article_fetcher.py with trafilatura +
async httpx (expect 20-30% failure rate). ~340K URLs -> ~2-3 days continuous
fetch. After fetching, re-run batch_etl: new body text produces different
content_hash, old empty-body entries are naturally invalidated from cache.

## Perimeter Pre-Filter

On a full RSS batch (11K items, 17 feeds, 6-month span):
- About 37% match a ticker from the per-month universe -> proceed to LLM
- About 63% are skipped (no ticker found in title or summary)

Most news volume is non-ticker-specific macro commentary. Use ~37% of total
news volume as the multiplier for LLM cost estimation.

## LLM Extraction Throughput

llama3-8b (temperature=0, max_tokens=256): about 2s per extraction via
:8079/v1. The batch ETL is single-threaded (no async concurrency).

| Metric | Value |
|--------|-------|
| Perimeter match rate | ~37% of total items |
| Per-call time | ~2s |
| 3,663 new items | ~2 hours wall-clock |
| Cache re-run | Instant (zero LLM calls) |

The llama3-8b slot is shared via the :8079 router. Other requests compete;
run long batches during low-usage hours.

## Data Distribution (observed Dec 2025-Jul 2026)

About 11K RSS items across 42 days. 95% are from July 2026
(cryptobriefing.com alone is 58%). Early months (Dec-Jun) have about 464
items total. The distribution is heavily right-skewed toward recent data.

## Survivorship-Bias-Free Asset Tagging

**Problem:** The LLM extraction pipeline uses `llama3-8b`, which does not
recognize newer tokens (ONDO, HYPE, DRIFT, etc.). Using a newer model
introduces lookahead bias (a neutral LUNA article from 2021 gets negative
sentiment because the model "knows" about the 2022 collapse).

**Solution:** `src/ingest/perimeter.py` pre-scans each article against a
per-month crypto universe from `data/perimeter/` JSON files before the LLM
is called. If no ticker matches, the article is skipped entirely (saves LLM
tokens). If a ticker matches, the asset is forced to that ticker and the
LLM only handles sentiment scoring.

See `references/perimeter-universe.md` for exchange format stripping rules
and alias map maintenance.

### Universe File Format

Files at `data/perimeter/recup_perimeter_YYYY-MM-DD.json`:
```json
{
  "binancefut": ["BTCUSDT", "ETHUSDT", ...],
  "hyperliquid": ["BTC/USDC:USDC", ...]
}
```

The normalizer strips suffixes (USDT, -USDT-SWAP, /USDC:USDC) to extract
bare tickers. Exchange names change over time; the handler tolerates any key.

### Integration

`src/extraction/batch_etl.py` calls `read_all_raw_news()` to load sources,
then `load_universe(earliest_item_date)` for that month's ticker set.
For each uncached article, `match_ticker(title+body, universe)` returns a
ticker or None. Only matched articles proceed to LLM extraction.

**Monthly workflow:** Save updated perimeter file as
`data/perimeter/recup_perimeter_YYYY-MM-DD.json` before running extraction.
The code picks the closest file <= the article date automatically.

## Known Pitfalls

- **CryptoPanic free tier** - `/news/rss/` returns HTML, not RSS XML.
  Feedparser emits "bozo with no entries". Skip on free tier.
- **Cryptoslate** - `/feed/` returns 403 behind Cloudflare. No bypass.
- **Router slot contention** - llama3-8b slots are finite. Long batches
  may compete with live requests on :8079.
- **GDELT body gap** - 340K records stored but none have extractable text.
  Without trafilatura fetch, GDELT contributes zero to the feature store.
- **pandas NaN in iterrows (crash-fix pattern)** — `row.get("body", "")`
  returns `float("nan")` when a DataFrame column has NaN, not None or "".
  This crashes `compute_content_hash(title, body[:500])` with
  `TypeError: 'float' object is not subscriptable`. The fix is a
  `_safe_str()` helper that converts NaN to "" before indexing/string ops.
  This applies to ANY `.get()` on a pandas row that may contain NaN —
  title, body, published_at, item_id, etc. The helper in
  `src/extraction/batch_etl.py::_safe_str()` handles: None -> "",
  float NaN -> "", bytes -> utf-8 decode, everything else -> str().
