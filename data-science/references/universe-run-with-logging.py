#!/usr/bin/env python3
"""Universe selection with comprehensive data logging.

This script runs the full PERP32 universe pipeline and logs every intermediate
data point (CLS inputs, scores, selection process) to a JSON artifact.

Usage:
    uv run python -m src.universe.run_with_logging
    uv run python -m src.universe.run_with_logging --init-mode
    uv run python -m src.universe.run_with_logging --perimeter PERP128
    uv run python -m src.universe.run_with_logging --reference-date 2026-05-27

Output:
    docs/examples/universe_run_log.json — full data log with:
    - run_metadata (config, gates, reference date)
    - stage_1_raw_candidates (per-exchange symbol counts)
    - stage_2_filtered (eligible symbols, cross-listed)
    - stage_3_cls_inputs (full ADV/AOI/trades per symbol with exchange detail)
    - stage_4_cls_scores (ranked CLS results with z-scores)
    - stage_5_sensitivity (DEFAULT vs HIGH_FIDELITY comparison)
    - stage_6_selection (turnover stats, alternates)
    - final_32 (selected assets with full metrics)
    - data_sources (provenance: preselection, TimescaleDB, exchange adapters)

Key diagnostic columns in the log:
- adv: median daily volume (180-day window, cross-exchange)
- z_adv: z-scored ADV (CLS component)
- z_oi: z-scored open interest (currently 0 for all symbols)
- z_atradecount: z-scored trade frequency per dollar (currently disabled)
- cross_listed: listed on ≥2 eligible exchanges (+0.10 CLS bonus)

To inspect the log:
    python3 -c "import json; d=json.load(open('docs/examples/universe_run_log.json')); print(json.dumps(d['final_32'], indent=2))"
"""
