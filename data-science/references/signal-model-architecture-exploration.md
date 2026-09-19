# Signal Model Architecture Exploration (June 2026)

## Models Tested

### 1. Ridge Regime (Baseline)
- **Architecture:** Per-pair Ridge regression on 12 features (6 tech + 6 regime)
- **Data:** 5m bars, 14d train, 7d val, 1d step, 6 pairs
- **Results (60d):** +3.48% return, Sharpe 0.14, MaxDD 0.62%, WR 52%
- **Results (30d, trending):** +14.26% return, Sharpe 2.15, MaxDD 0.82%, WR 53%
- **Results (60d, mixed):** -0.05% return, Sharpe 0.00, MaxDD 11.37%
- **Strengths:** Stable, low drawdown, works in trending markets
- **Weaknesses:** Linear model, bleeds in choppy markets (60d: -0.05%)

### 2. LGBM Regime (Per-Pair)
- **Architecture:** Per-pair LGBM on same 12 features
- **Params tuned:** num_leaves=63, max_depth=8, min_data=10, colsample=0.9, no regularization
- **Results (60d):** +1.79% return, Sharpe 0.07, MaxDD 3.26%, WR 50%
- **Problem:** Worse than Ridge — aggressive params overfit on 4K rows/pair
- **Conclusion:** Ridge > LGBM for small samples (<10K rows)

### 3. Pooled Cross-Sectional Rank (1h bars)
- **Architecture:** Single LGBM on cross-sectionally ranked features across 6 pairs, 1h bars
- **Features:** 8 technical (momentum 2h/4h/8h/24h, vol, RSI, volume ratio, range position)
- **Target:** 4h forward return
- **Results (90d):** +9.32% return, Sharpe 0.21, MaxDD 5.03%, WR 63%
- **Problem:** `best_iter=1` on most folds — model barely learns
- **Root cause:** Dense ranks with 6 pairs → only 6 discrete levels {0.0, 0.2, 0.4, 0.6, 0.8, 1.0}. Too coarse for tree splits on noisy targets.
- **Fix:** Use z-scores instead of ranks (continuous features)

### 4. Ensemble (Directional + Cross-Sectional + Mean-Reversion)
- **Architecture:** 
  - Head A: Per-pair Ridge (directional, regime-aware)
  - Head B: Pooled Ridge (cross-sectional, z-scored features)
  - Head C: Mean-reversion overlay (RSI extremes, Bollinger z, relative performance)
  - Regime-dependent blending weights
- **Results (30d):** 
  - With aggressive MR: -4.98% return, eliminated (MR fights trend)
  - With conservative MR (RSI >80/<20 only): +1.83% return, Sharpe 0.29
  - Baseline Ridge (no ensemble): +14.26% return, Sharpe 2.15
- **Problem:** Ensemble underperforms simple Ridge — CS and MR add noise
- **Root cause:** MR is toxic in trending markets; CS features don't add signal beyond directional

### 5. Trend Backbone + MR Leverage Adjustment (trend_mr)
- **Architecture:** 
  - Direction (1d): Ridge on regime features → LONG / SHORT / FLAT
  - Leverage (4h): MR signals (RSI, Bollinger z) → boost on pullbacks
  - Volume (4h): Deseasonalized volume → reduce on low vol (<70%), neutral otherwise
- **Data:** 5m bars, 11 pairs, same walk-forward as regime model
- **Results (30d, trending):** +13.81%, Sharpe 2.09, MaxDD 0.77%, WR 52%
- **Results (45d, mixed):** +17.49%, Sharpe 1.04, MaxDD 4.41%
- **Results (60d, mixed):** +14.80%, Sharpe 0.56, MaxDD 6.21%
- **Production status:** ✅ Implemented as `signal_bridge/backtest/trend_mr_model.py`

### 6. AdaVol Regime Detector (P1, June 7)
- **Architecture:** Adaptive EWMA on BTC squared returns with lambda adjusting to Volatility Ratio (fast_vol/slow_vol). 3 regimes: LOW_VOL(0) if vol_ratio<0.8, MED_VOL(1) if 0.8-1.2, HIGH_VOL(2) if >1.2.
- **Data:** 5m bars, 11 pairs, 30d fetch
- **Results (trend_mr + AdaVol regimes only, 30d):** +21.41% return, Sharpe 3.47, MaxDD 0.84%, WR 56%
- **Comparison vs rule-based:** +76% return (21.4% vs 12.1%), +88% Sharpe (3.47 vs 1.85), -14% MaxDD (0.84% vs 0.98%)
- **Performance:** 0.15s for 9K bars (O(n) — extract_regime_features called once, not per bar)
- **File:** `signal_bridge/backtest/regime_detector.py`
- **Runner:** `--regime-mode adavol`

### 7. Copula Mispricing Signal (P2, Experimental, June 7)
- **Architecture:** Normal GARCH(1,1) margins (returns×100, rescale=False) → PIT transform → optimal bivariate copula via pyvinecopulib → conditional CDF → cumulative mispricing z-score → LONG/SHORT/FLAT
- **Data:** 5m bars, 11 pairs, 30d fetch
- **Results (30d):** -37.47% return, Sharpe -6.57, MaxDD 37.94%, eliminated 9/9 folds
- **Problem:** Copula conditional probabilities on noisy 5m returns don't produce consistent signals. GARCH convergence unstable despite scaling. The copula structure is drowned by noise at 5m resolution.
- **Verdict:** Not production-ready at 5m. May work on daily/hourly bars.
- **File:** `signal_bridge/backtest/copula_signal.py`
- **Runner:** `--model copula`
- **pyvinecopulib v0.7.6 API quirks:** Bicop.select() not Bicop(data=...); FitControlsBicop not BicopControls; BicopFamily not FamilySet; cdf() needs (n,2) Fortran-order array. See `references/adavol-copula-signal-notes.md`.

## Comparative Results

| Model | 30d (trending) | 45d (mixed) | 60d (mixed) |
|-------|---------------|-------------|-------------|
| Base regime | +14.26% | +7.35% | **-0.05%** |
| trend_mr (rule-based regimes) | +13.81% | **+17.49%** | **+14.80%** |
| trend_mr + AdaVol regimes (P1) | +21.41% | — | — |
| trend_mr + AdaVol regimes + AdaVol sizing (P1+P3) | **+31.79%** | — | — |
| Copula mispricing (P2) | -37.47% | — | — |

**Key insight:** trend_mr is the production model for mixed conditions. Base regime wins only in strongly trending markets (30d), but bleeds in chop (60d: -0.05%). trend_mr outperforms on mixed conditions by 2-3×.

## Key Insights

### 1. More Pairs ≠ Better
- 6 pairs (BTC, ETH, SOL, XRP, DOGE, ADA): robust across conditions
- 12 pairs (add TAO, ZEC, BCH, LINK, XMR, LTC): better in trends (+14.26% vs +3.48% in 30d), worse in chop (+0.03% vs +3.48% in 60d)
- **Why:** All pairs use BTC-based regime. XMR/ZEC/XRP don't correlate with BTC → regime features are noise for them.
- **Solution needed:** Pair-specific regime detection or dynamic pair selection (only trade pairs with BTC correlation >0.7)

### 2. Mean-Reversion Must Be Regime-Gated
- MR fades momentum (shorts overbought, longs oversold) → fights trends
- Even with regime-gating (MR weight 0.1 in trending, 0.4 in choppy), MR activates too often
- Result: high WR (69%) but losses > wins (fades strong moves)
- **Fix:** Only activate on extreme overextension (RSI >80/<20, Bollinger >2.5σ), weight ≤0.2, disable in trending regimes

### 3. Portfolio Leverage Explodes with Many Pairs
- 12 pairs × 0.1× leverage = 1.2× total → exceeds Vanta cap, rapid drawdown
- **Fix:** Portfolio-level caps:
  ```python
  MAX_PORTFOLIO_LEVERAGE = 1.0
  MAX_POSITIONS = 6
  PER_POSITION_CAP = 0.20
  ```

### 4. Z-Scores > Ranks for Cross-Sectional Features
- Dense ranks with N pairs → N discrete levels (too coarse for trees)
- Z-scores: `(x - median) / (MAD * 1.4826)`, clipped to [-3, 3]
- Continuous features allow finer tree splits
- With 13 pairs, z-scores provide effective granularity vs 13 discrete ranks

### 5. Ridge > LGBM for Small Samples
- Ridge (closed-form L2) handles 4K rows/pair better than LGBM
- LGBM either overfits (aggressive params) or underfits (conservative params)
- **Rule of thumb:** Use Ridge for <10K rows, LGBM for 50K+ rows (pooled models)

## Production Model: trend_mr

**File:** `signal_bridge/backtest/trend_mr_model.py`
**Run:** `--model trend_mr`

**Architecture:**
- **Direction (1d):** Ridge on regime features → LONG / SHORT / FLAT
- **Leverage (4h):** MR signals (RSI, Bollinger z) → boost on pullbacks (RSI <40 in uptrend, RSI >60 in downtrend)
- **Volume (4h):** Deseasonalized volume → reduce on low vol (<70%), neutral otherwise
- **Parameters:** BASE_LEVERAGE=0.1, MAX_LEVERAGE=0.5, MIN_LEVERAGE=0.02, TREND_ENTRY=0.0001, TREND_EXIT=0.00005

**When to use adjustments:**
- **Volume filter (reduce on low vol):** Works in all conditions — reduces noise trades. Default on.
- **MR leverage boost (pullbacks):** Works best in ranging markets with clear support/resistance. Default on.
- **MR leverage reduction (overextension):** Works in strong trends to avoid fading. Default off (fights trend).
- **Volume boost (increase on high vol):** Works best in choppy/ranging markets where volume confirms breakouts. Default off (adds noise).

## Recommended Architecture (Not Yet Implemented)

### Hybrid Model with Pair-Aware Regime
1. **Pair-specific regime detection:** Each pair gets its own regime based on its own volatility/trend, not BTC
2. **Dynamic pair selection:** Only trade pairs with rolling 30d correlation to BTC >0.7
3. **Directional Ridge (per-pair):** Main signal, regime-aware (already in trend_mr)
4. **Cross-sectional z-score overlay:** Pooled model on z-scored features, weight 0.2–0.3
5. **Conservative MR overlay:** Only on extreme overextension, weight 0.0–0.1, disabled in trends (already in trend_mr)
6. **Portfolio-level risk controls:** Max 1.0× total leverage, max 6 positions, 0.20× per-position cap

### Feature Design
- **Directional (per-pair, raw):** momentum 1h/4h/12h, vol 8h, RSI, volume ratio, regime features
- **Cross-sectional (pooled, z-scored):** momentum 1h/4h/12h/24h, vol-adjusted mom, Bollinger z, range position, volume surprise
- **Regime (per-pair, raw):** pair-specific regime (not BTC), vol regime, trend strength
- **MR (overlay, rule-based):** RSI extremes, Bollinger extremes, relative performance vs BTC

### Training Pipeline
1. Fetch 5m OHLCV for 12 pairs (skip HYPE — not on Binance)
2. Resample to 1h for cross-sectional features
3. Compute pair-specific regime (rule-based on each pair's vol/return)
4. Cross-sectional z-scoring at each timestep
5. Walk-forward: 30d train, 7d val, 1d step
6. Train per-pair Ridge (directional) + pooled Ridge (cross-sectional)
7. Blend with regime-dependent weights
8. Apply portfolio-level leverage caps

## Files Created
- `signal_bridge/backtest/pooled_rank_model.py` — Cross-sectional ranking model (1h bars, z-scores)
- `signal_bridge/backtest/ensemble_model.py` — Ensemble model (directional + CS + MR)
- `signal_bridge/backtest/trend_mr_model.py` — Trend backbone + MR leverage adjustment (production)
- All wired into `runner.py` via `--model pooled_rank`, `--model ensemble`, `--model trend_mr`

## Open Questions
1. **Pair-specific regime:** How to compute without HMM (needs 400+ days)? Use rule-based on each pair's own vol/return?
2. **Dynamic pair selection:** Rolling correlation threshold? 30d window, >0.7?
3. **Cross-sectional feature engineering:** Which features benefit most from z-scoring vs raw?
4. **Ensemble blending:** Optimal weights for directional vs CS vs MR? Regime-dependent or static?
5. **MR activation criteria:** What thresholds avoid fighting trends while still capturing mean-reversion opportunities?

## Next Steps
1. **Deploy trend_mr to signal bridge** — replace base regime as default production model
2. Implement pair-specific regime detection (rule-based, not HMM) — XMR/ZEC/XRP don't follow BTC regime
3. Add dynamic pair selection (rolling correlation filter) — only trade pairs with BTC correlation >0.7
4. Test ensemble with pair-aware regime (not BTC regime for all)
5. Benchmark trend_mr against 6-pair vs 12-pair to find optimal pair count
6. If ensemble beats trend_mr, deploy to signal bridge for live testing
