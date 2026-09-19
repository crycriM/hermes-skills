# Look-Ahead Fixes (June 2026)

Two additional look-ahead sources fixed beyond the classic bar-level bias
(documented in `backtesting-lookahead-pitfalls.md`).

---

## 1. Global-Percentile Regime Leak

**File:** `signal_bridge/backtest/rule_regime.py`

### Before

```python
# Compute percentile thresholds from valid data
valid = ~np.isnan(rolling_means)
valid_means = rolling_means[valid]
bull_thresh = float(np.percentile(valid_means, HIGH_PERCENTILE))
bear_thresh = float(np.percentile(valid_means, LOW_PERCENTILE))

# Assign regimes using global thresholds
for i in range(min_win, n):
    if mean_ret <= bear_thresh:
        regime_labels[i] = 0  # BEAR
    ...
```

Problem: `np.percentile(valid_means, ...)` runs on ALL data at once. The
80th percentile of a 60-day dataset can be set by events in week 8-9, but
it's used to classify bars in week 2. Regime labels at bar 500 depend on
data from bar 10,000 — clear look-ahead.

### After

```python
CENTILE_TRAIL = 4032  # ~14 days of 5m bars

for i in range(min_win, n):
    trail_start = max(min_win, i - CENTILE_TRAIL)
    trail_means = rolling_means[trail_start:i + 1]
    valid_t = ~np.isnan(trail_means)
    t_means = trail_means[valid_t]
    bull_thresh = float(np.percentile(t_means, HIGH_PERCENTILE))
    bear_thresh = float(np.percentile(t_means, LOW_PERCENTILE))

    if mean_ret <= bear_thresh:
        regime_labels[i] = 0
    ...
```

Per-bar trailing window: each regime label uses only data available up
to that bar. Performance impact for <50K bars is negligible (~2ms per
bar on a single thread; the loop is already O(n) from rolling stats).

### Detection Pattern

Look for a single `np.percentile()` call on an entire array *before*
a per-bar loop that uses the result as a threshold. That's the leak.
Move the centile computation inside the loop with a trailing window.

AdaVol (`regime_detector.py`) is immune — it uses fixed thresholds
(0.8, 1.2) and purely trailing windows in `extract_regime_features`.

---

## 2. Live Funding Rate Leak

**File:** `signal_bridge/backtest/funding_alpha.py`

### Before

```python
def make_funding_alpha_signal_fn(ohlcv_data, pairs, ...):
    exchange = ccxt.binance(...)
    funding_rates = {}
    for pair in pairs:
        # Live fetch — returns TODAY's funding rates
        rates = exchange.fetch_funding_rate_history(ccxt_symbol)
        funding_rates[pair] = rates
    # Now these TODAY rates are used for all historical bars
```

In a backtest with `--days 60`, this fetches funding rates from *right now*
and uses them to drive signals 60 days ago. Real funding rates vary widely
during that period (positive to negative and back), so this injects both
a bias and spurious precision.

### After

```python
def make_funding_alpha_signal_fn(ohlcv_data, pairs, ...,
                                 funding_rates=None):
    if funding_rates is not None:
        # Backtesting: use pre-loaded historical data
        for pair in pairs:
            rates = funding_rates.get(pair, np.array([]))
            funding_rates_cache[pair] = rates
    else:
        # Realtime: fetch live (safe in production)
        exchange = ccxt.binance(...)
        for pair in pairs:
            rates = exchange.fetch_funding_rate_history(...)
            funding_rates_cache[pair] = rates
```

The `funding_rates` parameter lets callers pass historical funding data
aligned to the backtest period. The live fetch path is preserved for
realtime production use.

### Detection Pattern

Any `ccxt.fetch_*`, REST GET, or WebSocket subscription inside a signal
factory function that's called during backtest setup. All data sources
for backtesting must be pre-loaded and aligned to the historical window.

Broader rule: backtesting is a *simulation* with a fixed information
horizon. Every data point that enters the model must have existed at
the simulation time. Live API data violates this by definition.