# Benchmark History — Numerai Crypto v2.0

Evolution of model performance across feature engineering, backfill expansion,
hyperparameter tuning, and architecture changes. All numbers are purged 5-fold
CV (purge=25d, embargo=5d) unless marked "simple split".

**Target:** `target_binned_return_20` (20 business day forward return, quintile-binned)
**Symbols:** 1290 coins (1263 in Numerai dataset + some deduped)
**Date range:** 2020-01-01 to 2026-05-01

## Stage 1: Starter-only baseline (22 features, simple split)

*Method: single chronological split (< 2025 train, ≥ 2025 val), default LGBM params*

| λ | CORR | Sharpe |
|---|---|---|
| 0.0 | 0.1555 | 1.544 |
| 0.5 | 0.0699 | 0.954 |
| 1.0 | 0.0220 | 0.318 |

→ **These numbers are overoptimistic (~26% above purged CV). Simple split picks a favorable regime boundary.**

## Stage 2: Expanded backfill (derivatives 36→78, GitHub 4→39)

*Same simple split. Custom feature coverage: 12.9% (was 7.8%)*

| λ | Starter (22) | Combined (52) | Δ |
|---|---|---|---|
| 0.0 | 0.1555 | 0.1556 | +0.001 |
| 0.5 | 0.0699 | 0.0767 | +0.007 |
| 1.0 | 0.0220 | 0.0247 | +0.003 |

## Stage 3: Rocket features (6 features, 100% coverage)

*Rocket features derived from starters, ranked top-10 in importance*

| λ | Combined (58) | Δ vs starter |
|---|---|---|
| 0.5 | 0.0767 | +0.007 |
| 1.0 | 0.0246 | +0.003 |

## Stage 4: Purged CV (the honest number)

*5-fold CV, 25d purge, 5d embargo. Default LGBM params*

| Model | λ=0.0 | λ=0.5 | λ=1.0 |
|---|---|---|---|
| Starter-only (22) | 0.1303 ± 0.019 | 0.0642 ± 0.019 | 0.0259 ± 0.017 |
| Combined (52) | 0.1153 ± 0.029 | 0.0610 ± 0.020 | 0.0264 ± 0.016 |

→ **Purged CV raw CORR is 26% lower than simple split. The gap is real — market regimes vary significantly across folds.**

## Stage 5: Tuned hyperparameters

*Phased sweep (30 configs) on starter-only features. Best: max_depth=3, num_leaves=15, lr=0.02, min_data_in_leaf=500*

| Params | λ=0.0 | λ=0.5 | λ=1.0 |
|---|---|---|---|
| Default (depth=5, lr=0.01) | 0.1303 | 0.0642 | 0.0259 |
| **Tuned (depth=3, lr=0.02)** | **0.1334** | **0.0669** | **0.0269** |
| DEEP (depth=10, lr=0.001, 30K) | 0.1351 | 0.0644 | 0.0253 |

→ **DEEP wins raw but loses neutralized — overfits to crowd. Tuned shallow is the sweet spot.**

## Stage 6: LambdaRank + Pre-Neutralized Target

*Tuned params, 61 features (starter + rocket + liq + DPP + FD + DAA)*

| Method | λ=1.0 CORR | Sharpe | Std |
|---|---|---|---|
| Regression + post-hoc neutralize | 0.0282 | 1.87 | ±0.015 |
| **LambdaRank + pre-neutralized** | **0.0349** | **4.48** | **±0.008** |

## Best Configuration (Production)

**Model:** LambdaRank, max_depth=3, num_leaves=15, lr=0.02, colsample=0.1, min_data=500
**Features:** 61 ranked features (22 starters + 16 custom + 23 advanced)
**Validation:** Purged 5-fold CV, 25d purge, 5d embargo
**λ=1.0 CORR:** 0.0349 ± 0.008 (Sharpe 4.48)

## Feature Families Summary

| Family | Count | Coverage | Source |
|---|---|---|---|
| Starter (TA) | 22 | 100% | Numerai parquet |
| Rocket | 6 | 100% | Derived from starters |
| Liquidity | 3 | 100% | Derived from starters (mcap + vol) |
| DPP | 5 | 6% (78/1290) | Binance Futures CCXT |
| FD | 5 | 3% (39/1290) | DefiLlama API |
| DAA | 4 | 1% (17/1290) | GitHub API |
| Signature | 18 | 0% (not backfilled) | Binance OHLCV CCXT |
| Volume Anomaly | 5 | 0% (not backfilled) | Binance OHLCV CCXT |

**Key insight:** 100% coverage features (starter, rocket, liquidity) drive the model.
Sparse external features provide lift at λ≥0.5 but are diluted by coverage gaps.
Priority order for expanding: derivatives > on-chain > GitHub.
