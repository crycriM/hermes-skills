# Futures Cash Accounting Pitfalls

Cash accounting bugs are the silent killers of futures backtests. Signals
can be perfect, position sizing correct, and the equity curve still says
+2000% while every per-asset PnL is negative.

## The Wrong Pattern: "Commission-Only" Accounting

**Symptom:** Cash balance grows monotonically above initial capital even
as trade-level PnL is negative. The equity curve shows 10-100× returns
while per-asset trade PnL reports a net loss.

**Root cause:** OPEN only debits the commission cost, never the full
position notional. CLOSE adds back the full sale proceeds:

```python
# WRONG — cash accounting bug (what metalai engine did)
def _open_position(self, ticker, qty, price, dt, ...):
    cost = executor.calculate_cost(qty, price, ticker)  # 1 tick = $2
    cash -= cost  # Only deducts commission! Notional never leaves cash

def _close_position(self, ticker, price, dt):
    qty = pos.quantity
    cost = executor.calculate_cost(qty, price, ticker, closing=True)
    cash += qty * price - cost   # Adds back full sale proceeds
    # But qty*price was never deducted → phantom cash injection
```

**Why it's wrong:** Every CLOSE injects `qty * price - cost` into cash,
but the initial OPEN only removed `cost`. Net effect per round-trip:
cash increases by roughly `qty * entry_price` (the initial notional was
never spent). Cash becomes a function of trade volume, not PnL.

**Test for it:** A dummy signal doing one OPEN then one CLOSE should
return cash to roughly initial (minus 2× commission). If cash is
*higher* after the close, you have this bug.

```python
# Regression test
class RoundTripSignal(SignalBase):
    name = 'roundtrip'
    def compute(self, data, idx, dt):
        return {t: 0.5 for t in data if idx < 505}  # open for 5 bars
        # then returns 0.0 → close at next bar

engine = BacktestEngine(data, config, [RoundTripSignal()], ...)
engine.run(start_idx=500, end_idx=520)
# Assert: cash ≈ initial_cash - 2 * commission
```

## The Right Pattern: Full Notional Accounting (Futures/Margin Style)

For futures backtesting, each OPEN must debit the full position value
from cash (or from a separate margin account). This is the correct
accounting:

```python
# CORRECT — futures-style margin accounting
def _open_position(self, ticker, qty, price, dt, ...):
    notional = abs(qty * price)
    cash -= notional          # Deduct full notional
    cost = calculate_cost(qty, price, ticker)
    cash -= cost              # Plus commission
    self.margin[ticker] = notional  # Track per-asset margin

def _close_position(self, ticker, price, dt):
    qty = pos.quantity
    sale_proceeds = qty * price
    cash += sale_proceeds     # Add sale proceeds
    cost = calculate_cost(qty, price, ticker, closing=True)
    cash -= cost              # Plus closing commission
    # PnL naturally = sale_proceeds - notional - costs
```

**For markets that use margin (e.g., CME metals, index futures):**
- Track `cash` separately from `margin_used`
- OPEN: `cash -= notional * initial_margin_pct` (e.g., 5% for gold)
- Variation margin: daily PnL is settled to cash
- CLOSE: `cash += notional * initial_margin_pct + realized_pnl`

**For crypto perpetuals (leverage model):**
- OPEN: `cash -= notional / leverage` (margin = position/leverage)
- Mark-to-market updates the unrealized PnL each bar
- CLOSE: return margin + realized PnL

## Multi-Asset Cumulative Exposure

With 6 assets and `max_position_pct = 0.05`, if all assets get a signal
at the same time, the cumulative notional = 6 × 5% = 30% of portfolio.
The per-asset cap correctly limits each position, but the total exposure
can still exceed what's realistic for a strategy.

This is NOT a bug per se — a long/short book can have 30% gross notional.
But check:
- Are all positions on the same side (all long or all short)?
- Does `max_long_pct` / `max_short_pct` already limit this?
- Should there be a portfolio-level gross exposure cap?

A portfolio-level exposure cap is a separate check:

```python
MAX_GROSS_NOTIONAL_PCT = 1.0  # max 100% of equity

gross = sum(abs(p.quantity * price) for p in positions) / portfolio_value
if gross + new_notional_pct > MAX_GROSS_NOTIONAL_PCT:
    scale_factor = (MAX_GROSS_NOTIONAL_PCT - gross) / new_notional_pct
    new_qty *= scale_factor  # prorate
```

## Per-Asset PnL Tracking

When the engine supports partial position adjustments (ADD/REDUCE), the
per-asset PnL must include REDUCE trades, not just CLOSE trades:

```python
# WRONG — only counts CLOSE trades
pnls = [t['pnl'] for t in trades if t['action'] == 'CLOSE']

# CORRECT — includes all realized PnL events
pnls = [t['pnl'] for t in trades
        if t['action'] in ('CLOSE', 'REDUCE', 'STOP_LOSS')]
```

Without this, a strategy that frequently reduces positions will show
misleading per-asset PnL (all negatives) while the equity curve looks
great.

## Forecast Vol Annualization Factor

When annualizing intraday volatility, the multiplier must match the
actual bar density, not a theoretical 24h market:

| Data type | Bars/year | Annualization factor | Common mistake |
|-----------|-----------|---------------------|----------------|
| 1h futures (Globex, ~23h/day) | ~5600 | sqrt(5600) ≈ 74.8 | sqrt(252×24) = 77.8 → 4% too high |
| 1h crypto (24/7) | 8760 | sqrt(8760) ≈ 93.6 | sqrt(365*24) = 93.6 ✓ |
| 5m crypto (288/day) | 105,120 | sqrt(105120) ≈ 324 | sqrt(365×288) = 324 ✓ |
| Daily (252 trading days) | 252 | sqrt(252) ≈ 15.9 | sqrt(252) ✓ |

```python
# Compute from actual data
bars = len(df)
days = (df.index[-1] - df.index[0]).days
bars_per_day = bars / max(days, 1)
annual_bars = bars_per_day * 365
annualization_factor = np.sqrt(annual_bars)

# Then:
forecast_vol = recent_returns.std() * annualization_factor
```

A 4% overestimate of vol means positions are ~4% smaller than intended
(conservative). But a 50% underestimate (using 252×24 when data has
sparse intraday gaps) means positions are 50% larger — dangerous.

**Quick check:** Sample several assets' annualized vol using both the
config's factor and the data-derived factor. They should agree within
~5% if no gaps are inflating the factor.

## Diagnostic Procedure

When a backtest shows unrealistic returns, follow this trace:

1. **Equity vs trade PnL discrepancy** — If equity curve says +2000%
   but per-asset CLOSE trade PnL sums to negative, you have a cash
   accounting bug. Run the round-trip test above.

2. **Trace a single trade cycle** — Use a dummy signal that does one
   OPEN then one CLOSE. Print cash before/after each step:

   ```python
   print(f"Open: cash {cash_before:.0f} -> {cash_after:.0f}")
   print(f"  Expected: cash -= cost = {cash_before - cost:.0f}")
   print(f"Close: cash {cash_before:.0f} -> {cash_after:.0f}")
   print(f"  qty*price = {qty*price:.0f}")
   print(f"  Expected: cash += qty*price - cost")
   ```

3. **Compare delta to expected** — If CLOSE cash delta ≈ `qty*price`
   and the OPEN only deducted `cost`, you've found the bug.

4. **Check cumulative exposure** — Log `sum(abs(qty*price)) / portfolio`
   at frequent intervals. Should not exceed realistic limits.

5. **Per-asset PnL audit** — Sum all CLOSE, REDUCE, STOP_LOSS trade
   PnLs per asset. Compare to equity curve total change: `cash + MTM
   - initial_cash`. The two should approximately agree (within costs
   and open position MTM).