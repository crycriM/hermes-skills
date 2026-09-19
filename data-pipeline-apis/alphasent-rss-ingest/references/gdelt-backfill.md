# GDELT BigQuery Backfill — Setup & Quirks

GDELT GKG (`gdelt-bq.gdeltv2.gkg_partitioned`) is a public BigQuery dataset
indexing news articles from thousands of sources daily. It provides URL, source
domain, GKG themes, and a `V2Tone` sentiment score — but NOT titles or bodies.
Bodies must be fetched separately (or skip the fetch if using `doc_tone` directly).

## Prerequisites

```bash
uv add google-cloud-bigquery db-dtypes
```

A **service account** JSON key (`type: service_account`) with **BigQuery User**
(`roles/bigquery.user`) on a GCP project that has the BigQuery API enabled.

**Do NOT use an OAuth 2.0 desktop client ID** — those require interactive browser
auth and fail headless. The key must have `"type": "service_account"` and contain
a `private_key` field.

Place the key at the project root (auth.json). Point to it with:

```bash
export GOOGLE_APPLICATION_CREDENTIALS="$PWD/auth.json"
```

## Critical GDELT Query Quirks

### 1. DATE field is an integer, not a timestamp

GDELT's `DATE` column is a `YYYYMMDDHHMMSS` integer (e.g. `20260706053000`).
**Do NOT cast with `TIMESTAMP_MICROS()`** — integer overflow will crash the query.
Instead, parse it as a string:

```sql
PARSE_TIMESTAMP('%Y%m%d%H%M%S', CAST(DATE AS STRING)) AS crawl_ts
```

### 2. Project ID must be yours, not gdelt-bq

The BigQuery client must point to **your** project (where you have billing).

```python
client = bigquery.Client(project="your-project-id")
```

The query references `gdelt-bq.gdeltv2.gkg_partitioned` as the source, but
the job runs under your project. Using `project="gdelt-bq"` will fail with
`bigquery.jobs.create permission` even though the GDELT dataset is public.

Default in code: change `GDELT_PROJECT_ID` from `"gdelt-bq"` to your project.

### 3. Theme matching: use ECON_BITCOIN, not CRYPTOCURRENCY

The GKG `V2Themes` column is a semicolon-separated string of `THEME_NAME,SCORE`
pairs (e.g. `"ECON_BITCOIN,135;ECON_BITCOIN,321;...;TAX_ECON_PRICE,910"`).

- `ECON_BITCOIN` is the reliable crypto indicator (~900+ matches/day)
- `ECON_CRYPTOCURRENCY` may also work (less tested)
- `V2Themes LIKE '%CRYPTOCURRENCY%'` matches **zero rows** — don't use it

```sql
REGEXP_CONTAINS(V2Themes, 'ECON_BITCOIN')
```

### 4. Domain allowlist catches what themes miss

Many crypto articles from major publishers lack crypto themes but match by domain:

```sql
REGEXP_CONTAINS(DocumentIdentifier,
    r'coindesk\.com|cointelegraph\.com|decrypt\.co|'
    r'theblock\.co|bitcoinmagazine\.com|cryptoslate\.com')
```

Combined theme + domain filter yields ~1,400 records/day vs ~310 from themes alone.

### 5. V2Tone format

`V2Tone` is a comma-separated string with 7 fields:
`tone,positive,negative,polarity,activity_ref,self_ref,word_count`

Extract just the composite tone score (-100 to +100) with:

```sql
CAST(SPLIT(V2Tone, ',')[OFFSET(0)] AS FLOAT64) AS doc_tone
```

### 6. Timestamp handling in Python

GDELT returns tz-aware `datetime64[us, UTC]` Timestamps from BigQuery. Handle
conversion carefully in `_to_raw_news_item()`:

```python
crawl_ts = row["crawl_ts"]
if not isinstance(crawl_ts, pd.Timestamp):
    crawl_ts = pd.Timestamp(crawl_ts)
if hasattr(crawl_ts, 'tz') and crawl_ts.tz is None:
    crawl_ts = crawl_ts.tz_localize("UTC")
elif hasattr(crawl_ts, 'tz'):
    crawl_ts = crawl_ts.tz_convert("UTC")
```

### 7. GDELT records have no title

The GKG table does not include `title` or `body`. The converter sets
`title=""` and `body=""`. This matters for LLM extraction (works on title+body
which are both empty). Either use `doc_tone` directly as a feature, or run the
body fetcher (`article_fetcher.py` in `src/ingest/`) to crawl URLs.

## Running the Backfill

```python
from src.ingest.gdelt_fetcher import backfill_gdelt

# Dry run
backfill_gdelt(start_date="2025-07-01", end_date="2025-09-01",
               batch_days=30, dry_run=True)

# Full backfill — 30-day batches stay within free tier
backfill_gdelt(start_date="2025-07-01", end_date="2026-07-01",
               batch_days=30)
```

Typical yield: ~900-1,400 records/day, ~340K records/year. Each 30-day batch
takes ~60-90 seconds. Total backfill for 1 year: ~10-15 minutes.

## Output

Records are written to `data/news/YYYY-MM-DD.parquet` (day-partitioned, same
namespace as RSS normalized data). Loaded together by
`batch_etl.read_all_raw_news()` which checks three locations:
- `data/news/` (GDELT)
- `data/crypto_rss/normalized/` (RSS)
- `data/cryptopanic/normalized/` (if configured)

## Cost

GDELT GKG is ~300-500 GB/month. The domain/themes WHERE clause dramatically
reduces data scanned — ~1,400 rows/day out of ~300K/day total. Stays well
under BigQuery free tier (1 TB/mo).
