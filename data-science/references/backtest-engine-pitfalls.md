# Backtest Engine Pitfalls

Pitfalls discovered while debugging the metalai and taoshi-miner backtest
engines. These are engine-level issues — independent of signal logic.

## Forward-Fill Phantom Bars (Critical)

**Root cause:** Calling `pd.date_range(start, end, freq="h")` on sparse
intraday data (markets close on weekends/holidays) and then forward-filling
(`reindex(method="ffill")`) creates phantom bars with identical prices.

**Symptom chain:**
1. Phantom bars have `pct_change() ≈ 0` → near-zero realized volatility
2. `target_vol / forecast_vol` ratio becomes enormous → no damping
3. `base_size = signal * vol_ratio * portfolio / price` explodes
4. Returns inflate by 10–100× with 20–30% win rates

**Fix:** Use native timestamp intersection only, never synthetic date_range:

```python
# WRONG — creates phantom bars
full_index = pd.date_range(common_start, common_end, freq="h")
df = df.reindex(full_index, method="ffill")

# CORRECT — use actual timestamps
common = df1.index.intersection(df2.index)
# … iterate common, not a date_range
```

**Detection:** Check bar counts. If `len(aligned) > max(len(raw_df) for raw_df in data)`,
you have phantom bars. Also: `returns.std()` near zero for assets that should have
meaningful vol.

## Integer Position vs Datetime Indexing

When the engine iterates over a synthetic date_range but data uses `iloc[idx]`,
bars beyond the data length return `None` prices — silently skipping most bars.
Fix: use `df.loc[dt]` throughout (prices, returns, vol, ATR).

## NaN from Empty Containers

`np.mean([])` returns `NaN` in NumPy. Common in signal modules that compute
rolling statistics on initially-empty lists.

```python
# WRONG
intraday_ret = np.mean(self.intraday_returns.get(ticker, [0]))
# [0] is a single-element list — still computes mean, but empty list → NaN

# CORRECT
vals = self.intraday_returns.get(ticker, [])
intraday_ret = np.mean(vals) if vals else 0.0
```

Same pattern for `np.std([])`, `np.median([])`, etc.

## NumPy 2.x `erf` Moved

NumPy 2.x removed `np.erf` from the top-level namespace. Use `math.erf`:

```python
import math
norm_cdf = 0.5 * (1.0 + math.erf(x / 1.4142135623730951))
```

## Position Sizing with High-Priced Assets

For assets priced in thousands (metals, indices), `base_size = vol_ratio * portfolio / price`
produces tiny unit counts (e.g., 0.1 units of gold). If the engine treats 1 unit = 1 oz
and price is per-oz, 0.1 oz at $3000 is only $300 exposure — too small.
But if the contract multiplier is missing (1 GC contract = 100 oz = $300K notional),
the sizing formula must account for it. Always verify:

1. What does 1 unit represent in dollar terms? (price × multiplier)
2. Does `max_position_pct` limit dollar exposure or unit count?
3. Is `forecast_vol` annualized correctly for the data frequency?

**Quick sanity check:** Trade count should be reasonable. 5000+ trades on 5000 bars
with 6 assets means every bar is trading — likely position sizing is too large and
the engine is constantly rebalancing.
