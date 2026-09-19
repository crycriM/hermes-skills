# Signal Direction Diagnostics

## The Inversion Test

When a signal loses money, the first diagnostic is: **does it work when inverted?**

```python
class InvertedSignal:
    """Wrapper that negates signal outputs for direction testing."""
    
    def __init__(self, signal):
        self.signal = signal
        self.name = f"inverted_{signal.name}"
    
    def initialize(self, data):
        self.signal.initialize(data)
    
    def compute(self, data, idx, dt):
        results = self.signal.compute(data, idx, dt)
        return {t: (-v if v is not None else None) for t, v in results.items()}
```

Run the backtest twice: once with the original signal, once with the inverted wrapper. Compare results.

## Interpretation Matrix

| Normal Return | Inverted Return | Diagnosis | Action |
|---------------|-----------------|-----------|--------|
| -3% | +0.3% | Sign convention error | Invert the signal or fix direction mapping |
| -15% | -6% | Structurally broken | Reconsider signal concept for this asset/timeframe |
| -21% | -13% | Structurally broken | Signal loses both ways — conceptual issue |
| +0.5% | -0.4% | Works in one direction | Keep normal version |
| +2% | +1.5% | Robust signal | Signal works regardless of direction (rare, check for look-ahead bias) |

## Case Study: MetalAI Signals (May-June 2025)

| Signal | Normal | Inverted | Diagnosis |
|--------|--------|----------|-----------|
| IntradayMomentum | -3.12% | +0.34% | Sign error — overnight returns anti-correlate with intraday |
| GoldSilverSpread | -0.40% | +0.53% | Sign error — mean-reversion fades a trend |
| CrossAssetLag | -1.23% | -1.07% | Broken — loses both ways |
| ORB | -15.27% | -6.05% | Broken — breakout system fails in both directions |
| VolManagedMomentum | -21.09% | -12.87% | Broken — momentum concept fails on this data |
| Combined (all 5) | -35.96% | n/a | Ensemble dilution — worse than any individual |

## Root Cause Analysis

### Sign Convention Errors

**IntradayMomentum**: Predicts overnight return continues into intraday session. In commodity futures, overnight gaps frequently reverse during the pit session. The signal is a continuation model applied to mean-reverting data.

**Fix**: Negate the signal. Confirmed improvement: -3.12% → +0.34%.

**GoldSilverSpread**: Models `log(GC) = intercept + hedge_ratio * log(SI) + residual`. Trades z-score of residual, expecting mean reversion. If gold is outperforming silver (trend), the residual stays elevated and every mean-reversion trade loses.

**Fix**: Invert the signal. Confirmed improvement: -0.40% → +0.53%.

### Structural Failures

**ORB (Opening Range Breakout)**: Tracks session range from first 2 bars, enters on breakouts. Loses in both directions because:
- Breakouts fail more often than they succeed in low-vol environments
- No trailing stop or take-profit mechanism
- Daily-resetting ranges mean each trade is a 50/50 bet that bleeds via commissions

**VolManagedMomentum**: Multi-horizon momentum with cross-sectional ranking. Loses both ways because:
- Momentum at 50-500 bar horizons has negative autocorrelation on 15-min commodity data
- Cross-sectional ranking on only 6 assets produces coarse buckets with low signal-to-noise
- HAR vol forecast was computed at initialization and never updated (stale state bug)

**CrossAssetLag**: Lead-lag relationships between commodities. Loses both ways because:
- Lead-lag relationships are unstable and regime-dependent
- Correlation filter (`abs(corr) < 0.1`) is too loose
- Cross-sectional momentum component adds noise

## Ensemble Combiner Diagnostics

### The Dilution Problem

When combining signals with conflicting directional biases:

```python
# Example: 5 signals, 3 say long, 2 say short
signals = {
    'IntradayMomentum': +0.5,  # Long
    'GoldSilverSpread': +0.3,  # Long
    'ORB': -0.4,               # Short
    'VolManagedMomentum': -0.6, # Short
    'CrossAssetLag': -0.2,     # Short
}

# Equal-weighted average
combined = sum(signals.values()) / len(signals)  # = -0.08

# Result: weak short signal, barely passes dead-zone threshold
# Direction is wrong (should be long), size is tiny
```

### Symptoms of Combiner Dilution

1. **Ensemble performs worse than best individual signal**
   - Best signal: +0.53%
   - Ensemble: -35.96%
   
2. **Win rate drops when combining**
   - Individual signals: 18-44% win rate
   - Ensemble: 27% win rate (lower than most individuals)

3. **Positions are smaller and less confident**
   - Individual signals produce positions sized for their conviction
   - Averaged signal has low magnitude, producing tiny positions

### Diagnostic: Signal Agreement

Check how often signals agree on direction:

```python
agreement_count = 0
total_bars = 0

for bar in backtest_bars:
    signals = compute_all_signals(bar)
    directions = [1 if s > 0 else -1 for s in signals.values() if s is not None]
    
    if len(directions) >= 3:
        total_bars += 1
        majority = 1 if sum(directions) > 0 else -1
        agreement = sum(1 for d in directions if d == majority)
        if agreement >= 4:  # 4/5 agree
            agreement_count += 1

agreement_rate = agreement_count / total_bars
print(f"Signals agree (4/5 or better): {agreement_rate:.1%}")
```

If agreement rate is < 30%, the signals are fighting each other and the combiner is destructive.

### Fix: Regime-Conditional Combining

Only combine signals when they agree on direction:

```python
def combine_signals(signals, min_agreement=0.6):
    """Combine signals only when majority agrees on direction."""
    valid = {k: v for k, v in signals.items() if v is not None}
    if len(valid) < 2:
        return None
    
    directions = [1 if v > 0 else -1 for v in valid.values()]
    majority = 1 if sum(directions) > 0 else -1
    agreement = sum(1 for d in directions if d == majority) / len(directions)
    
    if agreement < min_agreement:
        return None  # Signals disagree, skip this bar
    
    # Combine only agreeing signals
    agreeing = {k: v for k, v in valid.items() if (v > 0) == (majority > 0)}
    return sum(agreeing.values()) / len(agreeing)
```

## Testing Workflow

1. **Test each signal individually** (normal and inverted)
2. **Identify profitable signals** (positive return in at least one direction)
3. **Drop structurally broken signals** (lose both ways)
4. **Test pairwise combinations** of profitable signals
5. **Check signal agreement rate** — if < 50%, combiner is destructive
6. **Consider regime filtering** — only trade when vol is high, or when signals agree

## Common Pitfalls

- **Averaging broken signals**: If 3/5 signals lose money, the ensemble will be worse, not better. Drop the losers.
- **Equal weighting**: Signals with different Sharpe ratios should be weighted by inverse variance or Kelly fraction.
- **Ignoring correlation**: If two signals are highly correlated, combining them doesn't add diversification.
- **Over-optimizing weights**: On 2 months of data, weight optimization will overfit. Use equal weights or simple heuristics.
