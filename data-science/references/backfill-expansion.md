# Backfill Expansion Reference

## Symbol mappings

The `src/universe/override.csv` maps 110 ucids to coingecko_id, ccxt_pair, and cmc_slug. Only entries with valid Binance Futures perpetual pairs (USDT-margined) can be backfilled for funding rate/OI data.

**Valid pairs count**: 98 of 110 entries have active Binance Futures markets (checked via `ccxt.binance().load_markets()`).

**Skipped**: Stablecoins (USDT, USDC, DAI, BUSD, TUSD, FDUSD, PAXG) and symbols without futures pairs.

## Data sources and coverage

| Source | Provider module | Backfill script | JSON column | Symbol count | Rows (latest) | Time range |
|--------|----------------|-----------------|-------------|-------------|---------------|------------|
| Derivatives | `src/data_sources/derivatives.py` | `backfill_binance.py --symbols 98` | `derived` | 89 (9 failed) | 136,825 | 2020-01-01 → 2026-04-30 |
| On-chain | `src/data_sources/defillama.py` | `backfill_defillama.py` | `onchain` | 39 | 58,953 | Same |
| GitHub | `src/data_sources/github_dev.py` | `backfill_github.py` | `social` | 39 repos (17 active) | 782 | Variable |
| Market (OHLCV) | `src/data_sources/market.py` | via MarketDataProvider | `market` | 0 (not yet backfilled) | 0 | — |

## Derivatives features stored in JSON

```json
{
  "funding_rate": 0.00014527,
  "funding_rate_avg_7d": 0.00008210,
  "funding_rate_zscore_7d": 1.234,
  "open_interest": 1456789012.34,
  "oi_change_1d": 0.0045,
  "oi_change_7d": 0.0230,
  "oi_volume_ratio": 0.789
}
```

## On-chain features stored in JSON

```json
{
  "tvl": 4567890123.45,
  "tvl_change_1d": 0.0120,
  "tvl_change_7d": 0.0450,
  "tvl_change_30d": 0.0980
}
```

## GitHub features stored in JSON

```json
{
  "weekly_commits": 45,
  "total_stars": 12345,
  "total_forks": 6789,
  "open_issues": 234,
  "contributor_count": 89,
  "language": "Rust"
}
```

## Coverage impact on model performance

After expansion (June 2026 session): derivatives 89 symbols, on-chain 39, GitHub 17 active. Overall custom feature coverage: **12.9%** of 489,796 training rows have non-zero custom data (up from 7.8% before expansion). Advanced features including rocket (6 features) bring total to 58 features.

**Latest training results with TUNED params** (58 features, `max_depth=3, num_leaves=15, lr=0.02`):

| λ | Starter-only | + All advanced | Δ |
|---|---|---|---|
| Raw | 0.1334 ± 0.019 | 0.1286 ± 0.025 | −0.005 |
| 0.5 | 0.0669 ± 0.019 | 0.0681 ± 0.021 | **+0.001** |
| 1.0 | 0.0269 ± 0.016 | 0.0284 ± 0.016 | **+0.002 (+5.6%)** |

*(Tuned params from purged-CV hyperparameter sweep — shallower trees, faster learning.)*

**Default params results (reference, before tuning):**

| λ | Starter-only | + All advanced | Δ |
|---|---|---|---|
| Raw | 0.1233 ± 0.031 | 0.1153 ± 0.029 | −0.008 |
| 0.5 | 0.0642 ± 0.019 | 0.0610 ± 0.020 | −0.003 |
| 1.0 | 0.0259 ± 0.017 | 0.0264 ± 0.016 | **+0.001** |

*(Simple chronological split gave 0.1555 raw — 26% overestimate vs purged CV.)*

Advanced features in top-20 importance: `rocket_vol_expansion` (#3), `fd_tvl_growth_gap_30d` (#4), `rocket_risk_adj_momentum` (#7), `rocket_breakout_intensity` (#8), `rocket_volume_conviction` (#11), `fd_tvl_mcap_log` (#14). Rocket features dominate with 4 entries in top 20 — all 100% coverage, no external data needed.

## Parquet export: DuckDB → .parquet (mandatory)

Backfill scripts write to `data/pit_store/features.duckdb`. Training scripts (`train_all_features.py`, `train_with_custom_features.py`) read from `data/pit_store/*.parquet`. After any backfill run, export is required:

```python
uv run python3 -c "
import polars as pl
from src.pit_store.schema import SchemaManager
schema = SchemaManager('data/pit_store/features.duckdb')
conn = schema.get_connection()
for source in ['derivatives', 'github', 'defillama']:
    df = conn.execute(f'SELECT * FROM features WHERE source = ?', [source]).pl()
    df.write_parquet(f'data/pit_store/{source}.parquet')
    print(f'{source}: {len(df)} rows exported')
"
```
