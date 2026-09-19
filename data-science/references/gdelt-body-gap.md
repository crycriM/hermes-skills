## Practical Data Shortfalls (observed Jul 2026)

### GDELT Body Gap

GDELT BigQuery stores metadata only: URL, domain, GKG themes, and doc_tone.
The `title` and `body` columns in `data/news/*.parquet` are empty strings
for all 340K+ records - the trafilatura fetch was never executed. Every
GDELT record is silently skipped by the batch ETL (filters on non-empty
title). GDELT contributes 0 EventRecords to the feature store.

Recovery path: article_fetcher.py with trafilatura + async httpx, expect
20-30% failure. ~340K URLs -> ~2-3 days continuous fetching.

### LLM Extraction Throughput

llama3-8b (temperature=0, max_tokens=256): about 2s per extraction via
the OpenAI-compatible API. The batch ETL is single-threaded sequential.

| Volume | Time |
|--------|------|
| 1 item | ~2s |
| 100 items | ~3 min |
| 1,000 items | ~33 min |
| 3,663 items | ~2 hours |

Cache re-runs (same model + prompt version) finish instantly.

### Perimeter Pre-Filter Efficiency

On a full RSS batch (11K items across 6 months): ~37% match a ticker,
~63% are skipped. Use this for cost estimation: budget for
~0.37 x total news volume as LLM calls.

### RSS Data Distribution

Observed distribution from Dec 2025-Jul 2026 (11K items, 42 days):
95% of items are from July 2026 only. Early months are very thin.
cryptobriefing.com alone produces 58% of all items.
