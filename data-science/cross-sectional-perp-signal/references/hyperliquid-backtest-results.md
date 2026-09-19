# Hyperliquid Backtest Results (June 2026)

Results across two data configurations on **99-100 HL perps, 90 days** using the naive equal-weight cross-sectional score.

## Fixed 4h Bars (6 bars/day, 4h spacing)

**Target:** Forward 4h return (4h horizon). **Rebalance:** Every 3 bars (12h).

| Metric | 20-name L/S | 100-name L/S |
|--------|:-----------:|:------------:|
| Ann. Return | +111% | +88.6% |
| Sharpe | 3.89 | 3.96 |
| Max DD | 8.6% | 7.9% |
| Avg IC | +0.064 | +0.013 |
| Hit Rate | 53.3% | 51.5% |

## Batch 4h Bars — LambdaRank vs Naive

**LambdaRank** (49 features, purged CV, in-fold neutralization):
- Validation IC: +0.078 (on held-out timestamps from same period)
- OOS IC: -0.008 (per-timestamp mean, 162 periods)
- Positive IC periods: 68/162 (42%)
- **Does not beat naive on 90-day window**

**Naive equal-weight score** (mean of all ranked features):
- OOS IC: +0.023 (per-timestamp mean, 162 periods)
- Positive IC periods: 91/162 (56%)

## Rolling 4h Windows from 1h Data (24 bars/day, 1h step)

**Target:** Forward 4h return from original 1h prices. **Rebalance:** Every 4 hours.

| Metric | 99-name L/S |
|--------|:-----------:|
| Ann. Return | -93% |
| Sharpe | -5.80 |
| Max DD | 20.1% |
| Avg IC | -0.020 |
| Hit Rate | 44.9% |

## Key Findings

1. **The naive equal-weight score is the best working signal** on 90 days of data. IC = +0.013 to +0.064, consistently positive across timestamps (51-56% hit rate). The 49-feature average captures genuine cross-sectional signal even without trained weights.

2. **LambdaRank overfits <500 bars** of training data. With 49 features and 56-day (336-bar) training windows, the model learns transient regime correlations that don't generalize. The LGBM infrastructure is correct — it just needs more data.

3. **Dollar-neutral mean-variance allocation improves risk metrics** vs naive equal-weight: Max DD 2.8% vs 7.9%, turnover 78% vs 140% (on 20-name test). Absolute returns are lower because Σ⁻¹ constrains factor exposure.

4. **Rolling 4h windows require correct target alignment**: the target is forward 4h return from original 1h prices, NOT deltas of overlapping rolling returns. PnL must use 1h price changes, not rolling return deltas.

5. **Sample every 4th hour for training** to handle autocorrelation from overlapping windows. Consecutive rolling 4h bars share 3/4 of price data.
