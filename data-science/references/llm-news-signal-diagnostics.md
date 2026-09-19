# LLM News Sentiment Signal Diagnostics

## Methodology (from AlphaSent 7-month run)

Run sequence for a text-only signal evaluation (no OHLCV):

```
1. Load all cached EventRecords via load_all_cached(MODEL_VERSION, PROMPT_VERSION)
2. For each asset with >=5 events, generate hourly bar schedule from
   min(published_at) to max(published_at) + 1 day
3. For each bar, call build_feature_vector(events, lookback_hours, bar_open_ts, asset)
   -- this handles PIT filtering internally
4. Write features per (asset, date) to data/features/<asset>/YYYY-MM-DD.parquet
5. Aggregate all feature parquets, compute:
   - Polarity distribution (mean, std, +/- split)
   - Event volume (mean/median/max events per bar, % zero bars)
   - Event-type flag rates (hack, regulation, listing, depeg)
   - Feature autocorrelation (lag 1, lag 24)
   - Feature-feature cross-correlation (detect multi-collinearity)
   - Per-asset breakdowns (event volume, polarity profile)
   - Info-ratio estimate: mean(polarity) / std(polarity)
```

## Key Diagnostics

### Zero-Bar Ratio
The fraction of hourly bars where n_events = 0 in lookback window.
- 24h lookback: ~79% across 40+ assets
- 72h lookback: ~50%
- Solution: daily bars (24h freq) cut this to <10%, or use wider lookback.

### Autocorrelation Structure
polarity_sum autocorrelation gives the signal's memory:
- Lag 1: ~0.99 at hourly bars (too slow to mean-revert)
- Lag 24: ~0.62 (still significant)
- Implication: news features at hourly frequency are almost non-stationary. 
  Consider differencing or daily aggregation.

### Polarity Distribution
Check for degenerate behavior:
- Healthy: mean ~0, std >= 0.5, roughly symmetric +/- split
- Suspect: mean strongly > 0 (systematic bullish bias), or std very low
- Llama3-8b output: mean +0.05, std 0.23, 79% at zero = poor
- Better model (gemma4-12b, qwen36-35b) may produce wider distributions

### Event-Type Sparsity
Rate of non-zero flag bars across the dataset:
- macro: ~63% of events (most common, lowest signal/noise)
- regulation: ~5% of events (best signal/noise)
- hack: ~1.3% (rare but high-impact)
- listing: ~1% (rare, mixed impact)
- depeg: ~2% (rare, high-impact but specific to stablecoins)

If regulation + hack + listing flags fire on <5% of bars, the signal
is too sparse for hourly models. Switch to daily and use event-count
as a thinning diagnostic.

### Feature Collinearity
On a 61-feature vector (6h/24h/72h lookbacks × ~15 base features):
- n_events ~ n_high_conf_events: r=0.999 (drop n_high_conf_events)
- mag_weighted_polarity ~ novelty_polarity: r=0.99 (drop one)
- polarity_sum ~ mag_weighted_polarity: r=0.99
- Effective dimensionality: ~5-6 independent factors
- Use PCA or select one lookback window, not all three

### LLM Calibration Check
Inspect confidence score distribution from extraction cache:
```
load_all_cached() -> df['confidence'].describe()
```
- Count: 3820, Mean: 0.82, Std: 0.12
- Llama3-8b clusters around {0.78, 0.85} with little variance
- Well-calibrated model would show U-shape near 0 and 1
- Poor calibration adds noise to the feature vector; treat confidence
  as a weight of limited value

## What a Healthy Signal Looks Like

Target profile for a usable news-based alpha satellite signal:

| Metric | Target | Current (llama3-8b) |
|--------|--------|---------------------|
| Zero-bar ratio (24h) | <30% | ~79% |
| Polarity mean | ~0 ± 0.02 | +0.05 |
| Polarity std | >0.5 | 0.23 |
| Autocorr lag 1 | <0.8 | 0.99 |
| Autocorr lag 24 | <0.3 | 0.62 |
| Effective dimensions | >10 | ~5-6 |
| LLM conf std | >0.15 | 0.12 |
