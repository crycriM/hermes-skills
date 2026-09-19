# Trading Signal & Ensemble Debugging

## When to Use This Reference

A combined multi-signal strategy underperforms or loses money, and you need to know whether individual signals are genuinely bad, directionally reversed, or fighting each other in the combiner.

Typical triggers:
- Combined equity curve is worse than any single signal run solo
- Win rate is ~25% but fees are tiny — systematic directional bias suspected
- "Inverting the signal" makes it profitable

## Phase 1: Per-Signal Isolation (Always First)

**Run each signal as the single active signal in the engine.** Do this for both normal and inverted directions:

```python
from copy import deepcopy

class InvertWrapper:
    """Wrap any signal and negate its outputs."""  
    def __init__(self, signal):
        self.signal = signal
        self.name = signal.name   # keeps combiner weights working
    def compute(self, data, idx, dt):
        r = self.signal.compute(data, idx, dt)
        return {t: (-v if v is not None else None) for t, v in r.items()}

for name, cls in all_signal_classes:
    for direction in ['normal', 'inverted']:
        sig = cls(config)
        sig.initialize(data)
        if direction == 'inverted':
            sig = InvertWrapper(sig)
        engine = BacktestEngine(aligned_data, config, [sig], ...)
        result = engine.run(...)
        # Record: total_return, sharpe, win_rate, num_trades, end_equity
```

**What to look for:**

| Pattern | Diagnosis |
|---------|-----------|
| Normal loses, inverted makes money | **Reversed signal bias** — the signal math maps opposite to actual price direction. Likely sign convention mismatch. |
| Both directions lose | **Dead signal** — no predictive content for this asset set / timeframe. Remove from ensemble. |
| One direction profitable but weak | **Weak signal** — has edge but low signal-to-noise. Needs parameter tuning or different asset set. |

## Phase 2: Signal Reversal Diagnosis

When 3+ of 5 signals perform better inverted, it's not coincidence — it's a systematic sign error in one of:

1. **Forecast computation** — the signal computes `forecast - current` but the price moves in the direction of `current - forecast`. The arrow of prediction is backwards.
2. **Lag alignment** — the signal uses `data.iloc[idx]` (current bar) but the actual execution price is from the **next** bar. If the signal says "buy" based on current price data, but the trade fills at next bar's open, the price move between bars cancels the edge.
3. **Return calculation** — `(open - close) / close` vs `(close - open) / open`. The sign flips depending on which price is the reference.

**Test:** Pick one reversed signal and trace a single trade:
```python
# For a specific signal at a specific bar:
# 1. What was the raw signal value? (+0.7 = strong buy)
# 2. What was the entry price and next-bar return?
# 3. If signal = +0.7 (buy) and next-bar return = -0.2%, the signal is genuinely reversed
```

## Phase 3: Ensemble Conflict Diagnosis

A combined ensemble that's **worse** than the average of its individual signals means the combiner is creating internal fights:

**Root cause:** If Signal A is bullish on GC=F and Signal B is bearish, the combiner averages them to ~0 (weak signal). The position is opened small or not at all. Meanwhile, a genuinely strong directional move gets no position while the allocation budget is consumed by signals fighting.

**Diagnostic:**

```python
# Track individual signal values at each bar
for each bar in backtest:
    for ticker:
        signal_values = {name: sig.compute(data, idx, dt)[ticker] for name, sig in signals}
        combined = weighted_average(signal_values)
        # If |combined| < min(|signal_A|, |signal_B|), the ensemble is diluting conviction
```

**Fix options:**
- Remove signals that fight the majority direction (worst performers from Phase 1)
- Use a combiner that selects the strongest signal rather than averaging (max-confidence)
- Add a "direction consensus" gate: only trade when 60%+ of signals agree on direction

## Pragmatic Filter for "Is This Signal Worth Keeping?"

After Phase 1, rank signals by sorted end equity:

```
Signal A (inv):  $1,003,438  +0.34%  ← keep if positive
Signal B (norm): $1,000,000   0.00%  ← flat, drop
Signal C (norm): $  847,301 -15.27%  ← always loses, drop
```

A flat signal (near 0% return) is not neutral — it's consuming position budget and adding noise. Drop it. A losing signal that reverses to winning is a sign convention fix, not a "keep" signal. Fix the sign, then re-evaluate the true edge.

## Real-World Example

From a 6-asset commodity futures system with 5 signals:
- 3 of 5 signals were directionally reversed (better inverted)
- The equity-weighted combiner averaged reversed + non-reversed → near-zero conviction on most bars
- Combined ensemble: -36% return
- Best individual (inverted): +0.53%
- Lesson: the ensemble was worse than useless — it was actively diluting the few signals that had edge

## Quick Reference

| Symptom | Action |
|---------|--------|
| Most signals lose money with low fees | Run per-signal isolation in both directions |
| Signal flips from loss to profit when negated | Fix sign convention in that signal's compute() |
| Combined result worse than best individual | Drop conflict-inducing signals or switch to max-confidence combiner |
| All signals lose both directions | The signal class doesn't work on this data — try different predictors or asset set |