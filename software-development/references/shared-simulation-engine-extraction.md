# Shared Simulation Engine Extraction

Extracting accounting/simulation logic from a backtest module into a shared
core, with a re-export shim preserving backward compatibility and a regression
gate confirming identical results.  Drawn from the Taoshi miner paper trading
evolution (P0–P2, July 2026).

## When this applies

A backtest module (`backtest/__init__.py`) contains the *only* implementation
of positions, PnL, fees, drawdown, and metrics — but the live pipeline needs
the same accounting without a chain.  The goal is **one accounting engine, two
drivers**: the historical backtest and the live paper-trading loop.

## Steps

### 1. Extract into a shared package

Create `signal_bridge/sim/engine.py` (or equivalent).  Move these from the
backtest module:

- Data structures: `Position`, `Portfolio`
- Execution: `execute_signal`, `apply_carry_fees`, `apply_spread_fee`
- Sizing: `DrawdownScaler`
- Engine: `compute_metrics`, `BacktestResult`, `run_walk_forward`
- Constants: all fee rates, leverage limits, bar counts

**Zero behavior change.**  Copy the logic verbatim — no refactoring, no
renaming beyond the module path.

### 2. Create a clean public API

`signal_bridge/sim/__init__.py` with `__all__` and re-exports from `engine.py`.

### 3. Rewire the backtest to import from the shared core

Replace the original `backtest/__init__.py` with a **re-export shim**:

```python
# backtest/__init__.py
from signal_bridge.sim.engine import Position, Portfolio, execute_signal, ...

__all__ = ["Position", "Portfolio", "execute_signal", ...]
```

Every existing import path still works:
```python
from signal_bridge.backtest import Position    # ✅ still works
from . import DrawdownScaler                  # ✅ still works
```

### 4. Regression gate

Verify identity: objects imported from both paths must be the **same object**:

```python
from signal_bridge.sim import Position as SimPos
from signal_bridge.backtest import Position as BtPos
assert SimPos is BtPos
```

Then run a known backtest scenario (fixed seed, known window) and confirm
**identical metrics** — same return, Sharpe, max DD, win rate.  This is the
regression gate: if metrics differ, the extraction broke something.

## Pitfalls

- **Don't refactor during extraction.**  The only change is the module path.
  Refactoring logic while moving it makes the regression gate meaningless.
- **Don't forget constants.**  Fee rates, leverage limits, bar counts — all
  must move with the logic.  A missing constant causes silent divergence.
- **Don't forget `__all__` in the shim.**  Check that every name in the original
  module is re-exported.
- **Identity assertion is the real gate.**  Running the backtest is the
  functional check, but the identity assertion (`is`) catches the case where
  two copies exist side-by-side with subtly different code.

## Related patterns

- **Open-core/plugin split** (`open-core-plugin-split.md`) — same
  extraction idea but driven by business model, not accounting parity.
- **Model versioning** — after extraction, stamp every emitted signal with
  `model_version` (semver) and `run_id` (timestamp + short git SHA).  This
  makes every fill traceable to the exact model version and code revision.
