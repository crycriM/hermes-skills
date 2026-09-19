#!/usr/bin/env python3
"""
Generate EGARCH-FHS predictions for the Synth subnet backtester.
Captures volatility clustering (EGARCH) + fat tails (filtered historical innovations).

Requirements: arch package (arch==8.0.0+)
  cd ~/projects/synth-miner/synth-lib && uv pip install arch

Usage:
  cd ~/projects/synth-miner/synth-lib
  source .venv/bin/activate
  PYTHONPATH=~/projects/synth-miner/synth-subnet python3 gen_egarch_predictions.py

Then:
  uv run synth_lib/backtester/scripts/run_backtest.py \\
    --miner-name egarch_fhs --asset BTC --competition crypto-24h --days 2

Notes:
- Fits EGARCH(1,1) on ~500 days of daily log returns from Binance
- Bootstraps standardized residuals for fat-tailed/skewed innovations
- Blends EGARCH cond vol (70%) with historical vol (30%) to prevent wild forecasts
- EGARCH score is ~105 (vs GBM 303) but still ranks last at 257/257
- arch 8.0.0 returns numpy arrays (not pandas) for .conditional_volatility and .std_resid
"""
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, '/home/cricri/projects/synth-miner/synth-subnet')

from arch import arch_model
from synth.miner.price_simulation import get_asset_price
from synth.miner.simulations import SIGMA_MAP

UTC = timezone.utc

ASSET = "BTC"
COMPETITION = "crypto-24h"
TIME_LENGTH = 86400
TIME_INCREMENT = 300
NUM_SIMULATIONS = 100
DAYS_FETCH = 7
HISTORICAL_DAYS = 500


def fetch_historical_returns(asset, days=500):
    """Fetch daily close prices from Binance, return log returns and last close."""
    import requests

    asset_map = {"BTC": "BTCUSDT", "ETH": "ETHUSDT", "SOL": "SOLUSDT", "XRP": "XRPUSDT"}
    symbol = asset_map.get(asset, asset + "USDT")

    resp = requests.get(
        "https://api.binance.com/api/v3/klines",
        params={"symbol": symbol, "interval": "1d", "limit": min(days, 1000)},
        timeout=30,
    )
    resp.raise_for_status()
    closes = np.array([float(k[4]) for k in resp.json()])
    log_returns = np.diff(np.log(closes))
    return log_returns, closes[-1]


def fit_egarch(returns, p=1, o=1, q=1):
    """Fit EGARCH(p,o,q). Returns are daily log returns."""
    model = arch_model(returns * 100, vol="EGARCH", p=p, o=o, q=q, dist="normal")
    return model.fit(disp="off", update_freq=0)


def simulate_paths(current_price, egarch_res, raw_returns, sigma_override=None):
    """Generate one batch of EGARCH-FHS price paths."""
    one_hour = 3600
    dt = TIME_INCREMENT / one_hour
    num_steps = int(TIME_LENGTH / TIME_INCREMENT)

    # Standardized residuals = filtered historical innovations
    std_resid = pd.Series(egarch_res.std_resid).dropna().values

    # Scale to intraday vol
    last_vol_daily_pct = egarch_res.conditional_volatility[-1]
    steps_per_day = 24.0 / dt
    vol_per_step = (last_vol_daily_pct / 100.0) / np.sqrt(steps_per_day)
    hist_vol_daily = np.std(raw_returns)
    hist_vol_per_step = hist_vol_daily / np.sqrt(steps_per_day)
    sigma_step = 0.7 * vol_per_step + 0.3 * hist_vol_per_step

    paths = np.zeros((NUM_SIMULATIONS, num_steps + 1))
    paths[:, 0] = current_price

    for i in range(NUM_SIMULATIONS):
        boot = np.random.randint(0, len(std_resid), size=num_steps)
        paths[i, 1:] = current_price * np.exp(np.cumsum(std_resid[boot] * sigma_step))

    return paths


def main():
    miner_name = "egarch_fhs"
    output_dir = Path(f"miner_outputs/{miner_name}/predictions")
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Fitting EGARCH(1,1) on {HISTORICAL_DAYS}d of {ASSET} daily returns...")
    raw_returns, _ = fetch_historical_returns(ASSET, days=HISTORICAL_DAYS)
    egarch_res = fit_egarch(raw_returns)
    print(f"  Last cond vol: {egarch_res.conditional_volatility[-1]:.4f}% daily")
    print(f"  AIC: {egarch_res.aic:.1f}")

    now = datetime.now(UTC)
    query_start = now - timedelta(days=DAYS_FETCH)

    import requests
    url = "https://api.synthdata.co/validation/scores/historical"
    scores = []
    cursor = query_start
    while cursor < now:
        chunk_end = min(cursor + timedelta(days=1), now)
        params = {
            "from": cursor.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "to": chunk_end.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "asset": ASSET,
            "time_length": TIME_LENGTH,
            "time_increment": TIME_INCREMENT,
        }
        resp = requests.get(url, params=params, timeout=30)
        data = resp.json()
        if data:
            scores.extend(data)
        cursor = chunk_end

    if not scores:
        raise RuntimeError("No scores found")

    df = pd.DataFrame(scores)
    df["scored_time"] = pd.to_datetime(df["scored_time"], utc=True)
    df["start_time"] = df["scored_time"] - pd.Timedelta(seconds=TIME_LENGTH)
    start_times = df["start_time"].drop_duplicates().sort_values()

    print(f"Generating {len(start_times)} EGARCH-FHS predictions...")
    generated = 0
    for st in start_times:
        st_ts = st.to_pydatetime().replace(tzinfo=UTC)
        price = get_asset_price(ASSET)
        if price is None:
            continue

        paths = simulate_paths(price, egarch_res, raw_returns)
        pred = {
            "start_timestamp": int(st_ts.timestamp()),
            "asset": ASSET,
            "time_increment": TIME_INCREMENT,
            "time_length": TIME_LENGTH,
            "num_simulations": NUM_SIMULATIONS,
            "num_steps": int(TIME_LENGTH / TIME_INCREMENT),
            "paths": paths.tolist(),
        }

        filename = st_ts.strftime("%Y-%m-%d_%H:%M:%SZ") + f"_{ASSET}_{TIME_LENGTH}.json"
        (output_dir / filename).write_text(json.dumps(pred))
        generated += 1

    print(f"Generated {generated} predictions for {miner_name}")


if __name__ == "__main__":
    main()
