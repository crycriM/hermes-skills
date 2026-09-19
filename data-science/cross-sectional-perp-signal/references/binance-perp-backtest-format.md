# Binance Perp Walk-Forward Backtest — Data & Per-Bar Position Capture

## Binance Yearly Data Format

The primary data source for Binance perp backtests lives on `studioc` at:

```
/home/christian/python_working/long-short/data/bin_yearly/
```

### Files

| File | Size | Description |
|------|------|-------------|
| `bin_yearly_2022.parquet` | 152 MB | 2022 1h OHLCV |
| `bin_yearly_2023.parquet` | 374 MB | 2023 1h OHLCV |
| `bin_yearly_2024.parquet` | 362 MB | 2024 1h OHLCV |
| `bin_yearly_2025.parquet` | 419 MB | 2025 1h OHLCV |
| `bin_yearly_2026.parquet` | 82 MB | 2026 partial (to ~Apr) |

### Schema

- **Index:** DatetimeIndex (UTC, 1h bars)
- **Columns:** `{SYMBOL}_close` and `{SYMBOL}_volume` for each perp
- **Coverage:** ~354 USDT-M perp tickers (varies by year, grows over time)
- **Source:** Binance public data at data.binance.vision (S3: `s3-ap-northeast-1.amazonaws.com/data.binance.vision/data/futures/um/monthly/klines/`)

### Data Loading

The project code in `perp_strategy/run_backtest.py` loads via glob:

```python
DATA_PATH = os.path.expanduser("~/Python/github/data/bin_yearly/bin_yearly_202*.parquet")
files = sorted(glob.glob(DATA_PATH))
df = pd.concat([pd.read_parquet(f) for f in files])

# Tickerc configured to:
# close_cols: {ticker}_close → resample with "last" agg
# vol_cols:   {ticker}_volume → resample with "sum" agg
```

### Copy from studioc

```bash
# One file
scp studioc:/home/christian/python_working/long-short/data/bin_yearly/bin_yearly_2025.parquet ~/Python/github/data/bin_yearly/

# All at once
rsync -avP studioc:/home/christian/python_working/long-short/data/bin_yearly/bin_yearly_202*.parquet ~/Python/github/data/bin_yearly/
```

SSH config hostname for studioc is `studioc` (IP [REDACTED], user christian).

## The 0dte/perp_strategy Project

A multi-signal walk-forward backtesting framework for Binance perps, located at:

```
~/projects/0dte/
├── perp_strategy/
│   ├── run_backtest.py          # Grid search over (resample × lookback)
│   ├── run_portfolio.py         # Portfolio combiner (equal, inverse_vol)
│   ├── run_all_backtest.py      # Custom: run all 16 signals with per-bar capture
│   ├── signals/                 # 16 signal modules (BaseSignal subclass)
│   │   ├── vine_basket.py       # Best: 4h/14D, Sharpe 1.80
│   │   ├── egarch_vol.py        # 30min/30D, Sharpe 1.75
│   │   ├── momentum_reversion.py
│   │   ├── pca_residual.py
│   │   ├── adavol_spread.py
│   │   ├── cross_sectional_momentum.py
│   │   ├── copula_mispricing.py
│   │   ├── pairs_zscore.py
│   │   ├── rkc_ranking.py       # New: random kernel convolution
│   │   ├── neighbor_rkc.py
│   │   ├── waveletnet_ranking.py  # PyTorch-based wavelet network
│   │   ├── lead_lag_graph.py
│   │   ├── pci.py / pci_df2006.py
│   │   └── dcc_correlation.py
│   ├── backtest/
│   │   ├── perp_engine.py       # Event-driven engine with kill switches
│   │   ├── position.py          # PerpPosition, PerpTrade dataclasses
│   │   └── strategy_output.py   # Cache/load strategy results
│   ├── models/                  # AdaVol, DCC, data_augmentation
│   └── tests/
├── strategy_outputs/            # Cached run results
└── download_binance_perps.py    # Script to download from binance.vision S3
```

## Running a Full Backtest with Per-Bar Position Capture

Two scripts are available:

### `run_all_backtest.py` (modular, cached)

Loads data once, iterates all 16 signals in `BEST_CONFIGS`, saves per-bar positions,
then runs portfolio analysis. Best for regular re-runs — uses `strategy_outputs/` cache.

```bash
PYTHONPATH=. python3 perp_strategy/run_all_backtest.py
PYTHONPATH=. python3 perp_strategy/run_all_backtest.py --strategies egarch_vol adavol_spread  # subset
PYTHONPATH=. python3 perp_strategy/run_all_backtest.py --force  # re-run all
```

### `run_full_backtest.py` (standalone, inline)

Self-contained script (one file) that loads data, caches resamples per frequency,
runs all signals, and produces the portfolio analysis in one go. Useful for
one-shot analyses or when you want a single entry point.

```bash
PYTHONPATH=. python3 run_full_backtest.py
```

Both scripts produce the same output format and are interchangeable for the
per-bar position capture described below.

### What it captures

For every strategy at every bar, it records a `positions_per_bar.parquet` with:

| Column | Description |
|--------|-------------|
| `timestamp` | Bar timestamp |
| `strategy` | Strategy name |
| `asset` | Ticker or `__SUMMARY__` for aggregate row |
| `direction` | long / short / flat |
| `size_usd` | Notional position (signed: positive=long, negative=short) |
| `unrealized_pnl` | Gross PnL (mark-to-market only, no fees) |
| `accumulated_funding` | Cumulative funding paid/received |
| `capital` | Available cash |
| `total_equity` | capital + sum(position.equity) |
| `signal_score` | Average signal strength for open positions |

Each bar gets one row per open position PLUS one `__SUMMARY__` row per
strategy with aggregate values. This gives you both per-asset granularity
and per-strategy totals in one DataFrame.

### Net vs Gross PnL

- **Gross PnL** = `positions["unrealized_pnl"]` — pure mark-to-market, no fees, no funding
- **Net PnL** = `positions["total_equity"].pct_change()` — after fees (0.05% taker entry + exit), funding, and stop-loss/take-profit exits

The trade records store final PnL with fees subtracted at exit.

### Multi-Strategy Portfolio Analysis

After collecting per-bar data for all strategies:

1. Align all timestamps to a common index
2. Build a strategy return DataFrame (one column per strategy)
3. Compute full-sample correlation matrix
4. Compute rolling 60-bar correlation for each pair
5. Compute mean position (net notional) across strategies per bar

```python
# Simplified recipe
ret_df = pd.DataFrame(index=all_timestamps)
for name, sd in strategy_data.items():
    ret_df[name] = sd["equity"].pct_change().reindex(all_timestamps).fillna(0.0)

full_corr = ret_df.corr()
roll_corr = ret_df.rolling(60).corr(pairwise=True)
mean_pos = size_df.mean(axis=1)
```

### Pitfalls

1. **PYTHONPATH required in background processes.** When running via
   `terminal(background=true)` the sys.path insert in the script's __main__
   guard may not resolve correctly. Always prefix with `PYTHONPATH=.`:
   ```bash
   PYTHONPATH=. python3 perp_strategy/run_all_backtest.py  # works
   ```

2. **Torch dependency.** `waveletnet_ranking` imports torch + tsai at
   module level (not lazily). All other signals import fine without it,
   but even importing `perp_strategy.signals` fails if torch is missing.
   Fix: `pip3 install --user --break-system-packages torch tsai`.

3. **arch and copula packages** needed for EGARCH and copula signals:
   `pip3 install --user --break-system-packages arch copula`.
