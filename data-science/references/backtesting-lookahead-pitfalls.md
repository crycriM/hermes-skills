# Look-Ahead Pitfalls in Daily Backtesting

## The Bug

Using today's close price to compute signals for today's trade, then
executing at today's close, is look-ahead bias. You're trading on
information you wouldn't have had at decision time.

## The Fix (Three Rules)

1. **Signal**: closes through `day-1` only — `closes[:day]`, not `closes[:day+1]`
2. **Entry**: yesterday's close `close[day-1]` ≈ today's open
3. **Mark**: today's close `close[day]` for PnL computation

## Reproduction

Backtest on 180 days of crypto (Dec 2025 – Jun 2026, strong bull market):

| Fix state | Return | Sharpe | MaxDD |
|-----------|--------|--------|-------|
| Before fix (look-ahead) | +252% | 11.0 | 0.75% |
| After fix | +6.4% | 1.53 | 9.6% |

The look-ahead inflated returns by ~40× and hid all drawdown risk.

## PnL Double-Counting (Secondary Bug)

Marking positions daily using `(close / entry_price - 1)` computes
cumulative PnL from entry. Adding this to cash every day applies the
same PnL repeatedly.

Fix: compute delta from previous mark:
```python
current_value = close / entry_price - 1
prev_value = pos._prev_mark / entry_price - 1
delta = current_value - prev_value
daily_pnl += leverage * delta
pos._prev_mark = close
```

Initialize `_prev_mark = entry_price` when opening a position.

## Regime Model Performance

Three signal models compared on 180 days, same backtester:

| Model | Return | Sharpe | MaxDD | Win Rate |
|-------|--------|--------|-------|----------|
| Momentum (rule-based) | +6.4% | 1.53 | 9.6% | 39% |
| HMM regime (broken on 180d) | -9.6% | -2.08 | 11.4% | 20% |
| Rule-based regime (Ridge) | +10.2% | 2.60 | 4.2% | 56% |

Rule-based regime model: Ridge regression per pair on 12 features
(6 technical + 6 regime from BTC thresholds), trained per fold.
Entry threshold 0.5%, exit threshold 0.1%, hysteresis on flips.
Base leverage 0.1×, max 0.5×, proportional to |predicted_return|.

## Claude Code Review

The PnL double-counting bug and portfolio-cap logic error were found
by Claude Code review. Setup:

```bash
mkdir -p /tmp/review && cp <files> /tmp/review/
claude --model claude-sonnet-4-20250514 --max-turns 10 \
  -p "$(cat review_prompt.md)"
```

Review prompt should specify: PnL math, position management, fees,
walk-forward isolation, edge cases. Be specific about what to check.
