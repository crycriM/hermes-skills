# Hyperliquid Cross-Sectional Signal Architecture

Reference for building quant signal pipelines on Hyperliquid perps, reusing existing data infrastructure.

## Project Structure

```
hl_signal/
├── config.py              # Frozen dataclasses for all hyperparameters
├── data.py                # Rankit DB reader (primary) + CCXT fallback
├── universe.py            # Top-N liquid perps by ADV, crypto-only filter
├── features.py            # Pipeline orchestrator (chains all feature modules)
├── features_helpers.py    # Shared: log_returns, ewma, rolling_std, rsi, bollinger, cross_sectional_rank
├── features_funding.py    # Funding alpha (7 features from hourly HL funding)
├── features_vol.py        # Volatility forecast (8 features, EWMA + realized)
├── features_rocket.py     # Momentum (6 features: accel, breakout, vol conviction, RSI)
├── features_liquidity.py  # Liquidity (3 features: turnover, accel, regime)
├── target.py              # Forward return + quintile binning
└── tests/
```

## Data Access Pattern

Primary reads from rankit's TimescaleDB (existing pipeline, no duplicate fetching). CCXT fallback for standalone use.

### Symbol Normalization
- rankit uses `BTC-USDT` format internally
- CCXT uses `BTC/USDC:USDC` format
- Conversion: `sym.replace("-USDT", "/USDC:USDC")` for CCXT, reverse for DB

### Universe Selection
- Fetch all active HL perps via `metaAndAssetCtxs` or CCXT
- Filter: exclude non-crypto (XYZ-* prefix = stocks/commodities/indices)
- Rank by 90-day ADV (notional volume)
- Top 100 (or N configurable)
- Refresh weekly (Sunday 00:00 UTC)
- ~257 active crypto perps on HL currently, so 100 is well within range

### HL-Specific Data Properties
- **Funding is hourly** (not 8h like Binance) — better granularity for signals
- **327 total perps** (257 active crypto + stocks/commodities/indices)
- **Settlement in USDC** (not USDT like Binance)
- **Rate limit**: 100 req/min
- **OHLCV via CCXT**: `fetch_ohlcv(sym, '4h', since=..., limit=5000)` works reliably
- **Funding via CCXT**: `fetch_funding_rate_history(sym, since=..., limit=500)` — capped at ~500 records (~21 days hourly)

## Feature Design Principles

1. **All features at 100% coverage** — no sparse external data problem (unlike Numerai's 8-40% coverage)
2. **Compute from raw OHLCV + funding** — no dependency on external starter features
3. **Spans in 4h-bar units** (not days): 1d = 6 bars, 1w = 42 bars
4. **Cross-sectional ranking mandatory** — per timestamp, across all N symbols
5. **Global features (same for all symbols) must NOT be ranked** — ranking a constant produces degenerate output

## Target Construction

- **Horizon**: 1 week = 168h / 4h = 42 bars forward return
- **Binning**: Cross-sectional quintiles per timestamp (0.0, 0.25, 0.5, 0.75, 1.0)
- **Purge gap**: ≥ 42 bars when computing features from target-derived columns

## Allocation Framework

- Blom order statistics: `z = Φ⁻¹((rank - 3/8) / (N + 1/4))`
- Expected returns: `μ̂ = IC × σ × z`
- Optimal weights: `w* = (1/λ) Σ⁻¹ μ̂`
- Σ: Ledoit-Wolf shrunk covariance from 90-day in-sample window
- 3-way portfolio: long top-20, short bottom-20, L/S dollar-neutral
- 12h rebalancing with 5% drift threshold

## Config Pattern (Frozen Dataclasses)

All hyperparameters in one file, organized by concern:
```python
@dataclass(frozen=True)
class HLSignalConfig:
    universe: UniverseConfig    # n_symbols, lookback_days, min_adv
    data: DataConfig            # exchange_id, timeframes, rate limits
    features: FeatureConfig     # EWMA spans, rolling windows
    target: TargetConfig        # horizon_bars, n_quintiles, purge_gap
    allocation: AllocationConfig # ic, risk_aversion, rebalance_freq
    risk: RiskConfig            # drawdown limits, position caps
```

Frozen dataclasses prevent accidental mutation and make configs safe to pass around.
