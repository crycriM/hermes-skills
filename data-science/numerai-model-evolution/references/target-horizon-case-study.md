# Target-horizon diversification: the 60D model (validated case study, 2026-08-20)

Second phase of the m5 investigation: choosing a distinct job for the third
slot (m5_beta) after residual-label training was rejected. The transferable
lesson is how to evaluate an alternative training-target horizon honestly.

## The opportunity

The Numerai Crypto training parquet ships `target_binned_return_60` alongside
the scored 20D target — unused by every model on the account. Numerai's own
spec notes training on 60D can help 20D performance. When a model is under
performing and shares its feature stack with a sibling, an unused target
column is the cheapest genuinely-new axis available.

## The purge-scaling leak (critical methodological catch)

A 60-day forward target means training rows near the validation boundary
share 60 days of forward returns with validation rows. The standard 25-day
purge (sized for the 20D target) LEAKS: with purge=25 the 60D model scored
0.1368 raw CORR on the 20D eval target; with the honest purge=65 it scored
0.1260 — roughly 1pp of the apparent edge was leakage.

**Rule: purge window must be ≥ target horizon + embargo. Scale it per
experiment; never reuse the default purge when changing the target column.**

The harness must accept a purge parameter, and reports must record it. If a
horizon experiment shows an edge, re-run it with the honest purge before
believing the number.

## Honest results (purge=65, eval on 20D target, 77-feature stack)

| Model | Raw | λ=0.5 | λ=0.7 | λ=1.0 | Retention @0.5 |
|---|---:|---:|---:|---:|---:|
| 20D target | 0.1401 | 0.0998 | 0.0797 | 0.0537 | 71.2% |
| 60D target | 0.1260 | 0.0991 | **0.0829** | **0.0601** | **78.6%** |

- The 20D model wins on raw CORR (it trains on the scored horizon) — expected.
- The 60D model wins at high neutralization (λ≥0.7) and retains more of its
  signal through the lambda ladder: its alpha is structurally less
  starter-loaded.
- Prediction-vs-prediction Spearman vs the 20D model: 0.86 — correlated but
  genuinely different (slower-horizon signal).

## What the 60D model is NOT

- **Not a CORR booster:** a 50/50 rank-normalized ensemble of the 20D and 60D
  models scored 0.137 vs 0.140 for the 20D single — no combined lift. Do not
  sell horizon diversification as a CORR play.
- **Not validated for MMC yet:** the case for it is portfolio structure
  (orthogonality), which only live resolved scores can confirm.

## Portfolio-ladder pattern

When running multiple slots on the same tournament, assign each a deliberate
position on the CORR/MMC trade-off rather than making every slot chase CORR:

| Slot | Target | λ | Role |
|---|---|---|---|
| Production | 20D | 0.0 | CORR maximizer (frozen) |
| Second | 20D | 0.5 | balanced |
| Third | 60D | 0.7 | max-orthogonality / MMC tilt |

Choose per-slot lambda by where each model's lambda ladder crosses the
others: the 60D model's ladder dominates at high λ, so that is where it
earns its slot. Escalation path if MMC stays flat: raise λ one step (60D at
λ=1.0 measured 0.060, the most orthogonal config).

## Diagnostics worth keeping

- Fold-1 weakness (0.068 raw on 292 train dates) is structural for
  long-horizon targets — early-period history is thin. Live training uses
  all history, so it mostly self-corrects; do not reject a horizon because
  its earliest fold is weak.
- Harness extensions that made this possible: `--target`, `--eval-target`,
  `--purge` CLI overrides and `--save-preds` parquet export (enables
  pred-vs-pred correlation and offline ensemble analysis without retraining).

## Artifacts (case-specific, on this machine)

- `~/projects/numerai-folders/numerai-crypto-bot/scripts/run_m5_rc_experiment.py`
- `src/docs/m5_beta_v2_plan.md` — full plan with rejected alternatives
- `data/exports/m5_rc_v2_*_60*_report.json` and `*_preds.parquet`
