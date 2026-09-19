# LLM-Based News Sentiment Pipeline (Text-Only)

Class-level workflow for building and evaluating a news-derived sentiment signal using a local LLM. **No price data required** — evaluates signal properties purely from event-derived features.

## Architecture

```
News Source (RSS / CryptoPanic)
    ↓  ingest (feedparser / API)
Raw News Store  (day-partitioned parquet)
    ↓  LLM extraction (grammar-constrained JSON)
Extraction Cache  (content_hash + model + prompt triple key)
    ↓  point-in-time feature build
Feature Store  (per-asset, per-date, hourly bars)
    ↓  signal evaluation
Signal Properties Report  (sparsity, polarity, flags, autocorr)
```

## Key Components

### 1. LLM Extraction Cache

Cache key: `(content_hash, model_version, prompt_version)` — all three must match for a hit.

- **Directory sharding** by 2-char hex prefix of content_hash
- **Append-only, immutable parquet** — old records survive model/prompt upgrades
- **Schema:** EventRecord: item_id, content_hash, model_version, prompt_version, extracted_at, published_at, asset, event_type, polarity, magnitude, novelty, confidence, extraction_only

### 2. Point-in-Time Feature Builder

**!!! CRITICAL PITFALL — the filter MUST be inside `build_feature_vector`, not expected from the caller.**

```python
# WRONG — every hourly bar for the same asset gets IDENTICAL features:
def build_feature_vector(events, lookback_hours, bar_open_ts=None):
    return {"polarity_sum": events["polarity"].sum()}  # uses ALL events

# CORRECT — function applies PIT filter internally:
def build_feature_vector(events, lookback_hours, bar_open_ts, asset):
    visible = events_visible_at(events, asset, bar_open_ts,
                                pd.Timedelta(hours=lookback_hours))
    if visible.empty:
        return zero_feature_vector(lookback_hours)
    return {"polarity_sum": visible["polarity"].sum()}
```

**The guard:** STRICT `< bar_open_ts`. Never `<=`. An event at bar open belongs to the NEXT bar.

```python
def events_visible_at(events, asset, bar_open_ts, lookback):
    mask = (
        (events["asset"] == asset)
        & (events["published_at"] >= bar_open_ts - lookback)
        & (events["published_at"] < bar_open_ts)
    )
    return events.loc[mask]
```

### 3. Text-Only Signal Evaluation

Without OHLCV, evaluate directly on features:

| Metric | What to look for | Good signal |
|--------|-----------------|-------------|
| Sparsity | % of bars with zero events | < 50% zero-bars |
| Polarity mean | Average direction | != 0 |
| Polarity std | Feature variance | > 0.5 |
| Flag frequency | Event type triggered % | hack > 1%, reg > 5% |
| Lag-1 autocorr | Event clustering | ~0.9+ |
| Lag-24 autocorr | Daily cycle | < 0.1 |

**Typical RSS profile** (11,000 items / 7 months across 17 feeds):
- 78% zero-event hourly bars (79% for hourly), mean 1.8 events/bar
- Polarity mean ~+0.05 to +0.17 (model-dependent), std ~0.2 (mean) / ~1.5 (sum)
- Hack flag on 1.4% of bars, regulation flag on 4.3-5.2%
- Lag-1 autocorr ~0.99, Lag-24 autocorr 0.46-0.62 (model-dependent)
- Autocorrelation at lag-24 is the key quality metric: lower = less narrative stickiness
- **75% of the signal comes from 5 assets** (BTC, TRUMP, ETH, XRP, SOL)

### 4. Contamination Audit (LLM Backtest Validity)

1. **Entity redaction test:** Replace entity names (BTC → Asset_X). If distributions diverge, LLM uses parametric memory.
2. **Extraction-only ablation:** Backtest on `extraction_only=True` records. Signal collapse = edge came from inferred judgments.
3. **Temporal holdout:** Compare Sharpe before/after model training cutoff.

## LLM Prompt Design

8k context budget: ~1700 tokens for system + few-shot + grammar; ~6300 for article. Truncate body; reduce to 2 exemplars if title alone exceeds budget.

Models with pre-backtest cutoffs (e.g., Llama-3-8B, March 2023) are safer but still need the audit.

## Dependencies

| Component | Library |
|-----------|---------|
| News ingest | `feedparser` (RSS), `httpx` (API) |
| Article body | `trafilatura` |
| LLM | `llama-cpp-python` or `vllm` + `outlines` |
| Data | `pandas`, `pyarrow` |
| Signal | `scikit-learn` (Ridge) |
| Eval | `scipy`, `arch` |

## Project Reference

- `~/projects/alphasent/` — Full implementation (extraction, cache, features, backtest, live poller)
- `~/projects/alphasent/src/extraction/batch_etl.py` — Batch extraction job
- `~/projects/alphasent/src/features/builder.py` — PIT-safe feature builder (includes events_visible_at)
- `~/projects/alphasent/scripts/eval_text_pipeline.py` — Text-only signal evaluation
- `~/projects/alphasent/PLAN.md` — Full project plan with contamination audit design
- `~/projects/alphasent/ALPHA_DIAGNOSTIC.md` — Model comparison and signal diagnostic report

## NaN Handling in Pandas Extraction Loops

When iterating over pandas rows (`for _, row in df.iterrows()`), `row.get("col", "")`
does NOT return the default when the cell is `NaN`. Pandas stores missing string
values as `np.nan` (a Python `float`), not `None`.

**Symptom:** `TypeError: 'float' object is not subscriptable` when calling
`row.get("body", "")[:500]` or `str(row.get("body", "")).strip()`.

**Fix — safe-str converter before any string operation:**

```python
def _safe_str(val) -> str:
    if val is None:
        return ""
    if isinstance(val, float) and math.isnan(val):
        return ""
    if isinstance(val, bytes):
        return val.decode("utf-8", errors="replace")
    return str(val)
```

Apply at every pandas field access site in extraction loops. The `or` chain
(`"" or row.get("summary")`) is also needed because pandas `.get()` returns NaN
even when the column exists, and `"" or NaN` → `NaN` in Python.

## GDELT Data: No Title/Body

GDELT BigQuery (`gdelt-bq.gdeltv2.gkg_partitioned`) returns **metadata only**:
- `title` is always empty string
- `body` is always empty string
- Only `raw_tone` (GDELT's -100 to +100 document-level sentiment) and URL are populated

GDELT data cannot go through LLM extraction without a separate `trafilatura` article
body fetch step (async, httpx, ~20-30% failure rate on older URLs).

## Model Selection: llama3-8b vs phi4

Two models tested on the same 11K-article RSS corpus:

| Aspect | llama3-8b (Q4_K_M) | phi4 (14.6B Q6_K) |
|--------|--------------------|--------------------|
| Speed | ~2s/article | ~6s/article |
| Default event type | "macro" (63%) | "other" (49%) |
| Polarity mean | +0.169 | +0.099 |
| Polarity std | 0.534 | 0.517 |
| Confidence mean | 0.817 | 0.774 |
| Info-ratio est (polarity) | 0.165 | 0.116 |
| Lag-24 autocorr | 0.616 | 0.462 |
| Failure rate | 0% | 0.4% |

**Trade-offs:**
- `llama3-8b` defaults to "macro" (noisier but more usable)
- `phi4` defaults to "other" (49% — honest but unusable for signal)
- `phi4` decorrelates faster (lag-24: 0.462 vs 0.616) — better for predicting regime changes
- `phi4` has ~25% lower polarity amplitude
- Both suffer from the same limit: ~2 crypto articles/hour is too sparse for hourly signal
- For event-type flags (hack, regulation, listing) the models agree closely — these are the most robust signal
