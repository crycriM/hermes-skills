# Regime Beta Features — Benchmark

## Overview

Per-coin regime sensitivity features computed from trailing-window target statistics.
Each feature captures how a coin historically performed in each market regime.

**Module:** `src/features/regime_beta.py`
**Training:** `scripts/train_regime_beta.py`

## Feature Design

7 features, all per-coin and per-date (cross-sectionally ranked):

| Feature | Description | Computation |
|---|---|---|
| `regime_beta_bull_mean` | Mean target in BULL regime | Rolling mean of masked target (bull dates only), 252d window, 25d purge |
| `regime_beta_bear_mean` | Mean target in BEAR regime | Same, bear dates only |
| `regime_beta_neutral_mean` | Mean target in NEUTRAL regime | Same, neutral dates only |
| `regime_beta_spread` | Bull - bear sensitivity | bull_mean - bear_mean |
| `regime_beta_t_stat` | Spread confidence | spread / pooled SE |
| `regime_beta_active_pct` | Fraction of lookback with active regime | Rolling fraction of bull+bear days |
| `regime_beta_consistency` | Autocorrelation of regime-adjusted returns | Rolling corr(residual[t], residual[t-7]) over 252d |

**Design decisions:**
- 252 trading day lookback (1 year)
- 25-day purge gap to avoid target horizon overlap (20 business day forward target)
- Min 10 samples required per rolling window
- Cross-sectionally ranked per date

## Results (Purged 5-fold CV)

Baseline: 22 starters + 16 custom + 23 advanced + 6 raw global = 58 features
Beta: baseline + 7 regime beta = 65 features

| λ | Baseline | +Beta | Δ | Gain |
|---|---|---|---|---|
| raw (0.0) | 0.1302 ± 0.0229 | 0.1420 ± 0.0179 | +0.0118 | +9.1% |
| 0.2 | 0.1048 ± 0.0230 | 0.1165 ± 0.0170 | +0.0117 | +11.2% |
| 0.5 | 0.0687 ± 0.0183 | 0.0784 ± 0.0171 | +0.0097 | +14.1% |
| 0.7 | 0.0506 ± 0.0163 | 0.0601 ± 0.0170 | +0.0095 | +18.8% |
| 1.0 | 0.0282 ± 0.0151 | 0.0372 ± 0.0169 | +0.0090 | +31.9% |

Gain increases with neutralization — beta features are orthogonal to starters.

## Top 20 Feature Importance

| Rank | Feature | Importance | Family |
|---|---|---|---|
| 1 | feature_volatility_20d_ranked | 0.1591 | starter |
| 2 | regime_beta_consistency_ranked | 0.0684 | BETA |
| 3 | regime_beta_neutral_mean_ranked | 0.0666 | BETA |
| 4 | feature_volatility_60d_ranked | 0.0631 | starter |
| 5 | regime_beta_bear_mean_ranked | 0.0577 | BETA |
| 6 | feature_sharpe_ratio_20d_ranked | 0.0291 | starter |
| 7 | feature_bollinger_20d_ranked | 0.0256 | starter |
| 8 | regime_beta_t_stat_ranked | 0.0244 | BETA |
| 9 | regime_beta_spread_ranked | 0.0236 | BETA |
| 10 | feature_bollinger_60d_ranked | 0.0204 | starter |

## Lookahead Bug (FIXED)

Two leakage sources found and fixed:
1. `rolling_mean()` includes current row → shift(1)
2. Numerai 20d target horizon creates overlapping windows → shift(PURGE_DAYS=25)

Before fix: impossible CORR (0.13→0.27 raw). After fix: realistic gains.
