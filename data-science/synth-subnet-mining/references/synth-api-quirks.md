# Synth API Quirks

## `/validation/scores/historical`
- GET `https://api.synthdata.co/validation/scores/historical`
- Params: `from` (ISO datetime), `to` (ISO datetime), `asset`, `time_length`, `time_increment`
- Paginates by default — use 1-day chunks (API has ~7-day max range)
- Returns array of `{miner_uid, asset, prompt_score, scored_time, crps, time_length}`
- No `start_time` in response — approximate as `scored_time - time_length`

## `/rewards/scores`
- GET `https://api.synthdata.co/rewards/scores`
- Accepts date-only format (`YYYY-MM-DD`) for `from`/`to`, NOT ISO datetime
- Uses `competition` param (slug: `crypto-1h`, `crypto-24h`, `com-equ-24h`), NOT deprecated `prompt_name`
- Returns array of `{miner_uid, smoothed_score, reward_weight, prompt_name, updated_at}`
- `prompt_name` in response is the full label (`"Crypto 24h"`), not the slug

## `/validation/realized-path`
- GET `https://api.synthdata.co/validation/realized-path`
- Params: `asset`, `start_time` (ISO datetime), `time_length`, `time_increment`
- Returns `{real_prices: [...]}` — the exact array the validator used for CRPS scoring
- Returns "No realized path available" → None if not found

## `/v2/leaderboard/historical`
- GET `https://api.synthdata.co/v2/leaderboard/historical`
- Params: `start_time` (ISO datetime), `end_time` (ISO datetime), `prompt_name` (slug or label)
- Returns per-miner leaderboard rows over the range

## `/v2/leaderboard/latest`
- GET `https://api.synthdata.co/v2/leaderboard/latest`
- Params: `prompt_name` (slug or label)
- Returns current leaderboard snapshot

## `monitoring.synthdata.co/v1` (miner dashboard API)
- `GET /v1/miners/rewards/pool` — params: `from`, `to` (date-only)
- Returns `{source, rows: [{date, usd}]}` — daily subnet miner pool in USD

## Backtester patches needed (as of 2026-07-31)

The `synth-lib` backtester (`synth_lib/backtester/backtest.py`) needed two patches:

1. `get_rewards_history()`: changed `from`/`to` params from `%Y-%m-%dT%H:%M:%SZ` to `%Y-%m-%d`
2. `get_rewards_history()`: changed param name from `prompt_name` to `competition` (value is the slug, unchanged)

## Asset price feeds (mirrors validator)

**Binance REST klines** — GET `/api/v3/klines`:
- Assets: BTC, ETH, SOL, XRP
- Interval: 1m
- Settlement guard: request +1 extra minute past end_time to verify kline has closed
- BINANCE_API_HOST env var escape hatch for geo-restricted regions (US CI → data-api.binance.vision)

**Hyperliquid candleSnapshot** — POST `https://api.hyperliquid.xyz/info`:
- Assets: HYPE, XAU, NVDAX, TSLAX, AAPLX, GOOGLX, SP500, SPCX, WTIOIL
- Body: `{"type": "candleSnapshot", "req": {"coin": "<symbol>", "interval": "1m", "startTime": <ms>, "endTime": <ms>}}`
- `req` wrapper is required (not flat format) — without it returns HTTP 422
- Max candles per call: 5000 (≈~3.5 days of 1m data)
- Settlement guard same as Binance: +1 minute witness

## Competition config (from synth.validator.competition_config)

```python
CRYPTO_24H = CompetitionConfig(
    label="Crypto 24h",
    time_length=86400,          # 24h in seconds
    time_increment=300,         # 5 min
    window_days=10,             # rolling average window
    asset_list=["BTC","ETH","SOL","XRP","HYPE"],
    scoring_intervals={"5min": 300, "30min": 1800, "3hour": 10800, "24hour_abs": 86400},
)

CRYPTO_1H = CompetitionConfig(
    label="Crypto 1h",
    time_length=3600,           # 1h
    time_increment=60,          # 1 min
    window_days=5,
    asset_list=["BTC","ETH","SOL","XRP","HYPE"],
    scoring_intervals={},       # special: 1,2,5,15,30,60min + gap series
)

COM_EQU_24H = CompetitionConfig(
    label="Commodities/Equities 24h",
    time_length=86400,
    time_increment=300,
    window_days=10,
    asset_list=["XAU","SP500","NVDAX","GOOGLX","TSLAX","AAPLX","WTIOIL","SPCX"],
    scoring_intervals={"5min": 300, "30min": 1800, "3hour": 10800, "24hour_abs": 86400},
)
```
