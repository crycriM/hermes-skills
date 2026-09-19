# AdaVol Adaptive Volatility Regime Detection

AdaVol (Adaptive Volatility) detects market volatility regimes using an
exponentially weighted moving average with a dynamically adjusted decay factor.
No training, no HMM — pure numpy, O(n).

## Algorithm

1. **Fast EWMA**: `fast_vol[t] = λ_fast * |r[t]| + (1 - λ_fast) * fast_vol[t-1]`
   where λ_fast = 0.06
2. **Slow EWMA**: `slow_vol[t] = λ_slow * |r[t]| + (1 - λ_slow) * slow_vol[t-1]`
   where λ_slow = 0.01
3. **Volatility Ratio**: `VR[t] = fast_vol[t] / slow_vol[t]`
4. **Adaptive lambda**: if VR > 1.5 → λ=0.12 (react faster to vol spikes),
   if VR < 0.7 → λ=0.03 (smooth out), else λ=0.06
5. **Variance**: `σ²[t] = λ_adap[t] * r[t-1]² + (1 - λ_adap[t]) * σ²[t-1]`
6. **Vol forecast**: `vol_forecast[t] = sqrt(σ²[t])`
7. **Regime**: LOW_VOL(0) if vol_ratio < 0.8, MED_VOL(1) if 0.8-1.2, HIGH_VOL(2) if ≥ 1.2
   where `vol_ratio = vol_forecast / hist_vol` (5-bar MA smoothed)

## Implementation Pattern

```python
def extract_regime_features(ohlcv):
    # Compute ALL features in one vectorized pass
    # Rolling windows are inherently no-lookahead (trailing only)
    # Returns (n_bars, 4): [log_return, vol_forecast, forecast_uncertainty, vol_ratio]

def run_walk_forward_adavol(ohlcv, warmup=120):
    # Call extract_regime_features ONCE on the full data
    features = extract_regime_features(ohlcv)
    # Then iterate over pre-computed features for classification
    for i in range(warmup, n_bars):
        label = 0 if vol_ratio[i] < 0.8 else 2 if vol_ratio[i] > 1.2 else 1
        probs[i] = soften(vol_ratio[i])
```

## Critical Performance Trap

**Never call extract_regime_features inside the per-bar loop** — that's O(n²).
The rolling windows in feature extraction already have no lookahead (they only
use data up to the current bar), so compute once, iterate on the result.

## Parameters That Matter

| Parameter | Value | Effect |
|---|---|---|
| λ_fast | 0.06 | Speed of fast EWMA response |
| λ_slow | 0.01 | Speed of slow EWMA baseline |
| VR high threshold | 1.5 | Triggers faster adaptation |
| VR low threshold | 0.7 | Triggers slower adaptation |
| λ_high | 0.12 | Fastest adaptation rate |
| λ_low | 0.03 | Slowest adaptation rate |
| Vol ratio LOW bound | 0.8 | LOW_VOL cutoff |
| Vol ratio HIGH bound | 1.2 | HIGH_VOL cutoff |
| Rolling hist vol | 60 bars | Long-term baseline |
| Rolling vol ratio MA | 5 bars | Smoothing |

## Integration Pattern

In a walk-forward backtest runner, add a `_get_regimes(btc_data, mode)` helper
that dispatches between rule-based and AdaVol. Store regimes once at startup
(same regimes for all pairs since BTC is the market proxy).