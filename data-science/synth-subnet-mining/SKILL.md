---
name: synth-subnet-mining
description: "Synth SN50: clone, GBM ref, backtester, CRPS baseline."
version: 1.0.0
tags: [synth, bittensor, crps, mining, subnet, sn50, forecasting]
---

# Synth Subnet Mining

Synth (Bittensor SN50, by Mode Network) — probabilistic price-path forecasting.
Miners submit Monte Carlo price paths; validators score with CRPS.

## Repos

- `synth-subnet/` — miner code (reference GBM, price feeds)
- `synth-lib/` — backtester

Both live under `~/projects/synth-miner/`.

## Setup

```bash
mkdir -p ~/projects/synth-miner && cd ~/projects/synth-miner
git clone https://github.com/synthdataco/synth-subnet.git
git clone https://github.com/synthdataco/synth-lib.git
cd synth-subnet && uv sync
cd ../synth-lib && uv sync
```

## Reference miner validation

```bash
cd ~/projects/synth-miner/synth-subnet
PYTHONPATH=. .venv/bin/python synth/miner/run.py
# → prints "CORRECT"
```

## Backtester

The backtester at `synth-lib/synth_lib/backtester/` replays the validator scoring pipeline (CRPS, smoothed scores, rank, estimated earnings) against historical market data.

## Prediction generation

Two scripts under `scripts/` automate the workflow. They fetch scored prompt times from the API, generate predictions using the respective model, and output JSON files in the format expected by the backtester.

**Always** use the miner code to generate predictions — the backtester's random-walk fallback does not represent the reference GBM baseline.

### GBM reference (baseline)

```bash
cd ~/projects/synth-miner/synth-lib
source .venv/bin/activate
uv pip install arch  # needed for EGARCH, optional for GBM
PYTHONPATH=~/projects/synth-miner/synth-subnet \
  python3 scripts/gen_gbm_predictions.py
```

### EGARCH-FHS (volatility clustering + fat tails)

```bash
cd ~/projects/synth-miner/synth-lib
source .venv/bin/activate
uv pip install arch
PYTHONPATH=~/projects/synth-miner/synth-subnet \
  python3 scripts/gen_egarch_predictions.py
```

## Running the backtester

```bash
cd ~/projects/synth-miner/synth-lib && source .venv/bin/activate
uv run synth_lib/backtester/scripts/run_backtest.py \
  --miner-name <miner_name> --asset BTC \
  --competition crypto-24h --days 2
```

## Known baseline scores (BTC, Crypto 24h, 2 days, July 2026)

| Model | Smoothed score | Mean CRPS | Rank | Notes |
|---|---|---|---|---|
| GBM (σ=0.00541) | 303.59 | 2947.61 | 257/257 | Reference, constant vol, normal innovations |
| EGARCH-FHS | 105.35 | 2748.30 | 257/257 | -65% score, still last |

EGARCH-FHS captures volatility clustering and fat tails but the top miners (~<50 smoothed score) likely layer on multi-asset correlations, regime switching, and/or jump components.

## Pitfalls

- **Backtester random fallback != GBM baseline**: The backtester generates random walks (0.001 σ) when no predictions exist. Always generate predictions using the miner code for a real baseline.
- **`/rewards/scores` API changed**: Uses `competition` param (slug) not `prompt_name`. Date format is `YYYY-MM-DD`, not ISO datetime.
- **GBM ranks last**: The reference GBM is intentionally naive — expect rank ~257/257 as the CRPS floor to beat.
- **EGARCH also ranks last**: Even with volatility clustering, single-asset EGARCH can't compete with the top miners' multi-asset ensemble approaches.
- **`arch` 8.0.0 API quirk**: `.conditional_volatility` and `.std_resid` return numpy arrays, not pandas Series. Use `pd.Series(float_array).dropna().values` instead of `.dropna()` on the raw array.
- **Predictions naming**: Format `{start_time_iso}_{asset}_{time_length}.json`.
