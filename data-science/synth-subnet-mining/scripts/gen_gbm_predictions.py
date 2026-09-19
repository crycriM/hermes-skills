#!/usr/bin/env python3
"""
Generate GBM reference miner predictions for the Synth subnet backtester.
Fetches scored prompt times from the Synth API and generates one JSON
prediction file per prompt using the reference GBM code.

Usage:
  cd ~/projects/synth-miner/synth-lib
  source .venv/bin/activate
  PYTHONPATH=~/projects/synth-miner/synth-subnet python3 gen_gbm_predictions.py

Then:
  uv run synth_lib/backtester/scripts/run_backtest.py \\
    --miner-name gbm_reference --asset BTC --competition crypto-24h --days 2
"""
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, '/home/cricri/projects/synth-miner/synth-subnet')

from synth.miner.price_simulation import get_asset_price, simulate_crypto_price_paths
from synth.miner.simulations import SIGMA_MAP

UTC = timezone.utc

ASSET = "BTC"
COMPETITION = "crypto-24h"
TIME_LENGTH = 86400       # 24h
TIME_INCREMENT = 300      # 5 min
NUM_SIMULATIONS = 100
DAYS_FETCH = 7

# Map asset to competition config
COMPETITION_PARAMS = {
    "crypto-24h": {"time_length": 86400, "time_increment": 300},
    "crypto-1h": {"time_length": 3600, "time_increment": 60},
    "com-equ-24h": {"time_length": 86400, "time_increment": 300},
}


def fetch_scored_prompt_times(asset, query_start, query_end, time_length, time_increment):
    """Fetch unique start times from miniconda scores API."""
    import requests

    scores = []
    cursor = query_start
    url = "https://api.synthdata.co/validation/scores/historical"

    while cursor < query_end:
        chunk_end = min(cursor + timedelta(days=1), query_end)
        params = {
            "from": cursor.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "to": chunk_end.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "asset": asset,
            "time_length": time_length,
            "time_increment": time_increment,
        }
        resp = requests.get(url, params=params, timeout=30)
        data = resp.json()
        if data:
            scores.extend(data)
        cursor = chunk_end

    if not scores:
        raise RuntimeError(f"No scores found for {asset} in range.")

    import pandas as pd
    df = pd.DataFrame(scores)
    df["scored_time"] = pd.to_datetime(df["scored_time"], utc=True)
    df["start_time"] = df["scored_time"] - pd.Timedelta(seconds=time_length)
    return df["start_time"].drop_duplicates().sort_values()


def generate_prediction(start_time_ts, current_price, asset, time_length, time_increment, num_simulations):
    """Generate a single prediction dict using the reference GBM."""
    sigma = SIGMA_MAP.get(asset, 0.005)
    paths = simulate_crypto_price_paths(
        current_price=current_price,
        time_increment=time_increment,
        time_length=time_length,
        num_simulations=num_simulations,
        sigma=sigma,
    )
    num_steps = time_length // time_increment
    return {
        "start_timestamp": int(start_time_ts.timestamp()),
        "asset": asset,
        "time_increment": time_increment,
        "time_length": time_length,
        "num_simulations": num_simulations,
        "num_steps": num_steps,
        "paths": paths.tolist(),
    }


def main():
    miner_name = "gbm_reference"
    output_dir = Path(f"miner_outputs/{miner_name}/predictions")
    output_dir.mkdir(parents=True, exist_ok=True)

    now = datetime.now(UTC)
    query_start = now - timedelta(days=DAYS_FETCH)

    start_times = fetch_scored_prompt_times(
        ASSET, query_start, now, TIME_LENGTH, TIME_INCREMENT
    )
    print(f"Generating {len(start_times)} GBM predictions for {ASSET}...")

    generated = 0
    for st in start_times:
        st_ts = st.to_pydatetime().replace(tzinfo=UTC)
        current_price = get_asset_price(ASSET)
        if current_price is None:
            print(f"  Skipping {st_ts}: no price")
            continue

        pred = generate_prediction(
            st_ts, current_price, ASSET,
            TIME_LENGTH, TIME_INCREMENT, NUM_SIMULATIONS
        )

        filename = st_ts.strftime("%Y-%m-%d_%H:%M:%SZ") + f"_{ASSET}_{TIME_LENGTH}.json"
        (output_dir / filename).write_text(json.dumps(pred))
        generated += 1

    print(f"Generated {generated} prediction files in {output_dir}/")


if __name__ == "__main__":
    main()
