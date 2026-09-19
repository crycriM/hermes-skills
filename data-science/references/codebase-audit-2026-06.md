# Codebase Audit — 2026-06-09

69 Python files, 8,668 LOC, 18 test files, 16 scripts, 15 source modules, 5 empty stubs.

## Duplication Map

### STARTER_FEATURES (22 columns) — duplicated 12 times
Every training/submission script redefines the same list inline:
- scripts/train_lambdarank.py
- scripts/train_all_features.py
- scripts/train_regime_model.py
- scripts/train_regime_beta.py
- scripts/train_lambdarank_beta.py
- scripts/train_s2_combined.py
- scripts/train_with_custom_features.py
- scripts/train_with_funding_rates.py
- scripts/train_with_novel_features.py
- scripts/tune_hyperparams.py
- scripts/submit_live.py
- scripts/submit_s2_live.py

**Fix target:** Single source in `src/features/constants.py` with `STARTER_FEATURES = [...]`, imported everywhere.

### FUNDING_FEATURES — duplicated 9 times
### ONCHAIN_FEATURES — duplicated 6 times
### GITHUB_FEATURES — duplicated 6 times
### load_parquet_features() — duplicated 8 times (identical JSON parsing)
### cross_sectional_rank() — duplicated 11 times (identical polars ranking)

## Stub Files (5 empty, TODO-only)
| File | Status |
|------|--------|
| src/features/transforms.py | "TODO: Implement raw feature transformations" |
| src/features/regimes.py | "TODO: Implement regime detection" |
| src/features/cross_sectional.py | "TODO: Implement cross-sectional feature engineering" |
| src/numerai/scoring.py | "TODO: Implement get_scores()" |
| src/data_sources/derived.py | "stub for future multi-source feature combination" |

## Misleading References
- **CLAUDE.md** references `src/features/perp_signals.py` (does not exist). Actual perp features are in 4 separate files: perp_funding_alpha.py, perp_vol_forecast.py, perp_copula.py, perp_adavol.py.
- **README.md** references `src/inference/` directory (exists but contains only empty `__init__.py`).
- **Dockerfile** CMD references `src.orchestrate` (does not exist).

## Stale Defaults
- `DEFAULT_PARAMS` in baseline.py: `lr=0.01, max_depth=5, num_leaves=31`
- Production LambdaRank: `lr=0.02, max_depth=3, num_leaves=15, min_data_in_leaf=500`
- The class defaults are old Numerai-recommended values, not what the tuned sweep found.

## Debug Artifacts in scripts/
- scripts/debug_neutralize.py — ad-hoc neutralization check (47 lines)
- scripts/debug_svd.py — feature variance check (38 lines)
- scripts/smoke_test.py — should be in tests/ (56 lines)

## Incomplete Abstractions
- `pit_store/backfill.py` insert_features() has inline migration hack for old "derivatives" → "derived" column rename
- `numerai/download.py` and `numerai/auth.py` have overlapping download logic with different patterns
- All `__init__.py` files are empty — no package-level exports
- `train_baseline.py` uses simple chronological split (overestimates CORR ~26% vs purged CV)

## Historical Docs (865 lines, overlapping)
- docs/numerai_crypto_bot_plan-1.md
- docs/numerai_crypto_bot_plan-2-improved.md
- docs/numerai_crypto_spec_addendum.md
- docs/IMPROVEMENT_PLAN_NUMERAI.md

## Execution Status (2026-06-09 session) — ALL PHASES COMPLETE

**Phase 1 (T1–T3) — DONE:**
- Created `src/features/constants.py` with all 4 feature lists + ALL_CUSTOM_FEATURES
- Replaced `src/features/cross_sectional.py` stub with canonical `cross_sectional_rank()`
- Created `src/data_sources/io.py` with shared `load_parquet_features()`
- Updated all scripts to import from shared modules — zero inline duplication remains
- ~460 lines of duplication eliminated. 253 tests pass.

**Quick wins (F1–F4) — DONE:**
- DEEP_PARAMS demoted to comment in baseline.py
- Dockerfile CMD fixed: `src.orchestrate` → `scripts/submit_live.py`
- `src/inference/` and `src/monitoring/` empty packages deleted
- cloudpickle dead code removed from LGBMBaseline.save()/load()

**Phase 2 (T4–T6) — DONE:**
- Deleted 3 dead stubs: regimes.py, scoring.py, derived.py
- Updated DEFAULT_PARAMS to production-tuned values (lr=0.02, max_depth=3, num_leaves=15, min_data_in_leaf=500)
- Created `src/features/perp_signals.py` re-export module (CLAUDE.md reference now valid)
- Updated 4 test assertions to match new defaults. 253 tests pass.

**Phase 3 (T7–T9) — DONE:**
- Unified download logic: `download.py` refactored to use common `_download_and_read()` helper via `auth.download_dataset()`
- Added `__init__.py` exports to features, models, validation, numerai packages
- Removed DuckDB migration hack from `pit_store/backfill.py` (dead code — "derivatives" column never produced)
- Rewrote 7 download tests to match new architecture. 253 tests pass.

**Remaining stubs (1 of 5 still present):**
- `src/features/transforms.py` — still a 4-line stub; real transforms (path signature, volume anomaly) are in `advanced.py`. Imported by `train_with_novel_features.py` which would fail at runtime — pre-existing bug, not yet fixed.
