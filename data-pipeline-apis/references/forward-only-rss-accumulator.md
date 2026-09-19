# Forward-Only RSS/News Accumulator Pattern

## Context

Many data sources (RSS feeds, firehose APIs, CryptoPanic) are **forward-only**: they
expose only the current window of items with no historical or date-range query. The
only way to build history is to start polling now and accumulate. This pattern covers
the architecture for such accumulators.

## Architecture (shared across API and RSS paths)

1. **High-water mark** — persist the newest item ID (or set of recent IDs) seen.
   Each run pages backward from "now" until it reaches the watermark. A missed run
   is harmless: the next run simply pages back further.
2. **Idempotent dedup** — items keyed by a stable ID (`cryptopanic:{post_id}` for
   API, `sha256(guid|link)` for RSS). Re-ingesting the same item is a no-op.
3. **Day-partitioned parquet** — `normalized/YYYY-MM-DD.parquet`, append-only,
   dedup at write time against existing rows in the partition.
4. **Raw JSON archive** — `raw_json/YYYYMMDDThhmmssZ.json.gz` per run. The raw
   payload is the source of truth for reprocessing; the feed is gone once it
   scrolls off.
5. **`ingested_at` vs `published_at`** — `ingested_at` (when we fetched) is the
   honest availability timestamp for live signal work. `published_at` is what the
   source reports. Always compare on `ingested_at` for latency studies.

## RSS-Specific Details

- **No auth needed** — unlike JSON APIs, RSS is public. Good for unattended cron.
- **feedparser** handles RSS 2.0 / RSS 1.0 / Atom and most namespace quirks.
- **Ticker tagging** — publisher feeds carry no currency tags. Derive
  `asset_mentions` by regex on title+summary (word-boundary, case-insensitive,
  conservative patterns to avoid false positives).
- **Per-feed watermark** — bounded LRU of recent item IDs (500 max) per feed.
  Older items fall through to storage-level dedup.

## Feed Discovery Pitfalls (verified Jun 2026)

| Feed | Issue | Fix |
|------|-------|-----|
| `cryptopanic.com/news/rss/` | Malformed XML (mismatched tag at line 91) | Drop or monitor for fix |
| `cryptoslate.com/feed/` | 403 Forbidden (blocks non-browser User-Agent) | Drop or spoof UA |
| `coindesk.com/arc/outboundfeeds/rss/` | 308 redirect to trailing-slash URL | `follow_redirects=True` handles it |
| `u.today/rss` | 301 to `rss.php` | `follow_redirects=True` handles it |

## Polling Cadence Recommendation

For crypto news (~10 msgs/hour across 8-10 feeds):
- **15 minutes** is optimal: avg latency 7.5 min, max 15 min
- Feed buffer is 20-100 items, so missing 3-4 consecutive runs is safe
- Matches GDELT's 15-min update cycle for overlap comparison
- 10 feeds × 1s pause = ~12s per run (negligible load)

## Perimeter-Based Ticker Pre-Filter

When feeding RSS articles into an LLM for extraction, most articles are not about
actively-traded crypto. A perimeter pre-filter scans each article against a
per-month crypto universe before the LLM is called:

1. **Monthly universe file** — JSON with exchange-tiered perp symbols (e.g.,
   `data/perimeter/recup_perimeter_YYYY-MM-DD.json`)
2. **Ticker normalization** — strips exchange suffixes (USDT, -USDT-SWAP, /USDC:USDC)
   to extract bare ticker names
3. **Alias resolution** — "Bitcoin" → BTC, "Solana" → SOL, "Ethereum" → ETH
4. **Skip if no match** — saves LLM tokens (63% of articles are non-crypto)

**Survivorship-bias-free:** Uses the universe from the article's publication date,
not today's list. Tokens later delisted are still matched in their era.

**Pitfall — single universe per batch:** The `_resolve_universe` function picks
one perimeter file for the entire batch (earliest article date). For multi-month
batches, chunk by month or use per-article date lookup.

## GDELT Backfill: Body Fetch Required

GDELT BigQuery (`gdelt-bq.gdeltv2.gkg_partitioned`) provides metadata only:
- `title` and `body` columns are **always empty strings**
- Only `raw_tone` (document-level sentiment, -100 to +100), URL, source domain,
  and themes are populated

To use GDELT for LLM extraction, a separate `trafilatura` async body fetch step
must be implemented. Without it, GDELT data is limited to the raw_tone signal,
which has lower discriminative power than LLM-extracted sentiment.

Expected fetch cost: ~340K URLs, ~20-30% failure rate (paywalls, link rot, 403s),
takes several hours to complete.

## Implementation Reference

Working code at `~/projects/alphasent/`:
- `crypto_rss_ingest.py` — multi-feed RSS accumulator (feedparser + httpx)
- `cryptopanic_ingest.py` — CryptoPanic JSON API accumulator (httpx, needs token)
- `test_crypto_rss_ingest.py` — 6 offline tests (synthetic XML, no network)
- `test_cryptopanic_ingest.py` — 4 offline tests (mocked API, no network)

Dependencies: `httpx pydantic pyarrow pandas feedparser`
