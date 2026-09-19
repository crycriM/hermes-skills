# Regime-Aware Multi-Model Benchmark Results

Session: 2026-06-05
Model: LGBM (tuned defaults: depth=3, leaves=15, lr=0.02, n_est=2000)
CV: Purged 5-fold, 25d purge, 5d embargo
Features: 22 starter + 16 custom (funding, TVL) + 24 advanced (rocket, liq, DPP, FD, sentiment)

## Regime Features

7 global regime features computed from BTC daily OHLCV (CCXT Binance, 2019–2026):
- `regime_btc_return_5d`, `regime_btc_return_20d`
- `regime_btc_vol_20d`, `regime_btc_vol_60d`
- `regime_btc_drawdown_60d`
- `regime_btc_volume_ratio`
- `regime_sentiment` (Coinybubble, 0 when missing)

## Rule-Based Regime Assignment

| State | Label | Days | BTC 20d ret | Vol 20d | Max DD | Trigger |
|-------|-------|------|-------------|---------|--------|---------|
| S0 | BEAR | 814 (49%) | -7.9% | 3.2% | -20% | ret < -0.5% OR dd < -15% |
| S1 | BULL-LV | 445 (27%) | +8.9% | 2.0% | -4.5% | ret > 0.5% AND vol < median |
| S2 | BULL-HV | 395 (24%) | +15.0% | 3.4% | -4.6% | ret > 0.5% AND vol >= median |

## Results: Hard Assignment Ensemble

Each state model trained only on its state's data. Val predictions routed by state.

| λ | Single Model | Regime Ensemble | Δ |
|---|---|---|---|
| raw | 0.1302 ± 0.023 | 0.1215 ± 0.010 | -6.7% |
| 0.2 | 0.1048 ± 0.023 | 0.1017 ± 0.013 | -3.0% |
| 0.5 | 0.0687 ± 0.018 | 0.0670 ± 0.016 | -2.5% |
| 0.7 | 0.0506 ± 0.016 | 0.0494 ± 0.014 | -2.4% |
| 1.0 | 0.0282 ± 0.015 | 0.0278 ± 0.013 | -1.6% |

Note: Ensemble std is CONSISTENTLY LOWER — more stable across folds despite lower mean.

## Results: Soft Weighting Ensemble

Each state model trained on ALL data, weighted by `P(state|date)`. Blended by regime probs.

| λ | Single Model | Soft Ensemble | Δ |
|---|---|---|---|
| raw | 0.1302 ± 0.023 | 0.1176 ± 0.015 | -9.7% |
| 0.5 | 0.0687 ± 0.018 | 0.0635 ± 0.016 | -7.6% |
| 1.0 | 0.0282 ± 0.015 | 0.0264 ± 0.013 | -6.4% |

Soft weighting performed WORSE than hard assignment. Weight blending dilutes the regime signal.

## HMM Walk-Forward

GaussianHMM (diag covariance, 500 iter) retrained every 2 months on 4yr windows.
- 69 refits, 0 failures (with BTC features)
- Previously: 34 refits, many convergence warnings with funding-only features
- State distribution: 21% / 20% / 59% (requires interpretation)
- Predictions identical or worse than rule-based

## Key Findings

1. **regime_state as a feature beats separate models.** Adding `regime_state` as a raw (non-ranked) feature to the single model improved baseline from 0.1288 → 0.1302 raw CORR. This is the simplest and most effective regime integration.

2. **Confidence gating is a no-op with rule-based regimes.** One-hot probabilities → entropy=0 → confidence=1.0 → gate always picks ensemble. Only useful with HMM soft probabilities.

3. **Hard assignment beats soft weighting.** Fragmenting training data by regime hurts less than diluting the regime signal with uniform base weights.

4. **State-specific feature importance shows genuine specialization:**
   - S0 (bear): vol_60d dominates (0.147), rocket_risk_adj_momentum (0.040)
   - S1 (bull-LV): vol_60d (0.169), FD_acceleration (0.043), DPP_oi_mcap (0.028)
   - S2 (bull-HV): vol_60d (0.151), FD_acceleration (0.077), FD_growth_gap (0.030)

5. **The fundamental limitation:** Numerai's target is cross-sectionally ranked per date. Market regime provides temporal context but doesn't change which relative feature relationships predict cross-sectional rank. A tree model with `regime_state` as a feature already captures regime-conditional splits.

## Recommendations (from Claude Code Opus review)

1. **Regime×feature interaction terms** (highest expected impact): Create features like `volatility_20d × regime_prob_bear` to let a single model learn regime-conditional effects without splitting data.

2. **Crypto-specific regime features**: Add funding rate dispersion, OI growth, cross-market metrics beyond BTC-centric data.

3. **Skip confidence gating** with rule-based regimes — use HMM soft probabilities if gating is desired.
