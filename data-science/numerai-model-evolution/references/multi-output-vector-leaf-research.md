# Multi-output / vector-leaf research for Numerai Crypto

Research design for a multi-target gradient-boosted model (XGBoost 3.4.1
`multi_strategy="multi_output_tree"`, or any multi-head GBM) for the Numerai
Crypto v2.0 bot. Condensed from a proposal authored by a Codex
`gpt-6-astra` instance on 2026-09-06. The proposal file itself lives at
`~/projects/numerai-folders/numerai-crypto-bot/docs/research-xgboost-vector-leaf-proposal.md`.

## Why this matters here

The winning component in every production Numerai Crypto model is the
**residual (neutralized) signal**, and L2 is the dominant loss:

- m5_draft: `objective="regression"` (L2) on raw quintiles 0-1, no residualization
  in training; neutralization applied at eval (lambda sweep).
- m5_rc: `objective="lambdarank"` on per-date residualized quintiles 0-4 (the
  ranking-loss holdout — keep it as a comparator).
- m5_beta: `objective="regression"` (L2) on continuous global-β OLS residuals
  (`y − X·β`, centered ~0); early-stops on full-pipeline Spearman.

Shared splits across multiple targets only help if the targets are orthogonal
signal. Raw-horizon blending fails because raw targets share the same
starter-correlated structure.

## Head design (the decisive axis)

- **Define heads as L2-RESIDUALIZED views, not raw horizons.** Each head =
  `residualize(target, basis)`, centered + scaled. Shared splits then learn one
  cross-sectional partition serving multiple neutralized targets — the hard
  signal that survives starter neutralization.
- **Winning second basis: within-sector residual**
  `r2 = y − ȳ_sector`, point-in-time sector dummies (L1/L2, DeFi, infra/oracles,
  gaming, exchange tokens, memes, unknown). Pool groups < 30 symbols.
- **Rejected bases:** date-global market return (constant across symbols, adds
  nothing with intercept); symbol-specific betas (overlap technical exposures);
  reranking starters (duplicates head 1); matched-pair groups (too small/noisy);
  liquidity×vol-cell (overlaps starters, already encoded in the 22 features).
- **Different bases ≠ orthogonal residuals.** Shared splits need *compatible
  predictive partitions*, not maximally uncorrelated labels (XGBoost vector-leaf
  docs). Test it; do not assume.

## Leakage rules

- Per-date OLS inside training dates is correct.
- Pooled OLS is valid ONLY if fitted on the fitting subset. Fitting β before CV
  leaks held-out outcomes into training labels (the existing
  `global_residual_target` pattern). Exclude inner early-stopping dates.
- Live inference needs NO target residualization and NO β from outcomes.
- Sector / cluster labels must respect prediction-time availability. The repo
  may not have historical sector classifications — verify before adopting the
  sector basis (go/no-go blocker).
- Drop rows with any missing head; do not impute a target.

## Scaling

Standardize each head only on fitting rows:
`z_h = (r_h − μ_h) / max(s_h, ε)`, equal head weights, drop degenerate heads.
This equalizes target variance, not predictability. Freeze scalers for
validation/live.

## Objective & evaluation

- XGBoost has no supported multi-output ranking objective. Phase one uses plain
  `reg:squarederror` + cross-sectional ranks, relying on the multi-target
  partition as regularization. Keep a scalar `rank:ndcg` (XGBRanker) as an
  optional diagnostic control, not the treatment.
- Score predictions against RAW targets through the unchanged Neutralizer, at
  the lambda ladder [0.0, 0.2, 0.5, 0.7, 1.0], primary = λ=0.5. Report full
  ladder and CORR.
- Keep m5_rc (LambdaRank) as a comparator even though it is the ranking-loss
  holdout.

## Comparison matrix (one row per construction/model/seed/λ)

- LGB-20: exact m5_draft refit on matched rows (production benchmark).
- XGB-20: scalar XGBoost squared-error on raw-20.
- XGB-AUX: scalar XGBoost on the auxiliary residual head.
- XGB-BLEND: 50/50 per-date percentile-rank blend of XGB-20 + XGB-AUX.
- XGB-OPT: one matrix with `multi_strategy="one_output_per_tree"` (heads do not
  share splits — API/data-shape control).
- XGB-VL: same matrix with `multi_strategy="multi_output_tree"` (vector-leaf treatment).

A CORR win requires: mean Δ > 0 at λ=0.5 on pooled dev OOF dates; one-sided
block-bootstrap p-value surviving Holm step-down across every dev configuration
with 95% lower bound > 0; positive Δ on the untouched late holdout; improvement
in ≥2 of 3 seeds; and XGB-VL beating both XGB-20 and XGB-BLEND at the primary
metric (proving a vector-leaf benefit, not just an XGBoost/aux-target benefit).

## Reproducible experiment skeleton

- Capacity-matched shallow params first (mirror m5_draft): n_estimators=2000,
  lr=0.02, max_depth=3, grow_policy=depthwise, min_child_weight=500,
  colsample_bytree=0.10, max_bin=255, tree_method=hist, multi_strategy=
  multi_output_tree, eval_metric=rmse, random_state=42. No early stopping in the
  first matched test (built-in multi-output RMSE averages heads and may stop for
  auxiliary improvement). Repeat only surviving configs with seeds {42, 137, 2026}.
- Data: `data/raw/crypto_v2.0_train.parquet` (510,196 rows, 1,721 dates through
  2026-08-05). `target_binned_return_60` ships but is null on the latest ~40
  dates (ends 2026-06-10) — complete-case rows + purge_window=90 for any 60-day
  head. Do not refresh the path mid-study.
- Dependency: XGBoost 3.4.1 requires Python ≥3.12; the repo targets ≥3.11. Add a
  research-only dep group + 3.12 env, do NOT bump the whole project's
  requires-python floor. `xgboost-cpu==3.4.1; python_version >= '3.12'`.

## Files that should host this work (new, never touch production)

- `scripts/train_s2_xgb_vector_leaf.py` — prep, splits, comparison matrix, metrics,
  bootstrap, report.
- `src/models/xgb_vector_leaf.py` — a NEW `XGBVectorLeaf` wrapper (fit/predict/
  predict_primary/save/load); do NOT subclass `LGBMBaseline` (matrix-valued
  predict contract differs).
- `tests/test_xgb_vector_leaf.py` — shape, serialization, shared-tree config,
  target construction, split leakage, neutralization, seed determinism.
- `data/exports/xgb_vector_leaf/` — research manifests and OOF outputs only.

## Delegation pattern used to research this

Two Codex instances, workspace-write sandbox, prompt piped via stdin:
`codex exec -m <model> --skip-git-repo-check -s workspace-write -C <project> < prompt.txt`.
- Instance 1 (gpt-5.6-sol) produced the full proposal.
- Instance 2 (gpt-6-astra, highest reasoning) answered the residualization-bases
  question. The answer text is in the log after the last `##` heading; extract it
  with a plain `sed -n '/Heading/,/NextHeading/p'` on the log file.
- Write proposals to `docs/`; Codex must not commit or touch `.env` / production
  files.
