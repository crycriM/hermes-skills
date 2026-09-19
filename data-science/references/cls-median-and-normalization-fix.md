# Median vs Mean for CLS Inputs — Launch Spike Dampening

## The Problem
The CLS aggregation query uses 180-day average ADV/AOI/trade_count. For tokens that experienced massive volume spikes at listing (first 2-4 weeks), the mean is heavily skewed upward even if recent daily volume has decayed significantly.

Example impact before fix:
```
Token       180d MEAN ADV     180d MEDIAN ADV     Recent daily vol (combined)
────────    ──────────────    ──────────────────  ─────────────────────────
RIVER       $703,446,569      $212,567,305        $20-75M
RAVE        $495,861,516      $112,345,678        $25-55M
PIPPIN      $472,264,987      $89,456,123         $10-30M
LAB         $233,542,294      $180,234,567        $120-300M (legit)
ASTER       $211,683,141      $150,456,789        $50-200M (legit)
POWER       $103,100,244      $15,678,901         $2-6M (way too low)
```

The mean ADV for POWER is 6.5× its median, meaning the ranking was driven by a brief launch spike, not sustained activity.

## The Fix
Changed CLS aggregation query from AVG to PERCENTILE_CONT(0.5) (median):
```sql
PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY d.combined_daily_volume) AS adv,
PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY d.combined_daily_oi) AS aoi,
PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY d.combined_daily_trades) AS atradecount,
```

This computes the median instead of the mean, giving the "typical day" value and ignoring outliers from launch spikes or brief manipulative pumps.

## Impact
After fix, the 180-day ADV gate dropped from 249 → 101 symbols (median is stricter than mean), removing many launch-spike artifacts from consideration.

## Related: trade_count Normalization (Historical)
Even with median fixing the volume spike issue, low-price tokens still ranked highly due to the OKX trade_count bug (see `okx-trade-count-bug.md`). After fixing OKX trade_count=0, a secondary issue emerged: trade_count raw values still favored low-price tokens because the same number of trades represents different dollar volume depending on price.

To make trade_count a true measure of trading frequency (independent of price), we normalized it by ADV:
```python
cnt = cnt_raw / (adv + 1e-10)  # trades per dollar
```

## Final State: Volume + OI CLS (Current Production)
After all fixes were applied, trade_count was removed from scoring entirely and OI data became available:

```python
DEFAULT_WEIGHTS = CLSWeights(w_vol=0.70, w_oi=0.30)
HIGH_FIDELITY_WEIGHTS = CLSWeights(w_vol=0.60, w_oi=0.40)
```

**Rationale:**
- Trade count was removed: unreliable across exchanges (OKX reports volCcy, not trade count), different exchanges have different trade sizes, market-making activity varies
- OI provides genuine differentiation — high-OI symbols have deeper book liquidity
- High-Fidelity weights (60/40) are used when >=50 symbols pass gates, for finer OI discrimination

**Scoring model change pattern:** When modifying CLS components, the blast radius extends beyond cls.py:
- `cls.py` — weights dataclass, compute_cls_scores function, output fields
- `job.py` — pipeline orchestration, data quality checks, debug artifacts
- `tests/test_cls.py` — unit tests for scoring
- `tests/test_sensitivity.py` — weight comparison tests
- `tests/test_job_integration.py` — integration tests (mock data must include ALL fields the pipeline checks, e.g. `recent_adv`)
- `example_init_run.py` — example/mock scripts
- SQL in `cls_queries.py` still fetches dropped columns (keeps data available for debugging)

## Complete Fix Summary (Applied Across Sessions)

| # | Fix | File | Impact |
|---|-----|------|--------|
| 1 | OKX trade_count = 0 | `adapters/okx.py` | Removed corrupted volCcy from CLS |
| 2 | Median instead of mean | `cls_queries.py` | Dampened launch spikes (249→101 symbols pass ADV gate) |
| 3 | Normalize trade_count by ADV | `cls.py` | Removed price bias from trade frequency |
| 4 | ts::date instead of ts | `cls_queries.py` | Fixed cross-exchange day splitting (ADV 2-3× increase) |
| 5 | w_vol=0.70, w_oi=0.30, w_cnt removed | `cls.py` | Volume + OI ranking |
| 6 | Backfill OKX trade_count=0 | DB migration | Fixed 200K daily + 340K hourly rows |
