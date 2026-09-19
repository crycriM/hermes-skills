---
name: cross-sectional-perp-signal
description: "Build cross-sectional ranking signals for perpetual futures trading — adapting Numerai-style features for live venues (Hyperliquid, Binance). Covers feature architecture, data pipeline integration, target construction, walk-forward backtesting, and allocation."
triggers:
  - "cross-sectional signal"
  - "perp signal"
  - "trading signal for perps"
  - "adapt numerai signal"
  - "hyperliquid signal"
  - "live trading signal"
  - "perp ranking"
  - "binance perp backtest"
  - "0dte strategy"
  - "perp_strategy project"
  - "walkforward backtest binance"
  - "SAX tokenizer"
  - "SAX signal"
  - "symbolic aggregate approximation"
  - "markov surprise"
  - "ngram_counts"
  - "xs_sax"
  - "paa slope signal"
  - "volume plumbing perp"
---

# Cross-Sectional Perp Signal

Build a cross-sectional ranking signal for perpetual futures, adapting the Numerai Crypto tournament architecture for live trading on a specific venue.

## Trigger Conditions

Load this skill when:
- Adapting the Numerai signal for live perp trading (Hyperliquid, Binance, etc.)
- Building a new cross-sectional ranking signal from scratch for perps
- Adding features to an existing perp signal pipeline
- Setting up walk-forward backtesting for a cross-sectional perp strategy

## Hyperliquid API Notes

- **327 total perps, 257 active crypto perps** (as of June 2026)
- **Non-crypto perps** use `XYZ-` prefix (stocks: TSLA, NVDA; commodities: CL, GOLD; indices: SP500). Filter them out for crypto signal: `not markets[s]['base'].startswith('XYZ')`
- **Funding is hourly** (not 8h like Binance) — better granularity for funding alpha features
- **Rate limit:** 100 req/min. Full 100-symbol refresh takes ~2.5 min via CCXT
- **OHLCV via CCXT:** `fetch_ohlcv('BTC/USDC:USDC', '4h')` works. Symbols use `/USDC:USDC` format.
- **Funding history via CCXT:** `fetch_funding_rate_history('BTC/USDC:USDC')` — returns hourly records, ~500 max per call
- **Ticker volume:** `fetch_tickers()` returns `quoteVolume` (24h notional) for ADV ranking

## Architecture

### Core Principle: No Duplicate Data Fetching

**ALWAYS build signal modules on top of existing data infrastructure.** When a data pipeline already exists (e.g., `rankit/` for market data), the signal module should READ from it, not re-fetch.

```
signal_module/           # Signal + strategy logic (new)
    features.py          # Computes features from OHLCV
    ranking.py           # Cross-sectional rank → score
    backtest.py          # Walk-forward backtester
    allocation.py        # Mean-variance sizing

existing_data_pipeline/  # Data fetching (already exists, DO NOT duplicate)
    adapters/            # Exchange-specific fetch
    db.py                # Storage layer
    preselect.py         # Universe selection
```

If no DB exists, provide a CCXT fallback reader, but always prefer the existing pipeline.

### Feature Architecture (Mirror the Tournament Model)

When adapting the Numerai signal, mirror its feature layering:

| Layer | Role | Examples | Coverage Target |
|-------|------|----------|-----------------|
| **Technical Baseline** | Neutralization basis (equivalent to Numerai's 22 starters) | Bollinger, close avg/EWA, momentum, RSI, Sharpe, vol, volume avg/EWA | 100% (price-derived) |
| **Custom Alpha** | Orthogonal signal beyond baseline | Funding alpha, vol forecast, rocket momentum, liquidity, copula mispricing | 100% (ideally) |
| **Cross-pair** | Depends on other symbols | Copula mispricing, peer deviation | 100% (computed cross-sectionally) |

**Why mirror the tournament model:** The Numerai architecture separates signal into a "crowd" baseline (22 starters) and orthogonal custom features. This separation enables neutralization — you can measure how much alpha your custom features add beyond what everyone else sees. The same principle applies to live trading: the technical baseline captures obvious TA signal, custom features capture edge.

### Timeframe Adaptation

When adapting daily Numerai features to intraday (4h, 1h):

| Daily (Numerai) | 4h Equivalent | Formula |
|-----------------|---------------|---------|
| 20-day window | 5 bars | `daily_window / (24 / bar_hours)` |
| 60-day window | 15 bars | Same |
| Target horizon (20d) | 42 bars | `target_hours / bar_hours` |
| Purge gap (25d) | 42 bars | Must ≥ target horizon |

**Annualization factor for 4h bars:** `sqrt(6 bars/day × 365 days) ≈ 46.8`

### Cross-Sectional Ranking

Every feature must be ranked cross-sectionally per timestamp before feeding to the model. Raw feature scales are not comparable across symbols (BTC vol ≠ PEPE vol).

```python
def cross_sectional_rank(df: pl.DataFrame, feature_cols: list[str]) -> pl.DataFrame:
    result = df.clone()
    for col in feature_cols:
        result = result.with_columns(
            pl.col(col).rank("dense").over("timestamp").alias(f"{col}_ranked")
        )
    return result
```

### Target Construction

Forward return, quintile-binned per timestamp:

```python
# Forward return
df = df.with_columns(
    (pl.col("close").shift(-horizon_bars) / pl.col("close") - 1.0)
    .over("symbol").alias("target_return")
)

# Quintile binning (per timestamp)
df = df.with_columns(
    pl.col("target_return").rank("dense").over("timestamp")
    .pipe(lambda r: ((r - 1) / (r.max().over("timestamp") - 1) * 4).round() / 4)
    .alias("target_binned")
)
```

### Walk-Forward Backtester

Event-driven, no look-ahead:

```
|<── 90d training ──>|<── 12h pred ──>|  step 1
      |<── 90d training ──>|<── 12h pred ──>|  step 2
```

**Critical: delta PnL, not cumulative.** Track `prev_mark` on each position and compute only the day-over-day change. Cumulative PnL applied daily causes exponential compounding of the same unrealized return. (This bug caused +212% fake returns in the Vanta SN8 backtester — actual was +6.4%.)

```python
# WRONG — adds cumulative PnL every day:
daily_pnl = pos.leverage * (current_price / entry_price - 1.0)

# CORRECT — delta from previous mark:
current_value = direction * (mark / entry_price - 1.0)
prev_value = direction * (prev_mark / entry_price - 1.0)
delta = current_value - prev_value
daily_pnl = leverage * delta
prev_mark = mark
```

### Rolling 4h Windows from 1h Data (the "1h step" pattern)

When the spec says "4h returns with a 1h step", construct rolling 4h windows from 1h candles. Exchange-fixed 4h candles (aligned to 00:00/04:00/...) aren't what's specified — each hour a new rolling 4h window closes.

**Architecture:**

```python
# Each hour, compute the rolling 4h return:
rolling_4h_return = close / close.shift(4) - 1  # 4 hourly periods ago

# Build a "pseudo-4h bar" per hour from 1h data:
high_4h = high.rolling_max(window_size=4)
low_4h = low.rolling_min(window_size=4)
volume_4h = volume.rolling_sum(window_size=4)
open_4h = open.shift(4)
```

**Autocorrelation and training sampling.** Consecutive rolling 4h bars share 3/4 hours of price data, producing high serial correlation in targets and features. This is a **first-class design constraint, not just a nuisance:**
- For model training: sample every 4th hour (`sample_stride=4` in CV) to maintain independence. Training on adjacent 1h steps with overlapping 4h windows is label-leakage-by-overlap.
- For the purge gap: use `4 × daily_bars_needed` instead of the usual 42-bar purge.
- For IC evaluation: overlapping targets inflate or deflate IC variance. Report per-stride-sample IC as the honest metric.

**Correct PnL for rolling-window signals — critically different from fixed-bar backtests.**

**PnL must use 1h returns, NOT deltas of overlapping rolling returns.** The rolling 4h return at hour H+1 minus hour H represents only the 1 hour of new price data entering the window. Using rolling-return deltas as PnL produces massive errors:

```python
# WRONG — using overlapping return deltas as PnL:
pnl = position_weight × (rolling_ret_{H+1} - rolling_ret_H)

# CORRECT — track actual hourly price changes:
pnl = position_weight × (price_{H+1} / price_H - 1)
```

**Target alignment:** The target is forward 4h return, computed from original 1h prices:
```python
# Target = price in 4 hours / price now - 1 (using original 1h close)
feature_data.with_columns(
    (pl.col("_orig_close").shift(-4).over("symbol") / pl.col("_orig_close") - 1.0)
    .alias("target_return")
)
```

### Allocation: Full Recipe (trading_scheme.md)

The complete pipeline from cross-sectional scores to actual trades:

```python
z = norm.ppf((ranks - 3/8) / (N + 1/4))     # Blom rankits
mu_hat = ic * sigma * z                       # Grinold: alpha = IC × vol × score
aim = (1/lambda) * Sigma_inv @ mu_hat         # Markowitz aim portfolio
trade = kappa * (aim - w_prev)                # Gârleanu-Pedersen dynamic
```

#### Step 1: Ranks → Expected Returns

Blom order statistics convert ranks to Gaussian quantiles:

```python
z = norm.ppf((ranks - 3/8) / (N + 1/4))
mu_hat = ic * sigma * z   # Grinold: alpha = IC × vol × score
```

IC is measured empirically as Spearman(score, realized_return).

#### Step 2: Covariance Estimation (Ledoit-Wolf)

Use shrunk covariance to ensure invertibility and reduce estimation error:

```python
from sklearn.covariance import LedoitWolf
sigma = LedoitWolf().fit(returns_matrix).covariance_
```

#### Step 3: Aim Portfolio (Markowitz Target)

The frictionless optimum. Apply dollar-neutral constraint:

```python
w = (1.0 / risk_aversion) * sigma_inv @ mu

# Two-pass dollar-neutral (clipping breaks neutrality, re-center after)
if dollar_neutral:
    w = w - np.mean(w)
w = np.clip(w, -max_position, max_position)
if dollar_neutral:
    w = w - np.mean(w)

# Leverage cap
gross = np.sum(np.abs(w))
if gross > max_leverage:
    w *= max_leverage / gross
```

#### Step 4: Gârleanu-Pedersen Dynamic Trading

Don't trade to the full aim in one step — trade partway, damped by signal persistence and cost:

```python
# kappa = fraction of the gap to trade each period
decay = 1 - exp(-rebalance_freq / signal_half_life)  # How much signal decays
cost_damping = 1 / (1 + cost_impact / sigma_ret)      # High cost → slower
kappa = decay * cost_damping                           # Typical: 0.03–0.12

# Initial entry from zero: full kappa = 1.0
effective_kappa = 1.0 if no_current_weights else kappa

trade = effective_kappa * (aim - w_prev)
w_new = w_prev + trade
```

The `kappa` formula captured in `garleanu_pedersen_implied_kappa()` in the allocation module. Typical κ = 0.06 (trade 6% toward target per 12h rebalance with 1-week signal half-life).

#### Pitfall: Mean-variance produces net-long bias without dollar-neutral constraint

**Symptom:** Long-short portfolio has strong positive net exposure in bull markets. Short book bleeds while long book prints. Net L/S return is much lower than expected.

**Root cause:** Unconstrained `w* = (1/λ) Σ⁻¹ μ̂` does NOT guarantee dollar-neutrality. Cross-sectional scores are positively correlated with market beta. Σ⁻¹ amplifies the dominant (market) eigenvector. The optimizer tilts heavily long.

**Fix:** Apply the dollar-neutral constraint as shown above (two-pass center-clip-recenter).

**When this matters:** Any time you run mean-variance on a cross-sectional rank signal in a trending market. The longer the bull run, the worse the bias. Naive equal-weight (5% each to top-N and bottom-N) is mechanically neutral and avoids this entirely.

## Pitfalls

### Polars `rolling_corr` not available as chained Expr method

**Symptom:** `AttributeError: 'Expr' object has no attribute 'rolling_corr'`

**Root cause:** Polars `rolling_corr` exists on Series but not as a chained Expr method in the way `rolling_mean`/`rolling_std` are.

**Fix — manual covariance formula:**
```python
# Instead of: col_a.rolling_corr(col_b, window_size=W)
# Use:
result = result.with_columns([
    (col_a * col_b).rolling_mean(window_size=W, min_periods=W)
    - col_a.rolling_mean(window_size=W, min_periods=W)
    * col_b.rolling_mean(window_size=W, min_periods=W)
).over("symbol")
/ (
    col_a.rolling_std(window_size=W, min_periods=W)
    * col_b.rolling_std(window_size=W, min_periods=W)
    + 1e-10
)
```

### Dense ranks start at 1, not 0 — scores exceed [0,1]

**Symptom:** `naive_score` (mean of ranked features) produces values > 1.0.

**Root cause:** Polars `rank("dense")` assigns ranks starting at 1 (not 0). With N features averaged, the raw score ranges from N to N×max_rank, not [0,1].

**Fix — normalize to [0,1] per timestamp:**
```python
result = result.with_columns(
    pl.mean_horizontal(ranked_cols).alias("_raw_score")
)
result = result.with_columns(
    ((pl.col("_raw_score") - pl.col("_raw_score").min().over("timestamp"))
     / (pl.col("_raw_score").max().over("timestamp") - pl.col("_raw_score").min().over("timestamp") + 1e-10))
    .alias("score")
)
```

### Target binning operator precedence with Polars expressions

**Symptom:** `AttributeError: 'int' object has no attribute 'alias'`

**Root cause:** Python operator precedence: `expr.round().fill_null(0).cast(Float64) / 4` evaluates `cast(Float64) / 4` as `(cast) / 4` which is `Expr / int` → returns int, losing the chain.

**Fix — explicit parentheses around the full expression:**
```python
# WRONG:
result.with_columns(
    ((col - 1) / (max - 1) * 4).round().fill_null(0).cast(pl.Float64) / 4
    .alias("target_binned")
)

# RIGHT:
result.with_columns(
    (
        ((col - 1) / (max - 1) * 4).round().fill_null(0).cast(pl.Float64) / 4
    ).alias("target_binned")
)
```

### Market cap not available from OHLCV — use OI-weighted volume

When adapting Numerai's `feature_market_cap_avg_*` features for a perp venue, market cap is not available from OHLCV data. Substitute with OI-weighted volume (volume × open_interest) as a proxy for notional market cap. If OI is not available, use volume alone (already notional on Hyperliquid).

### Funding rate frequency differs across exchanges

- **Hyperliquid:** Hourly funding (every hour)
- **Binance:** 8-hour funding (every 8h)
- **Bybit:** 8-hour funding

When adapting features that use funding rates, adjust aggregation windows accordingly. Hyperliquid's hourly funding gives finer granularity — features like `funding_accel` (fast EMA - slow EMA) are more responsive.

### pytest-asyncio required for async tests in numerai-crypto-bot

**Symptom:** `Failed: async def functions are not natively supported`

**Fix:** `uv add --dev pytest-asyncio` in the project directory. Then async tests with `@pytest.mark.asyncio` work.

### ngram_counts performance — use ngram_total for IC checks

**Symptom:** `ngram_counts()` with A=8, n=3 produces 512 DataFrames and takes 30+ min per fold for 80-asset panels. Gate 0 evaluation never finishes.

**Root cause:** For each asset × timestamp × window position, it counts every n-gram type (A^n), builds string keys, and writes to 512 separate DataFrames. O(coins × T × W × n × A^n).

**Fix:** Use `ngram_total()` instead for IC evaluation — a single DataFrame with TOTAL n-gram counts per (time, asset) via numpy convolution. ~50× faster. Reserve full per-type `ngram_counts()` only for motif-discovery runs.

### Pandas Int64 and np.isnan incompatibility

**Symptom:** `TypeError: boolean value of NA is ambiguous` when checking `np.isnan()` on xs_sax output.

**Root cause:** xs_sax returns nullable `Int64` dtype. `np.isnan()` doesn't work on `pd.NA` — use `pd.isna()`. `valid.any()` also breaks — use `np.count_nonzero(valid)`.

### Volume plumbing — always pass volumes through fit/generate

**Symptom:** Volume-using signals produce zero-filled `logvol_24h` at inference because the harness only passes returns.

**Root cause (fixed July 2026):** The walk-forward loop passed only `train_returns` to `fit()` and `avail_returns` to `generate()`. Volume data was loaded and available but never threaded through.

**Fix:** BaseSignal.fit() and generate() now accept `volumes=` and `prices=` kwargs. run_backtest.py and run_all_backtest.py slice training/test volumes and pass them. WaveletNet's `_build_feature_window()` now computes real `logvol_24h` when volumes are available. All 15 signal generate() signatures extended with `**kwargs`.

### LambdaRank (LGBM) and the 90-day data wall

LambdaRank with 49 features **does not generalize on <1 year of data.** Tested on HL: validation IC = +0.078, out-of-sample IC = -0.008. The naive equal-weight score (IC = +0.013) outperforms LGBM on short histories.

**Root cause:** 49 features with rolling windows (5-bar, 15-bar, 42-bar) overfit to transient regime correlations in 56-day training windows. Cross-sectional patterns in crypto perps are non-stationary at short timeframes.

**Recommendation:** Use linear regression or naive equal-weight score until ≥500 bars of training data are available. The 49 features are directionally consistent even without a trained LGBM model.

### Background processes need explicit PYTHONPATH

**Symptom:** `ModuleNotFoundError: No module named 'perp_strategy'` (or any local module) when running a script via `terminal(background=true)`.

**Root cause:** The script's `sys.path.insert(0, os.path.dirname(...))` in `__main__` doesn't resolve as expected from background process CWD. Systemd/Popen/env state differs from interactive shell.

**Fix:** Always prefix background commands with `PYTHONPATH=.`:
```bash
# BROKEN (background):
python3 perp_strategy/run_all_backtest.py

# FIXED (background):
PYTHONPATH=. python3 perp_strategy/run_all_backtest.py
```
This is specific to background processes — foreground terminal() calls inherit the shell state where `sys.path` is already set. Test with a foreground call first when debugging import issues, then switch to background with `PYTHONPATH=.`.

### Heavy dependencies crash import chain (torch, tsai)

**Symptom:** Importing any module from the signals package fails even if you only need the lightweight ones. `ModuleNotFoundError: No module named 'torch'`.

**Root cause:** `signals/__init__.py` imports `waveletnet_ranking` at module level, which does `import torch` at module level (not lazy). torch is heavy (CUDA deps ~5GB) and not installed by default. Same issue exists for `tsai.all`, `arch`, `copula` — one unimportable module poisons the entire tree.

**Fix (two options):**
1. Install all deps: `pip3 install --user torch tsai arch copula scikit-learn lightgbm`
2. Import specific signals directly instead of going through `from perp_strategy.signals import *`:
   ```python
   from perp_strategy.signals.vine_basket import VineBasket  # torch-free
   # instead of:
   from perp_strategy.signals import ...  # triggers waveletnet import → crash
   ```

### Signal validation sample-period bias — always backtest across a full market cycle

**Symptom:** A signal scores Sharpe > 1.0 on a 2025-only backtest, but Sharpe drops to 0.1–0.5 or negative on 2022–2025 (full cycle including bear market).

**Root cause:** 2025 was a strong trending year. Many signals (pair spreads, momentum, ranking-based) detect and profit from trends — they naturally perform well in trending regimes but fail in choppy or declining markets. Testing on one year masks regime-dependence.

**Fix — always extend the backtest window to include at least one full bear-bull cycle:**
```python
# Minimum: include 2022 (bear) + 2023-2025 (recovery/bull)
# The 2022-2025 window is the minimum for crypto perps
BACKTEST_WINDOWS = [
    ("2022_full", "2022-01-01", "2022-12-31"),  # bear
    ("2023_full", "2023-01-01", "2023-12-31"),  # recovery
    ("2024_2025", "2024-01-01", "2025-12-31"),  # bull
]
```

**Known degradation pattern (tested on 16 signals, 4h bars, Binance perps 2022–2025):**

| Signal | 2025-only Sharpe | Full-cycle Sharpe | Verdict |
|--------|:-:|:-:|---|
| EGARCH vol | ~1.75 | **+1.04** | Survives — regime-robust vol timing |
| Momentum reversion | ~1.54 | +0.15 | Degrades — trend bias in full cycle |
| PCA residual | ~1.44 | -0.08 | Fails outside 2025 regime |
| CS momentum | ~0.79 | -0.55 | Fails — trend-following hurts in 2022 |
| RKC / waveletnet | N/A | -0.4 to -1.2 | Negative across full window |

**Lesson:** Always reject a signal that was only tested on one bull year. The edge must hold through a bear market to be real.

### Zero-signal output from spread/pair/regime signals

**Symptom:** `run_strategy` reports "N folds, 0 signals" for signals like `vine_basket`, `copula_mispricing`, `lead_lag`, or `regime_switching`. No positions opened.

**Root cause (several possible):**
1. **Pair selection gate:** Signals that select pairs via correlation threshold (e.g., `min_corr=0.6`) may find zero qualifying pairs at 4h resolution over a training window where correlations are lower than at 1h.
2. **Top-N filtering:** The liquidity-selection step + pair-selection step together can cull the universe below the signal's internal minimum before it emits any trades.
3. **Z-score thresholds:** entry_z thresholds that were calibrated on one frequency (e.g., 30min) may never fire at a coarser frequency (4h) because the signal variance compresses with longer bars.

**Diagnostic procedure:**
```python
# 1. Check whether fit() raises or produces a model
sig_gen.fit(train_returns)
print("Fitted:", sig_gen.is_fitted)

# 2. Call generate() directly on the training period tail to check output
sigs = sig_gen.generate(train_returns.iloc[-100:], train_returns.index[-90])
print(f"Direct generate(): {len(sigs)} signals")
for s in sigs[:5]:
    print(f"  {s.asset} {s.direction} strength={s.strength:.2f}")

# 3. If 0 direct signals, relax thresholds temporarily to find floor
```

**Frequency switching:** A signal producing 0 at 4h may work at 1h or 30min where more tickers have valid data per bar. However, 30min over 4yr data is 70k+ bars — factor this into runtime budget.

### Per-bar position capture requires engine instrumentation

**Problem:** The standard `BacktestResult` only saves aggregate trades (`PerpTrade`) and the equity curve. For portfolio-level analysis (mean position per bar, rolling correlation of returns, gross vs net PnL attribution), you need per-bar position snapshots.

**Fix — instrument the engine loop to record every bar's positions:**

```python
per_bar_records = []

for date in bt_dates:
    prices = test_prices.loc[date].to_dict()

    # ... standard engine loop (mark-to-market, close, open, risk checks) ...

    # Record this bar's positions:
    for pos in positions:
        per_bar_records.append({
            "timestamp": date,
            "strategy": strategy_name,
            "asset": pos.asset,
            "direction": pos.direction,
            "size_usd": pos.size_usd,
            "unrealized_pnl": pos.unrealized_pnl,
            "accumulated_funding": pos.accumulated_funding,
            "capital": capital,
            "total_equity": total_equity,
            "leverage": pos.leverage,
            "signal_score": pos.signal_score,
            "hold_days": pos.hold_days,
        })

    # Also add a __SUMMARY__ row per bar for the aggregate:
    per_bar_records.append({
        "timestamp": date,
        "strategy": strategy_name,
        "asset": "__SUMMARY__",
        "direction": "flat",
        "size_usd": sum(p.size_usd * (1 if p.direction == "long" else -1) for p in positions),
        "unrealized_pnl": gross_pnl,
        "accumulated_funding": sum(p.accumulated_funding for p in positions),
        "capital": capital,
        "total_equity": total_equity,
        "signal_score": np.mean([p.signal_score for p in positions]) if positions else 0.0,
        "hold_days": np.mean([p.hold_days for p in positions]) if positions else 0,
    })

# Save as parquet for downstream portfolio analysis
pd.DataFrame(per_bar_records).to_parquet("positions_per_bar.parquet")
```

This enables:
- **Mean position per bar** across strategies (net long/short exposure)
- **Rolling return correlation** between strategies (align by timestamp)
- **Gross vs net PnL attribution** per bar
- **Active strategy count** per bar

### Backtest signal filter too strict for small symbol counts

**Symptom:** Backtest returns 0 periods despite sufficient data.

**Root cause:** Hardcoded `if len(signal_df) < 10` skips all timestamps when testing with fewer than 10 symbols (e.g., 6-symbol smoke test).

**Fix:** Use `cfg.n_long + cfg.n_short` as the minimum:
```python
if len(signal_df) < cfg.n_long + cfg.n_short:
    continue
```

### scipy.stats.spearmanr needs ≥3 observations

**Symptom:** `ConstantInputWarning` or NaN correlation with 2-element arrays.

**Fix:** Guard with `if len(x) < 3: return 0.0` before calling `spearmanr()`.

### GP kappa: initial entry vs steady-state

**Symptom:** After first rebalance, positions are near-zero despite a clear signal.

**Root cause:** Gârleanu-Pedersen kappa = 0.03–0.12 means "trade 3-12% toward the aim portfolio per period." From zero initial weights, the first trade only opens 3-12% of the target position. If the target is 2% per name, first trade opens 0.06-0.24% — effectively nothing.

**Fix — full establishment on first entry:** Check whether any weights exist. If current weights are all zero, set kappa = 1.0 for the initial position establishment, then revert to the decayed kappa for subsequent adjustments:

```python
have_weights = any(abs(w) > 0 for w in current_weights.values())
effective_kappa = kappa if have_weights else 1.0
trade = effective_kappa * (aim - w_prev)
```

## Key Concepts

### Information Coefficient (IC)

IC = Spearman rank correlation between signal score and realized forward return, measured cross-sectionally at each timestamp.

```
IC = corr(rank(signal), rank(realized_return))
```

| IC Value | Meaning |
|----------|---------|
| 0.00 | No predictive power (random) |
| 0.01–0.03 | Weak but tradeable at scale |
| 0.03–0.05 | Good — typical quant equity fund |
| 0.05–0.10 | Strong — rare in practice |

**IC Sharpe** = mean(IC) / std(IC) — measures consistency. IC Sharpe > 0.5 is good, < 0.2 means noisy signal.

**Grinold's Fundamental Law:** `IR = IC × √breadth`. With 100 names × 2 rebalances/day × 365 days, breadth is enormous. Even IC = 0.01 compounds into meaningful alpha at that frequency.

**Measured IC on HL data:** Naive equal-weight score: IC = 0.013 (100-name) to 0.064 (20-name). LGBM-trained signal expected: IC = 0.03–0.06.

## Remaining Phases (as of June 2026)

| Phase | Status | What's left |
|-------|--------|-------------|
| 0-3 | ✅ Done | Features, backtest, allocation, GP dynamic trading — 96 tests, all green |
| 4: LGBM | ⏸️ Blocked | Needs ≥1 year of HL data. Naive equal-weight works. LGBM ported but OOS IC < naive on 90d window |
| 5: Live | TODO | Hourly signal loop, 12h execution, paper trading |
| 6: Risk | TODO | Circuit breakers, drawdown alerts, reconciliation |
| 7: Optimize | TODO | Feature ablation, horizon tuning, regime-aware alloc |

## Initial Backtest Results (June 2026, 99 perps, 90 days)

For detailed results see `references/hyperliquid-backtest-results.md`.

## Key Commands

```bash
# Run all hl_signal tests
cd ~/projects/numerai-folders/numerai-crypto-bot
PYTHONPATH=. uv run python3 -m pytest hl_signal/tests/ -v

# Fetch 100-name OHLCV for backtest
PYTHONPATH=. uv run python3 -c "
from hl_signal.data import CCXTReader
reader = CCXTReader()
syms = reader.fetch_universe()[:100]
df = reader.fetch_ohlcv_batch(syms, '4h')
df.write_parquet('/tmp/hl_backtest_100.parquet')
"

# Run backtest
PYTHONPATH=. uv run python3 -c "
from hl_signal.backtest import run_backtest, BacktestConfig, print_backtest_summary
import polars as pl
ohlcv = pl.read_parquet('/tmp/hl_backtest_100.parquet')
result = run_backtest(ohlcv, config=BacktestConfig(n_long=20, n_short=20))
print(print_backtest_summary(result))
"
```

## References

- `references/hyperliquid-backtest-results.md` — Real-data backtest results (June 2026): naive vs mean-variance comparison, IC analysis, mean-variance long bias diagnosis
- `references/binance-perp-backtest-format.md` — Binance perp yearly data format, copy from studioc, per-bar position capture technique, 0dte project structure, net vs gross PnL decomposition
- `~/projects/numerai-folders/numerai-crypto-bot/src/docs/trading_scheme.md` — Theoretical framework (Gaussian, Grinold, Gârleanu-Pedersen)
- `~/projects/numerai-folders/numerai-crypto-bot/src/docs/trading_schemes.md` — Implementation guide (HL variant)
- `~/projects/numerai-folders/numerai-crypto-bot/src/docs/hyperliquid_signal_plan.md` — Module-level design
- `~/projects/numerai-folders/numerai-crypto-bot/src/features/constants.py` — Numerai starter feature list (22 features)
- `~/projects/numerai-folders/numerai-crypto-bot/src/features/perp_*.py` — Original perp feature modules (adapted for HL)
- `~/projects/rankit/src/market_data/` — Existing market data infrastructure (reuse, don't duplicate)

## Related Codebases

### 0dte / perp_strategy — Multi-strategy Binance perp walk-forward backtest

```
~/projects/0dte/
```

16 signal modules tested against 354 Binance perps on yearly 1h OHLCV data.
Runs walk-forward grid search and portfolio combination. Signals include
vine_basket, egarch_vol, momentum_reversion, pca_residual, adavol_spread,
cross_sectional_momentum, copula_mispricing, pairs_zscore, rkc_ranking,
neighbor_rkc, waveletnet_ranking, lead_lag, pci, dcc_correlation, regime_switching.

Best configs per signal (2025 out-of-sample):
- vine_basket 4h/14D → Sharpe 1.80
- egarch_vol 30min/30D → Sharpe 1.75
- momentum_reversion 4h/14D → Sharpe 1.54
- Combined portfolio (top-8, equal weight) → Sharpe 3.38

See `references/binance-perp-backtest-format.md` for data format and per-bar capture.

**SAX signal primitives (July 2026):** See `references/sax-signal-primitives.md` for
the SAX tokenizer API, Markov surprise, n-gram counts, volume plumbing fix, and
Gate 0 IC evaluation results.

### Key Commands

```bash
# Grid search over resample × lookback
cd ~/projects/0dte
PYTHONPATH=. python3 perp_strategy/run_backtest.py

# Run with per-bar position capture (all 16 signals, portfolio analysis)
PYTHONPATH=. python3 perp_strategy/run_all_backtest.py

# Same but standalone single-file (no imports from perp_strategy package)
PYTHONPATH=. python3 run_full_backtest.py

# Portfolio combination from cache
PYTHONPATH=. python3 perp_strategy/run_portfolio.py --combine-only

# Copy data from studioc
rsync -avP studioc:/home/christian/python_working/long-short/data/bin_yearly/bin_yearly_202*.parquet ~/Python/github/data/bin_yearly/

# Install all dependencies
pip3 install --user --break-system-packages torch tsai arch copula scikit-learn lightgbm

# Multiple runs in parallel for different strategy groups
PYTHONPATH=. python3 perp_strategy/run_all_backtest.py --strategies egarch_vol momentum_reversion &
PYTHONPATH=. python3 perp_strategy/run_all_backtest.py --strategies rkc_ranking neighbor_rkc &
```
