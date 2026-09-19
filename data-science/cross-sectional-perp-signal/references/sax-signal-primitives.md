# SAX (Symbolic Aggregate approXimation) — Signal Primitives & Gate 0

Built July 2026 as Phase 0 of `docs/SAX_TRANSFORMER_RESEARCH_PLAN.md` / `SAX_IMPLEMENTATION_NOTES.md`.
Zero new dependencies — pure numpy/pandas. Located at `perp_strategy/signals/sax.py`.

## Core Design

The entire tokenizer pivots on one observation: `rank(pct=True)` *is* the
empirical CDF, so equal-mass symbolisation is a single line and carries zero
lookahead by construction. No z-normalisation, no breakpoint estimation.

## API

```python
from perp_strategy.signals.sax import (
    xs_sax, paa, slope, sax_1d,
    markov_surprise, ngram_counts, ngram_total,
)
```

### xs_sax(panel, alphabet=8) → DataFrame[int]
Cross-sectional rank quantile tokenizer. For each row t, ranks every asset
cross-sectionally, scales to [0,1], bins into `alphabet` equal-mass buckets.
Symbols are nullable Int64 (preserves NaN through panels with missing assets).

### paa(panel, w) → DataFrame
Piecewise aggregate approximation — mean of each segment of length w, expanded
back to original length. Segment mean at each bar.

### slope(panel, w) → DataFrame
Per-segment OLS slope (hand-rolled, no tslearn dependency). β = Σ(x−x̄)(t−t̄) / Σ(t−t̄)².

### sax_1d(panel, w=4, a_mean=8, a_slope=4) → (mean_sym, slope_sym)
1d-SAX: symbolise both segment mean and slope. Joint state space = a_mean × a_slope.
Returned as two separate DataFrames; caller decides concatenation vs cartesian.

### markov_surprise(symbols_df, train_window, alphabet=8) → DataFrame
Per-asset -log P(s_t | s_{t-1}). Transition matrix estimated on first `train_window`
bars only, frozen for remainder — no rolling estimation, no lookahead. Add-one
smoothing. Surprise ≈ log(A) for i.i.d.; spikes flag regime breaks.

### ngram_counts(symbols_df, n=2, window=96, alphabet=8) → Dict[str, DataFrame]
Full per-type n-gram sliding-window counts. Returns A^n DataFrames, one per n-gram type.
Keys are lexicographic: "0_1" for bigram "01", "0_1_2" for trigram "012".

**Performance warning:** A=8, n=3 → 512 DataFrames. For 80 assets × 500 bars this
is ~30+ min per fold. Use `ngram_total` for correlation checks; reserve full
per-type counts only for motif-discovery runs.

### ngram_total(symbols_df, n=2, window=96, alphabet=8) → DataFrame
Vectorized total n-gram count via numpy convolution. Single DataFrame instead of A^n.
~50× faster than ngram_counts. Use for IC evaluation, feature dicts.

## Pandas Nullable Int64 Pitfall

xs_sax returns `Int64` (nullable) to preserve NaN through panels with spotty asset
coverage. This means:

- **Do NOT** use `np.isnan()` — use `pd.isna()` (works on both np.nan and pd.NA)
- **Do NOT** call `valid.any()` on an Int64 series (pd.NA is ambiguous) — use `np.count_nonzero()`
- When converting to numpy: `sym_series.fillna(-1).astype(int).values`

## Gate 0 Results (in progress as of 2026-07-21)

Walk-forward SAX-VSM check: n-gram total counts + Markov surprise vs forward
cross-sectional rank IC on 4h Binance perp data (2022-2025, ~354 tickers).

### Interim readings (fold 40/~70):
| Feature | mean IC | Status |
|---------|--------:|--------|
| Bigram total count | ~0.0000 | Dead |
| Trigram total count | ~0.0000 | Dead |
| Markov surprise | ~0.0086 | Rising, approaching 0.01 gate |

Bigram/trigram total counts show zero IC — every asset's window has comparable
n-gram totals after xs_sax equal-mass binning, so there's no cross-sectional
differentiation. Markov surprise (a scalar per asset) may pass the gate on its own.

Gate threshold: |IC| ≥ 0.01 → proceed to Phase 1 (add surprise to WaveletNet features).
Below threshold → document negative result, abandon SAX discretization.

## Volume Plumbing (July 2026)

Root-cause fix: `BaseSignal.fit()` and `generate()` now accept `volumes=` and
`prices=` kwargs. All 15 signal classes updated. `run_backtest.py` and
`run_all_backtest.py` slice training/test volumes from the resampled data and
pass them through. WaveletNet's `_build_feature_window()` now computes real
`logvol_24h` at inference instead of zero-filling.

Before this fix, every volume-using signal had to zero-fill or reconstruct from
returns — the `channels[:, i] = 0.0` line at `waveletnet_ranking.py:732` was the
canonical workaround. That line is now gated on volume availability.
