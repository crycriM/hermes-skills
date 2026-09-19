# Futures vs Equity Accounting Models

## The Core Difference

**Equity**: You buy the asset. Cash decreases by full notional. You own the asset. On sale, cash increases by full proceeds. PnL = sale - purchase.

**Futures**: You post margin (collateral). No cash leaves for the notional. PnL settles daily via variation margin. On close, only the realized PnL hits cash.

## Correct Futures Accounting Implementation

```python
class PositionManager:
    def __init__(self, initial_cash=1_000_000):
        self.cash = initial_cash
        self.positions = {}  # ticker -> Position(quantity, entry_price)
    
    def open_position(self, ticker, qty, price, commission):
        """Open new futures position. Only commission debited."""
        self.cash -= commission
        self.positions[ticker] = Position(qty, price)
    
    def close_position(self, ticker, price, commission):
        """Close position. Only realized PnL credited."""
        pos = self.positions.pop(ticker)
        pnl = pos.quantity * (price - pos.entry_price)
        self.cash += pnl - commission
        return pnl - commission
    
    def add_to_position(self, ticker, delta_qty, price, commission):
        """Add to existing position. Only commission debited."""
        self.cash -= commission
        self.positions[ticker].quantity += delta_qty
    
    def reduce_position(self, ticker, delta_qty, price, commission):
        """Reduce position. Realized PnL on reduced portion credited."""
        pos = self.positions[ticker]
        pnl = delta_qty * (price - pos.entry_price)
        self.cash += pnl - commission
        pos.quantity += delta_qty  # delta_qty is negative
        if abs(pos.quantity) < 1e-10:
            del self.positions[ticker]
        return pnl - commission
    
    def get_portfolio_value(self, prices):
        """Equity = cash + unrealized PnL of all open positions."""
        unrealized = sum(
            pos.quantity * (prices[ticker] - pos.entry_price)
            for ticker, pos in self.positions.items()
        )
        return self.cash + unrealized
```

## Verification Pattern

After running a backtest, verify accounting integrity:

```python
# Reconstruct cash from trade records
cash_reconstructed = initial_cash
for trade in trades:
    if trade['action'] in ('OPEN', 'ADD'):
        cash_reconstructed -= trade['cost']
    elif trade['action'] in ('CLOSE', 'REDUCE'):
        cash_reconstructed += trade['pnl']  # pnl already includes cost deduction

# Compare to actual
assert abs(cash_reconstructed - engine.cash) < 0.01, \
    f"Accounting mismatch: {cash_reconstructed} vs {engine.cash}"
```

## Common Mistake: Sale-and-Repurchase Model

```python
# WRONG — this is equity accounting applied to futures
def open_position(self, ticker, qty, price, commission):
    self.cash -= qty * price + commission  # Debits full notional!

def close_position(self, ticker, price, commission):
    pos = self.positions.pop(ticker)
    self.cash += pos.quantity * price - commission  # Credits full proceeds!
```

**Why it's wrong**: On open, $50K notional is debited. On close, $50K+ is credited. Net cash change per trade cycle = full notional + PnL - 2*commission. After N trades, cash inflates by N * avg_notional.

**Symptom**: Equity curve grows monotonically with trade count, regardless of whether trades are profitable. Cash reaches millions while realized PnL is negative.

## Margin Account Model (Alternative)

Some systems track margin explicitly:

```python
class MarginAccount:
    def __init__(self, initial_cash, margin_pct=0.1):
        self.cash = initial_cash
        self.margin_pct = margin_pct
        self.margin_used = 0
    
    def open_position(self, notional, commission):
        margin_required = notional * self.margin_pct
        self.cash -= margin_required + commission
        self.margin_used += margin_required
    
    def close_position(self, notional, pnl, commission):
        margin_returned = notional * self.margin_pct
        self.cash += margin_returned + pnl - commission
        self.margin_used -= margin_returned
    
    def get_equity(self):
        return self.cash + self.margin_used  # Cash + margin held
```

This is equivalent to the simpler model if you track equity = cash + margin_used + unrealized_pnl.

## Per-Asset PnL Tracking

For reporting, track PnL per asset:

```python
asset_pnl = {}
for trade in trades:
    ticker = trade['ticker']
    if trade['action'] in ('CLOSE', 'REDUCE'):
        asset_pnl.setdefault(ticker, 0)
        asset_pnl[ticker] += trade['pnl']
    elif trade['action'] in ('OPEN', 'ADD'):
        asset_pnl.setdefault(ticker, 0)
        asset_pnl[ticker] -= trade['cost']
```

Note: OPEN/ADD costs are separate from CLOSE/REDUCE PnL. The trade record for CLOSE/REDUCE typically stores `pnl = raw_pnl - cost`, so you don't double-count.
