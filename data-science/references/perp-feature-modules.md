# Perp-Inspired Feature Modules (Second Model)

Four feature modules ported from the `perp_strategy` project, designed for dual-model deployment.
All live in `src/features/perp_*.py`, use computed feature names prefixed `perp_*`, and are tested via `tests/test_perp_*.py`.

## 1. Funding Rate Alpha (`perp_funding_alpha.py`)

**Dual-regime approach** adapted from the perp_strategy `FundingAlpha` signal.

| Feature | Description |
|---------|-------------|
| `perp_funding_mr_long` | `-tanh(funding_zscore / 2.0)` — positive when funding very negative (shorts paying) |
| `perp_funding_mr_short` | `tanh(funding_zscore / 2.0)` — positive when funding very positive (longs paying) |
| `perp_funding_mr_raw` | `-clip(funding_zscore, -3, 3) / 3` — linear fade signal |
| `perp_funding_mom_raw` | `sign(funding_z) * momentum_20d` when `|z| < 2.0`, else 0 |
| `perp_funding_conviction` | `OI_change_1d * funding_zscore` — institutional flow conviction |
| `perp_funding_composite` | Weighted blend (0.4 mr_raw + 0.2 mom_raw + 0.2 conviction + 0.1 long + 0.1 short) |
| `perp_funding_oi_weighted` | `funding_zscore * log(OI)` — size-weighted carry signal |

**Data required:** `custom_funding_rate_zscore_7d`, `custom_open_interest`, `custom_oi_change_1d` from `derivatives.parquet`.

## 2. EGARCH-Style Vol Forecast (`perp_vol_forecast.py`)

**Volatility forecast features** adapted from the perp_strategy `EGARCHVol` signal.
Uses starter volatility features as proxy (20d and 60d) to avoid expensive GARCH fitting.

| Feature | Description |
|---------|-------------|
| `perp_vol_ewma50` | Assigns `feature_volatility_60d` (long-term vol estimate) |
| `perp_vol_ewma20` | Blend of `feature_volatility_20d * 0.6 + feature_volatility_60d * 0.4` |
| `perp_vol_realized10` | Assigns `feature_volatility_20d` (short-term realized vol) |
| `perp_vol_ratio` | `ewma50 / realized10` — forecast vs recent vol |
| `perp_vol_z` | `log(vol_ratio)` — symmetric vol deviation measure |
| `perp_vol_expansion` | `vol_ratio > 1.1` (vol expanding) |
| `perp_vol_compression` | `vol_ratio < 0.9` (vol compressing) |
| `perp_vol_momentum` | `vol_ratio * sign(momentum_20d)` — vol × direction interaction |

**Data required:** `feature_volatility_20d`, `feature_volatility_60d`, `feature_momentum_20d` (all starter features — 100% coverage).

## 3. Copula Mispricing (`perp_copula.py`)

**Relative value mispricing** adapted from the perp_strategy `CopulaMispricing` signal.
Uses Gaussian copula approximation via peer-group correlation — no pyvinecopulib needed at inference time.

| Feature | Description |
|---------|-------------|
| `perp_copula_mispricing_z` | Z-score of cumulative mispricing against peer group (60d lookback) |
| `perp_copula_mispricing_z_max` | Absolute value of mispricing z-score |
| `perp_copula_peer_deviation` | Raw mispricing = actual momentum rank − mean peer rank |
| `perp_copula_extreme_count` | 1.0 if `|z| > 2.0`, else 0.0 |
| `perp_copula_dispersion` | Standard deviation of peer ranks (uncertainty in peer group) |

**Algorithm:** For each symbol, top-3 peers by rolling Spearman correlation. Expected rank = average peer rank. Mispricing = actual − expected. Cumulative mispricing z-score over 60d.

**Data required:** `feature_momentum_20d` (100% coverage). Uses ~1263 symbols for correlation matrix.

## 4. AdaVol Adaptive Scaling (`perp_adavol.py`)

**Volatility-normalized features** adapted from the perp_strategy `AdaVol` model.
Normalizes raw features by their own EWMA forecast volatility at 3 time scales (10, 30, 60).

| Feature pattern | Description |
|----------------|-------------|
| `perp_adavol_{feat}_s{span}` | `feat / sqrt(ewma_variance(feat, span))` — stationary feature |
| `perp_adavol_fvol_{feat}_s{span}` | `sqrt(ewma_variance)` — the forecast vol itself |

**Target features:** `feature_momentum_20d`, `feature_momentum_60d`, `feature_volatility_20d`, `feature_volatility_60d`, `feature_volume_avg_20d`, `feature_volume_avg_60d`, `feature_sharpe_ratio_20d`, `feature_sharpe_ratio_60d`.

**3 spans × 8 targets × 2 features = 48 AdaVol features** (all 100% coverage from starters).

## Combined Training

`scripts/train_s2_combined.py` loads all four modules + derivative data, runs purged 5-fold CV:
1. Baseline (22 ranked starters, LambdaRank with in-fold target neutralization)
2. Combined (22 starters + all perp features, same training)

Reports neutralized CORR at λ = [0.0, 0.2, 0.5, 0.7, 1.0] with feature importance.

## Test Coverage

| Module | Tests | Status |
|--------|-------|--------|
| `perp_funding_alpha` | 8 | All pass |
| `perp_vol_forecast` | 9 | All pass |
| `perp_copula` | 7 | All pass |
| `perp_adavol` | 7 | All pass |
| **Total** | **31** | **All pass** |

## Key Design Rules
- **Never modify existing production files.** All new code goes in `perp_*.py` / `test_perp_*.py`.
- **Each feature family lives on its own git branch** (`feature/funding-alpha`, `feature/egarch-vol`, etc.) for independent testing.
- **Combined branch** `second-model` merges all feature branches via cherry-pick.
- **All features are NaN-safe** — fill with `pl.lit(0.0, dtype=pl.Float64)` as defaults.
- **Cross-sectional ranking required** — perp features get ranked per date alongside starters.
- **No lookahead** — all features use only past data at prediction time.