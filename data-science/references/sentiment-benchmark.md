# Sentiment Feature Integration Results

Session: 2026-06-04
Model: LGBM (tuned defaults: depth=3, leaves=15, lr=0.02, n_est=2000)
CV: Purged 5-fold, 25d purge, 5d embargo

## Data

Coinybubble global crypto sentiment index (`data/coinybubble_1h.csv`):
- 5,140 hourly rows, 2025-10-29 → 2026-06-01
- Range: 31–73 (0–100 scale), mean=57.8, median=59.1
- Resampled to 216 daily values (daily close)
- 134 of 1,654 Numerai training dates covered (8.1%)

## Features

5 global sentiment features — same value for all symbols on a date:

| Feature | Description | Coverage |
|---------|-------------|----------|
| `sentiment_level` | Raw daily close (30–73) | 8.2% of rows |
| `sentiment_change_5d` | 5-day raw change | 7.8% |
| `sentiment_change_20d` | 20-day raw change | 6.5% |
| `sentiment_zscore_90d` | Z-score over 90d rolling window | 2.8% |
| `sentiment_volatility_20d` | Rolling std of 1d changes | 5.3% |

Missing dates filled with 0.0 (sentinel for "no data").

## Results

Compared to starter-only baseline (22 features):

| λ | Starter-only | +Sentiment (27 feat) | Δ |
|---|---|---|---|
| raw | 0.1333 ± 0.019 | 0.1288 ± 0.023 | -0.0045 |
| 0.5 | 0.0669 ± 0.018 | 0.0678 ± 0.019 | +0.0009 (+1.3%) |
| 1.0 | 0.0269 ± 0.016 | 0.0282 ± 0.015 | +0.0013 (+4.8%) |

Full comparison (starter + all custom + sentiment = 66 features):
- Raw CORR decreased slightly (-0.0045) due to noise from low-coverage features
- λ=0.5 improved by +0.0009
- λ=1.0 improved by +0.0013
- λ=1.0 Sharpe improved from 1.639 → 1.870 (+14%)

## Feature Importance

Sentiment features rank 34–56 out of 57 total features:
- `sentiment_volatility_20d`: rank 34, importance 0.0086
- `sentiment_zscore_90d`: rank 41, importance 0.0065
- `sentiment_level`: rank 42, importance 0.0065
- `sentiment_change_5d`: rank 49, importance 0.0041
- `sentiment_change_20d`: rank 56, importance 0.0017

## Key Design Rule

Sentiment features are GLOBAL (same value for all symbols per date). They must NOT be cross-sectionally ranked — ranking a constant gives every symbol the same rank (degenerate). Keep them raw; tree models handle mixed scales natively. Module: `src/features/sentiment.py`.

## Data Refresh

Sentiment CSV is updated via `projects/cexdex_data_fetcher/datafeed/sentiment_data.py`:
```bash
uv run python3 projects/cexdex_data_fetcher/datafeed/sentiment_data.py \
    projects/numerai/numerai-crypto-bot/data/coinybubble_1h.csv
```
This calls Coinybubble API, fetches 32d hourly, merges duplicates, atomically replaces the CSV.
