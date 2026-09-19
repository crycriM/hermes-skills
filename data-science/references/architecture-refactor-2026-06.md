# Architecture Refactor — June 2026

## New shared modules (consolidated from per-script duplication)

### `src/features/constants.py`
Single source of truth for all feature column name lists:
- `STARTER_FEATURES` — 22 Numerai-provided features
- `FUNDING_FEATURES` — 7 custom funding rate columns
- `ONCHAIN_FEATURES` — 4 custom TVL columns
- `GITHUB_FEATURES` — 5 custom dev activity columns
- `ALL_CUSTOM_FEATURES` — union of FUNDING + ONCHAIN + GITHUB

Import in scripts: `from src.features.constants import STARTER_FEATURES, ...`

Previously each of 12 scripts defined these inline (~180 lines of duplication).

### `src/features/cross_sectional.py`
Replaced the TODO stub with the canonical `cross_sectional_rank()` implementation.
Uses the safer pattern with `if c in result.columns` guard (silently skips missing
columns instead of crashing). Previously duplicated in 11 scripts (~80 lines).

Import: `from src.features.cross_sectional import cross_sectional_rank`

### `src/data_sources/io.py`
Shared `load_parquet_features(path, json_col)` — parses JSON columns from PIT store
parquet files into `custom_*` feature columns. Uses `row.get(json_col, "{}")` default
for robustness against null columns. Previously duplicated in 8 scripts (~200 lines).

Import: `from src.data_sources.io import load_parquet_features`

## Removed dead code

| What | Where | Why |
|------|-------|-----|
| DEEP_PARAMS | baseline.py | Demoted to comment — tested, loses on neutralized CORR |
| cloudpickle path | baseline.py save/load | Crypto tournament uses native LightGBM format only |
| inference/ package | src/inference/ | Empty __init__.py, zero consumers |
| monitoring/ package | src/monitoring/ | Empty __init__.py, zero consumers |
| regimes.py | src/features/ | 4-line stub — regime_detection.py supersedes it |
| scoring.py | src/numerai/ | 4-line stub — score queries not implemented |
| derived.py | src/data_sources/ | 1-line stub — multi-source combination not needed |
| DuckDB migration hack | pit_store/backfill.py | Handled "derivatives"→"derived" rename for column never produced |

## Remaining stubs (1 only)

- `src/features/transforms.py` — 4-line stub; real transforms (path signature, volume anomaly) in `advanced.py`. Imported by `train_with_novel_features.py` which would fail at runtime — pre-existing bug, not yet fixed.

## Deduplication totals

| Constant | Before | After |
|----------|--------|-------|
| STARTER_FEATURES | 12 inline copies | 1 import |
| cross_sectional_rank() | 11 inline copies | 1 shared function |
| load_parquet_features() | 8 inline copies | 1 shared function |
| FUNDING_FEATURES | 9 inline copies | 1 import |
| ONCHAIN_FEATURES | 6 inline copies | 1 import |
| GITHUB_FEATURES | 6 inline copies | 1 import |

~460 lines of duplication eliminated. 253 tests pass.
