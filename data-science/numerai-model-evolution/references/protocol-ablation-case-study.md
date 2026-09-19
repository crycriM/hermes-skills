# Numerai Crypto protocol-ablation results (validated case study, 2026-08-20)

Measured outcome of the m5_rc v2 investigation. Use as a reference point when
running the same ablations on a new model or tournament; absolute numbers are
case-specific, the ratios and signatures are the transferable part.

## Setup

- Harness: matched purged walk-forward CV, 4 valid folds (fold 0 structurally
  empty — first block has no training dates before the purge cutoff), 25-day
  purge, 5-day embargo, fixed 2,000-tree LightGBM, per-date Spearman vs the
  raw target. Neutralization: ridge-stable per-date OLS (α=1e-4) against the
  22 ranked starter features, blend `(1-λ)·pred + λ·residual`.

## Protocol penalty decomposition (identical 97-feature stack)

| Protocol | Raw CORR | λ=0.5 | λ=1.0 |
|---|---:|---:|---:|
| L2 regression, raw target | 0.14352 | 0.10186 | 0.05343 |
| LambdaRank, raw quintile target | 0.07577 | 0.06064 | 0.02881 |
| LambdaRank, residualized+binned target (old m5_rc) | 0.03293 | 0.03644 | 0.03789 |

- Objective penalty (L2-raw → LambdaRank-raw): −6.8pp.
- Label-transform penalty (LambdaRank-raw → LambdaRank-residualized): −4.3pp.
- Old protocol retains ~23% of achievable signal.
- **Diagnostic signature of over-transformed labels:** the residualized
  protocol's λ-ladder is *increasing* (raw worse than neutralized) because
  residualized training already strips starter-correlated signal, so
  inference-time neutralization adds nothing. A healthy raw-target model
  shows a monotonically decreasing λ-ladder.

## Feature-family ablation (L2, raw target)

| Stack | Features | Raw CORR | λ=0.5 |
|---|---:|---:|---:|
| 22 starters only | 22 | 0.13330 | 0.08687 |
| Production stack | 66 | 0.12937 | 0.08950 |
| + volume_alpha only | 69 | 0.14225 | 0.10157 |
| + adavol only | 74 | 0.13717 | 0.09510 |
| + volume_alpha + adavol (chosen) | 77 | 0.14009 | 0.09981 |
| + all 5 S2 families | 97 | 0.14352 | 0.10186 |

- volume_alpha strongest (+1.3pp raw over production), adavol second (+0.8pp).
- funding_alpha, vol_forecast, copula each ran *below* the production
  baseline individually — dead weight in the combined stack.
- Full stack's +0.002 CORR over the selected 77-feature stack did not justify
  carrying 20 dead features.
- colsample_bytree grid on the 97-feature stack: 0.1 (0.14352) > 0.25
  (0.13828) > 0.5 (0.13511). The "low colsample starves large stacks"
  hypothesis was wrong at these sizes — test it, don't assume it.

## Live confirmation (official final-day scores)

| Model | Rounds | Mean CORR | MMC mean |
|---|---:|---:|---:|
| m5_draft (L2 raw target) | 51 | 0.14625 | +0.02438 |
| m5_rc (LambdaRank, residualized+binned) | 49 | 0.09821 | +0.00243 |
| m5_beta (L2, global-β residual labels) | 20 | 0.02558 | −0.03795 |

m5_beta isolates the residual-label axis live (same L2 objective as m5_draft,
only the label differs) and is the worst model — a near-experimental control
confirming the CV conclusion with no CV caveats.

## Score-cache measurement caveat

Averaging all day-level score entries understated m5_rc (~0.036) versus the
final-day-per-round mean (0.098). Always aggregate `submission_scores` by
round taking the last scoring day per round before comparing models —
day-level entries mix partially-resolved rounds.

## Deployed recipe (m5_rc v2)

- L2 regression on raw continuous target, full-data train, fixed 2,000 trees,
  no early stopping (protocol symmetry with the production control).
- Features: production stack + volume_alpha + adavol (77 total).
- Inference-time neutralization vs 22 ranked starters at λ=0.5: keeps ~71% of
  raw CORR while halving starter overlap; λ=1.0 keeps only ~38%.
- Pre-deploy differentiation check: rank correlation vs production model
  0.67; top-decile overlap 12/30 (random expectation 3/30).
- Old pipeline kept untouched for one-line rollback.
- Promotion gate: final-day CORR ≥ 0.12 and MMC > 0 over 4+ resolved rounds.
