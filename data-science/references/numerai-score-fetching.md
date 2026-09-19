# Numerai Crypto Score History Fetching

How to pull official Numerai Crypto score history for all submitted models.

## Score-fetching script

`scripts/fetch_numerai_scores.py` fetches both per-day and per-round score history
for every model on the account. Saves to `data/scores/`.

Run with:
```bash
PYTHONPATH=. uv run python3 scripts/fetch_numerai_scores.py
```

Requires `PYTHONPATH=.` — the script imports `src.numerai.auth` which is not on
the path by default when running from `scripts/`.

## API methods for score fetching

### `submission_scores(model_id, ...)` — per-day granularity

Returns one row per metric per day per round. For a 20-round model with ~10 days
per round and 8 metrics, this yields ~1600 entries.

**Available metrics (Crypto tournament 12):**
- `corr` / `canon_corr` — correlation (identical values in Crypto)
- `mmc` / `canon_mmc` — model-meta contribution
- `apcwcm` — adjusted percentile weighted cumulative
- `mcwcm` — model correlation weighted cumulative
- `cwmm` — correlation weighted model mark (round-level only, ~1 per round)
- `season_score` — running season score

**Key quirks:**

1. **`resolved` is always `False` for Crypto per-day scores.** Do NOT filter
   with `resolved=True` — you will get zero results. The `resolved` flag only
   works for `cwmm` (round-level metric). Instead, filter on `value is not null`
   to identify scored entries.

2. **Multiple entries per round.** Each round has up to 10 daily score entries.
   For round-level analysis, use `distinct_on_round=True` parameter:
   ```python
   scores = api.submission_scores(model_id, display_name='corr', distinct_on_round=True)
   ```
   This returns one row per round (the latest day's score).

3. **`resolved=True` filter only returns `cwmm`.** If you need per-round corr
   scores, use `round_model_performances_v2` instead.

### `round_model_performances_v2(model_id)` — one row per round

**DEPRECATED** (emits DeprecationWarning) but the only reliable source for
round-level corr scores with percentiles and payouts. Suppress the warning:
```python
import warnings
with warnings.catch_warnings():
    warnings.simplefilter("ignore", DeprecationWarning)
    perf = api.round_model_performances_v2(model_id)
```

Each entry contains:
- `roundNumber`, `roundOpenTime`, `roundResolveTime`, `roundResolved`
- `atRisk` — NMR at stake (0.0 for both models as of July 2026)
- `corrMultiplier` — increased from 0.05 to 0.10 over the active period
- `submissionScores` — nested list with per-metric `value`, `percentile`,
  `payoutPending`, `payoutSettled` (keyed by `displayName`)

Flatten the nested `submissionScores` into columns like `corr_value`,
`corr_percentile`, `mmc_value`, etc. for DataFrame use.

## Cross-model comparison pattern

For comparing two models (e.g. m5_draft vs m5_rc):

1. Use `round_model_performances_v2` output (one row per round)
2. Pivot on `model` column with `round_number` as index
3. `drop_nulls()` to keep only rounds where both models have scores
4. Compare `corr_value`, `corr_percentile`, `mmc_value` side by side

Do NOT pivot `submission_scores` directly — the multiple-entries-per-round
structure will produce a messy pivot with more rows than rounds.

## Auth setup recap

Uses existing `src/numerai/auth.py` → `get_api()` which auto-sets
`tournament_id=12`. Needs `NUMERAI_PUBLIC_ID` and `NUMERAI_SECRET_KEY` in `.env`.
Scopes needed: `read_submission_info` (for scores) + `read_user_info` (for
`get_models()`).

## Output files

- `data/scores/submission_scores.csv` — per-day score entries (all metrics)
- `data/scores/round_performances.csv` — per-round summary with percentiles
- `data/scores/models.json` — model name → model_id mapping