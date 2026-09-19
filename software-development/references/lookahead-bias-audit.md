# Lookahead Bias Audit for Trading Signal Code

## When to Use

Dispatch this audit whenever a signal function or regime detector is modified or added.
The audit runs via `delegate_task` and produces a structured finding table.

## Audit Template

```python
delegate_task(
    goal="Audit {files} for lookahead bias in trading signal code",
    context=f"""
    Signal code review for lookahead bias.
    
    Execution model context:
    - Backtest engine calls signal_fn(bar, train_slice, prices)
    - train_slice = ohlcv_data[pair][bar - train_bars:bar]  (data through bar-1)
    - Execution at close[bar-1], PnL = close[bar] / close[bar-1]
    - Signal MUST only use data up to bar-1 for predictions
    
    Files to audit:
    {file_list}
    
    For each file, check:
    1. Rolling windows — are they trailing (i+1 includes current bar) or centered?
    2. Pre-computed features — computed on full dataset, but each bar's value depends only on trailing data?
    3. Target alignment — does training target fwd[d] match the PnL horizon close[bar]/close[bar-1]?
    4. Walk-forward boundaries — training data strictly before fold_start?
    5. GARCH/copula/regime fitting — data window bounded by current bar?
    
    Output structured table: FILE | LINE(S) | ISSUE | VERDICT (BIAS/SAFE)
    """,
    toolsets=["terminal", "file"]
)
```

## Common Bias Patterns Found in Practice

### Target Misalignment (most common)
```
Features at d-1 → target fwd[d] = close[d+1]/close[d]
But execution PnL = close[bar]/close[bar-1]
                              
Fix: change y_rows.append(fwd[d]) → y_rows.append(fwd[d-1])
```
Impact: ~8% return and ~1.1 Sharpe inflation on 30d 5m backtest.

### Progressive O(n²) Loops
```
for i in range(WARMUP, n_bars):
    features = extract_regime_features(ohlcv[:i+1])  # Re-computes everything
```
Fix: compute all features in one vectorized pass (they're already trailing-window based), then iterate for classification only.

### Pre-computed Features on Full Data
Features computed once on the full OHLCV array, then accessed at `[bar-1]`. This IS safe IF each bar's feature depends only on trailing data up to that bar. Verify the feature functions don't use `iloc[i+1:]` or centered windows.

### Wrong Price Data in Signal Functions
The `prices` dict in signal_fn(bar, train_slice, prices) contains {pair: float} (mark prices), not OHLCV arrays. Code that tries `prices[pair][bar-1, 4]` will crash. Use `ohlcv_data[pair]` from the closure instead.

## Findings from Real Audit (30d SN8 backtest)

22 findings across 3 files:
- 1 genuine BIAS (target misalignment in trend_mr_model.py)
- 21 SAFE (all rolling windows trailing, pre-computed features causally correct)

The bias inflated results from +23.0% to +31.8% — always run this audit before trusting backtest numbers.