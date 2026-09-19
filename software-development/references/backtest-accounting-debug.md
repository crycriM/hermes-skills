# Backtest Accounting Debugging

## Symptom Pattern

Portfolio equity grows even though every trade taken individually shows a loss. Cash balance keeps rising with trade volume. The strategy appears to be printing money when it shouldn't.

**Root cause (most common):** The cash accounting model is wrong — typically a bug where OPEN only debits commission (not full notional), while CLOSE credits the full sale proceeds back. Every complete trade cycle injects phantom cash equal to the position notional.

**Detection:** Compare `total_realized_PnL` (sum of `trade['pnl']` for CLOSE/REDUCE trades) against the actual cash change. If cash is growing faster than realized PnL, the accounting model is wrong.

## Correct Futures-Style Accounting Model

| Action | Cash Change | Notes |
|--------|------------|-------|
| **OPEN** | `cash -= commission_only` | Full notional is NOT debited |
| **CLOSE** | `cash += qty * (exit_price - entry_price) - closing_cost` | Only realized PnL plus commission |
| **ADD** | `cash -= commission_only` | Same as OPEN |
| **REDUCE** | `cash += delta * (exit_price - entry_price) - closing_cost` | Realized PnL on reduced portion |

**Equity formula:**
```
equity = cash + sum(qty * (current_price - entry_price) for open positions)
```

This is **unrealized PnL** — NOT the full market value of positions (`qty * current_price`). The unspent notional (`qty * entry_price`) was never deducted from cash, so it must not appear in equity.

**Wrong equity formula (the bug):**
```
equity = cash + sum(qty * current_price)
```
This double-counts the entry basis and inflates equity the moment a position is opened.

## Cash Flow Trace — Diagnostic Pattern

Build a focused diagnostic script to verify every penny:

```python
cash_track = 1_000_000.0  # Starting cash
for t in trades:
    if t['action'] in ('OPEN', 'ADD'):
        cash_track -= t['cost']  # commission only
    elif t['action'] in ('CLOSE', 'REDUCE'):
        cash_track += t['pnl']   # pnl field already = raw_pnl - cost
actual_cash = position_manager_instance.cash
print(f"Reconstructed: ${cash_track:.2f}, Actual: ${actual_cash:.2f}")
```

If they match to within floating-point noise (<$10 over 10K trades), accounting is correct. Large gaps ($thousands) mean the trade record fields don't match the actual cash operations.

**Floating-point noise baseline:** Expect ~$0.10–$0.15/trade of accumulated FP noise from `abs(qty) * (cost_per_contract + 0.5 * tick_size)` in cost calculations. Over 30K trades, $3K–$5K of noise is normal — not a bug. To verify noise vs real gap, trace cash before/after each trade and compare to expected delta from trade record fields. Every mismatch >$0.50 is a real discrepancy; FP noise stays sub-cent.

### Detailed Mismatch Detection

```python
# Per-trace mismatch script pattern
class TraceEngine(BacktestEngine):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.cash_trace = []
    def _open_position(self, ticker, qty, price, dt, signal, atr):
        before = self.position_mgr.cash
        super()._open_position(ticker, qty, price, dt, signal, atr)
        self.cash_trace.append(('open', ticker, before, self.position_mgr.cash))
    # Same pattern for _close, _add, _reduce...

mismatches = []
for i, (action, ticker, before, after) in enumerate(engine.cash_trace[1:], 1):
    trade = engine.trades[i - 1]
    if action in ('open', 'add'):
        expected = -trade.get('cost', 0)
    elif action in ('close', 'reduce'):
        expected = trade.get('pnl', 0)
    if abs((after - before) - expected) > 0.001:
        mismatches.append(...)
```

If zero mismatches, every penny is accounted for and the final gap is purely FP accumulation.

## Common Pitfalls

1. **CLOSE/REDUCE trade records missing the `cost` key** — the `pnl` field in the trade dict already includes the cost subtraction (`pnl = raw_pnl - cost`). Don't subtract cost again when summing pnl.

2. **`calculate_cost` asymmetry** — closing costs often use a 2x multiplier (`closing=True`). The trade's `pnl` field reflects this. OPEN trades use 1x and store the cost in the `cost` field separately.

3. **Dead `self.portfolio.cash` field** — many backtest engines have a `PortfolioState` object that shadows the `PositionManager.cash` field. One is written, the other is read. Check which one `get_portfolio_value()` actually uses.

4. **`_mark_to_market()` using stale prices** — if it does `self.data[ticker].iloc[-1]["Close"]`, it reads the very last bar of the dataset, not the current bar. This gives wrong MTM during the backtest loop. The live price from the current bar should be passed in instead.

## Payoff

This class of bug inflates performance by injecting phantom capital. A strategy showing 1,720%+ return in 3 months on 6 commodity futures is almost certainly an accounting bug. After fixing: the same strategy shows -36%. Always verify cash integrity before trusting any backtest result.