# Macro Data Sources for Regime Detection

## Overview

The regime detection module (`src/features/regime_detection.py`) uses three external data sources to compute per-date global market regime features. All three are point-in-time (daily frequency, no lookahead).

## BTC Daily OHLCV

**File:** `data/btc_daily.parquet`
**Source:** Binance via CCXT
**Columns:** date, open, high, low, close, volume
**Range:** 2019-01-01 → current
**Refresh command:**
```bash
cd /home/cricri/projects/numerai/numerai-crypto-bot
uv run python3 -c "
import ccxt, polars as pl
ex = ccxt.binance()
since = ex.parse8601('2019-01-01T00:00:00Z')
all_ohlcv = []
while True:
    ohlcv = ex.fetch_ohlcv('BTC/USDT', '1d', since=since, limit=1000)
    if not ohlcv: break
    all_ohlcv.extend(ohlcv)
    since = ohlcv[-1][0] + 1
    if len(ohlcv) < 1000: break
df = pl.DataFrame(all_ohlcv, schema=['timestamp','open','high','low','close','volume'], orient='row')
df = df.with_columns(pl.from_epoch('timestamp', time_unit='ms').dt.date().alias('date'))
df.select(['date','open','high','low','close','volume']).write_parquet('data/btc_daily.parquet')
print(f'{len(df)} rows, {df[\"date\"].min()} -> {df[\"date\"].max()}')
"
```
**Refresh frequency:** Every ~3 months (historical BTC candles don't change). Only needed to pick up recent data.

## Gold Futures (GC=F)

**File:** `data/gold_daily.parquet`
**Source:** Yahoo Finance via yfinance (`yfinance` package)
**Columns:** date, close
**Range:** 2019-01-02 → current
**Refresh command:**
```bash
cd /home/cricri/projects/numerai/numerai-crypto-bot
uv run python3 -c "
import yfinance as yf, polars as pl
data = yf.download('GC=F', start='2019-01-01', end='2026-12-31', auto_adjust=False, progress=False)
df = pl.DataFrame({
    'date': [d.date() for d in data.index],
    'close': [float(v) for v in data['Close'].values.flatten()]
}).sort('date')
df.write_parquet('data/gold_daily.parquet')
print(f'{len(df)} rows, {df[\"date\"].min()} -> {df[\"date\"].max()}')
"
```
**Alternative source:** PAXG/USDT on Binance via CCXT (shorter history: 2020-08-28 →). Gold futures (GC=F) preferred for longer history.
**Refresh frequency:** Monthly (futures prices update daily).

## 10-Year Treasury Yield (^TNX)

**File:** `data/treasury_10y_daily.parquet`
**Source:** Yahoo Finance via yfinance
**Columns:** date, close (yield in percent, e.g., 4.5 = 4.5%)
**Range:** 2019-01-02 → current
**Refresh command:**
```bash
cd /home/cricri/projects/numerai/numerai-crypto-bot
uv run python3 -c "
import yfinance as yf, polars as pl
data = yf.download('^TNX', start='2019-01-01', end='2026-12-31', auto_adjust=False, progress=False)
df = pl.DataFrame({
    'date': [d.date() for d in data.index],
    'close': [float(v) for v in data['Close'].values.flatten()]
}).sort('date')
df.write_parquet('data/treasury_10y_daily.parquet')
print(f'{len(df)} rows, {df[\"date\"].min()} -> {df[\"date\"].max()}')
"
```
**Refresh frequency:** Monthly.

## FRED API (M2, Fed Funds — alternative, network unreliable)

FRED (Federal Reserve Economic Data) provides M2 Money Supply (M2SL), Fed Funds Rate (DFF), and 10Y Treasury (DGS10) via CSV download at `https://fred.stlouisfed.org/graph/fredgraph.csv?id=SERIES_ID&cosd=2019-01-01&coed=2026-12-31`. No API key required for CSV downloads.

**Note:** FRED CSV downloads were unreliable during development (connection timeouts from the server environment). yfinance is the preferred source for treasury yields. FRED may work from different network environments — try if yfinance is unavailable.

## Regime Features Computed

From these three data sources, `compute_regime_features()` produces 13 regime features:

| # | Feature | Source | Description |
|---|---------|--------|-------------|
| 1 | regime_btc_return_5d | BTC | 5-day log return |
| 2 | regime_btc_return_20d | BTC | 20-day log return |
| 3 | regime_btc_vol_20d | BTC | 20-day rolling std of daily returns |
| 4 | regime_btc_vol_60d | BTC | 60-day rolling std |
| 5 | regime_btc_drawdown_60d | BTC | % below 60-day high |
| 6 | regime_btc_volume_ratio | BTC | 20d/60d volume ratio |
| 7 | regime_gold_return_20d | Gold | 20-day log return |
| 8 | regime_gold_vol_20d | Gold | 20-day rolling std |
| 9 | regime_gold_drawdown_60d | Gold | % below 60-day high |
| 10 | regime_treasury_change_20d | Treasury | 20-day change in 10Y yield |
| 11 | regime_treasury_level | Treasury | Absolute 10Y yield level |
| 12 | regime_real_yield_20d | Combined | Treasury level - gold return×100 |
| 13 | regime_sentiment | Coinybubble | Crypto fear/greed index |

Features 7-12 (macro) are optional — the regime detection and beta feature computation work without them. The fallback fills missing columns with 0.0.

## Installation

```bash
cd /home/cricri/projects/numerai/numerai-crypto-bot
uv add yfinance  # one-time, for gold and treasury
```
CCXT is already a project dependency with the `--features binance` flag.
