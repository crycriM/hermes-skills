# Full-Cycle Backtest Results (2022–2025)

Generated 2026-06-29. Data: Binance perpetual futures, 354 tickers, 1h OHLCV aggregated from yearly parquet files. Walk-forward scheme: 120D (expand) / 60D (slide) train, 14D test, 14D step. Top-16 liquid perps per fold, $100K initial capital.

## Best Config Per Signal (4h frequency)

| Rank | Signal | Sharpe | Return | MaxDD | Trades | Win% | Verdict |
|------|--------|-------:|-------:|------:|------:|-----:|---------|
| 1 | **egarch_vol** 4h/30D | **+1.043** | **+228.1%** | 41.8% | 1,687 | 40.8% | ✅ Survives full cycle |
| 2 | momentum_reversion 4h/14D | +0.146 | -13.2% | 61.9% | 2,425 | 41.2% | ⚠️ Degraded vs 2025-only |
| 3 | pca_residual 4h/60D | -0.084 | -27.2% | 73.0% | 1,707 | 48.2% | ❌ Fails outside bull |
| 4 | dcc_correlation 4h/30D | -0.228 | -50.0% | 76.7% | 3,833 | 37.2% | ❌ |
| 5 | adavol_spread 4h/30D | -0.345 | -44.2% | 63.3% | 3,290 | 39.6% | ❌ GARCH refit loop, heavy compute |
| 6 | waveletnet_ranking 4h/30D | -0.371 | -17.8% | 21.9% | 3,864 | 38.0% | ❌ |
| 7 | cross_sectional_momentum 4h/30D | -0.548 | -79.1% | 81.9% | 3,172 | 37.1% | ❌ Trend-following hurts in 2022 |
| 8 | neighbor_rkc 4h/30D | -0.756 | -74.8% | 75.5% | 2,603 | 35.4% | ❌ |
| 9 | pci_df2006 4h/30D | -0.933 | -40.0% | 46.8% | 3,489 | 49.6% | ❌ (highest win% though) |
| 10 | rkc_ranking 4h/30D | -1.199 | -86.2% | 86.9% | 2,433 | 37.7% | ❌ |
| 11 | pairs_zscore 4h/60D | -1.206 | -44.5% | 46.9% | 719 | 42.1% | ❌ |

## Signals Producing 0 Signals (at 4h)

These signals produced 0 trades at 4h/14D–30D windows. They may work at finer frequencies or with relaxed parameters:

- vine_basket (4h/14D)
- copula_mispricing (4h/14D)
- lead_lag (4h/30D)
- regime_switching (4h/30D)

## Other Configs Tested (waveletnet_ranking)

| Freq | Lookback | Sharpe | Return | MaxDD |
|------|----------|-------:|-------:|------:|
| 12h | 30D | -0.378 | -16.2% | 34.2% |
| 4h | 30D | -0.371 | -17.8% | 21.9% |
| 4h | 60D | -0.942 | -35.5% | 41.1% |
| 1h | 30D | -0.963 | -36.1% | 36.9% |
| 1h | 60D | -1.054 | -39.0% | 40.7% |

## Key Observation

Only egarch_vol maintained positive Sharpe over the full 2022-2025 cycle (which includes the 2022 crypto bear market). Every other signal that showed Sharpe > 1.0 on 2025-only data degraded significantly. EGARCH vol-of-vol timing appears regime-robust. All ranking/ML-based signals (RKC, waveletnet, CS momentum) were negative over the full window.

## Strategy Return Correlation

Despite most strategies being negative, they are **nearly uncorrelated** — excellent diversification potential when individual signals perform well:

| Metric | Value |
|--------|------:|
| Mean pairwise rho | +0.012 |
| Median pairwise rho | +0.007 |
| Min | -0.213 (cs_momentum / pci_df2006) |
| Max | +0.308 (rkc_ranking / neighbor_rkc) |

Highest correlated pairs are from the same family: RKC/neighbor_RKC (+0.308). The most negative pair is cs_momentum / pci_df2006 (-0.213) — natural momentum vs. mean-reversion hedge.

Rolling 60-bar correlations are highly unstable (std ~0.3, ranging from -0.99 to +1.00). Pairs with the most positive mean rolling correlation: RKC/neighbor_RKC (+0.334), pairs_zscore/pci_df2006 (+0.206).

## Portfolio Combinations (common date range 2023-04 → 2026-01, 5,868 bars)

| Portfolio | Return | Ann. Vol | Sharpe | MaxDD |
|-----------|------:|---------:|------:|------:|
| Equal-weight (10 strats) | -22.3% | 17.9% | -0.502 | 30.4% |
| Sharpe-weighted (2 pos strats: egarch + momentum) | +198.5% | 53.4% | +0.944 | 40.6% |
| EGARCH only | +228.1% | ~55% | +1.043 | 41.8% |

The equal-weight portfolio diluted EGARCH's strong performance with 9 negative-strategy drags. A Sharpe-weighted or EGARCH-only deployment is strictly better on the full-cycle test. Key lesson: **do not equal-weight signals without regime-aware filtering** — bad signals destroy the portfolio during bear markets.

## Mean Position Across Strategies (per bar)

| Metric | Value |
|--------|------:|
| Mean net position (signed) | +$46,519 (slight long bias) |
| Std net position | ±$120,488 |
| Min/Max | -$401K / +$469K |
| Mean absolute position | $188,695 |
| Avg active strategies per bar | 5.9 out of 10 executed |

## Files Saved

Per-bar positions for each strategy at `strategy_outputs/<signal>__4h__<lookback>/positions_per_bar.parquet`. Each file has per-bar rows per asset plus a `__SUMMARY__` row with aggregate stats (net size, gross PnL, active positions count).

Portfolio analysis output (from `run_full_backtest.py`):
- `strategy_outputs/aligned_returns.parquet` — 5,868-bar aligned return series
- `strategy_outputs/aligned_equity.parquet` — aligned equity curves
- `strategy_outputs/correlation_matrix.csv` — full-sample correlation
- `strategy_outputs/position_series.parquet` — per-bar net/abs positions, active count
- `strategy_outputs/portfolio_analysis_final.txt` — complete text summary
