---
name: numerai-model-evolution
description: "Use when comparing Numerai models; isolate factors."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [Numerai, Crypto, model-comparison, CORR, MMC, purged-CV, feature-ablation]
---

# Numerai Model Evolution

A disciplined workflow for improving a Numerai Crypto model when one production model consistently beats more complex variants. The central rule is to separate protocol effects from feature effects; otherwise a failed experiment teaches almost nothing.

## When to use

Use this skill when:

- A production Numerai model consistently beats experimental models.
- A second model adds features, a different objective, residualization, neutralization, or early stopping.
- CORR and MMC disagree, or a supposed diversity model has negative MMC.
- A model has live submissions but incomplete or asynchronous score history.

## Core workflow

### 1. Freeze the production control

Do not modify the production submission path. Record its exact feature list, target, objective, hyperparameters, missing-value policy, universe mask, rank transformation, and submission semantics. Reproduce this control in the evaluation harness before changing anything.

### 2. Build a matched evaluation harness

Use identical purged walk-forward folds for control and variants:

- same dates and universe rows;
- same feature availability mask and joins;
- same purge and embargo windows;
- same training budget before comparing early stopping;
- same per-date metric implementation;
- persisted fold predictions, not only aggregate scores.

If the harness cannot reproduce the control, stop. Do not interpret variant results yet.

### 3. Separate the experimental axes

Test these as independent factors:

1. raw continuous target versus residual target;
2. L2 regression versus LambdaRank or other ranking objective;
3. fixed tree budget versus purged early stopping;
4. production feature stack versus one added feature family;
5. prediction-only output versus beta-restored output;
6. inference-time neutralization and its lambda value.

Do not introduce several of these changes in one candidate and then attribute the result to its features.

### 3b. Multi-output / multi-target designs (vector-leaf, multi-head GBMs)

When the new architecture is a multi-output tree model (XGBoost `multi_strategy="multi_output_tree"`, or any multi-head GBM), the shared-split benefit only appears if the heads are **orthogonal signal**, not just different-looking targets. The decisive lesson from the Numerai Crypto vector-leaf experiment:

- **Do NOT define heads as raw-horizon blends (e.g. raw-20d + raw-60d).** Raw targets share the same starter-correlated structure, so shared splits learn only the crowd signal and gain nothing vs a scalar model or a rank-blend. The Codex proposal's initial raw-20 + raw-60 framing was the wrong axis.
- **DO define heads as L2-RESIDUALIZED views of the target.** Each head = `residualize(target, basis)`, centered/scaled. Shared splits then learn one cross-sectional partition serving multiple neutralized targets — the hard signal that survives starter neutralization. This is the axis that actually matters in this repo, where the winning component is always the residual (m5_draft = raw L2, m5_rc = LambdaRank residual quintiles, m5_beta = global-β residual L2).
- **Second basis choice:** within-sector residual (`y − ȳ_sector`, point-in-time sector dummies) beat market-factor, liquidity-vol-cell, and matched-pair bases. Rationale: the 22 starters already encode cap/vol/volume, so liquidity-vol bases overlap too much; sector captures economic-narrative exposure beyond linear technical factors. A global market return is constant across symbols (adds nothing with an intercept); symbol betas overlap technical exposures; reranking starters duplicates head 1.
- **Different bases do not imply orthogonal residuals.** Shared splits need *compatible predictive partitions*, not maximally uncorrelated labels (per XGBoost vector-leaf docs). Test it; do not assume.
- **Leakage:** per-date OLS inside training dates is correct; pooled OLS is valid ONLY if fitted on the fitting subset (fitting β before CV leaks held-out outcomes — the existing `global_residual_target` pattern). Live inference needs no residualization and no β from outcomes. Sector/cluster labels must respect prediction-time availability — the repo may not have historical sector classifications, which is a go/no-go blocker.
- **Scaling:** standardize each head only on fitting rows, `z=(r−μ)/max(σ,ε)`, equal head weights, drop degenerate heads. This equalizes variance, not predictability.
- **Objective:** XGBoost has no supported multi-output ranking objective; phase one uses plain `reg:squarederror` + cross-sectional ranks, relying on the multi-target partition as regularization. Keep a scalar `rank:ndcg` (XGBRanker) as a diagnostic control, not the treatment. See the `codex` skill for the two-instance delegation pattern used to research this.

See `references/multi-output-vector-leaf-research.md` for the full head design, comparison matrix, leakage rules, and the gpt-6-astra research answer.

### 4. Treat MMC as a separate objective

A second model should demonstrate incremental residual alpha, not merely be different. Evaluate raw CORR, neutralized CORR at a lambda ladder such as `[0.0, 0.2, 0.5, 0.7, 1.0]`, MMC proxy if available, per-fold stability, and rank stability. A model with negative MMC is not a successful diversity model just because it has low correlation with the production model.

For MMC-oriented candidates, first test ordinary raw-target regression followed by inference-time neutralization against the starter/crowd basis. This is a cleaner control than simultaneously residualizing the training labels, binning them, and changing the objective.

### 5. Add features only through nested ablation

Evaluate feature families one at a time, starting from the frozen production stack. For each family, measure:

- coverage, zero rate, and date availability;
- correlation with existing features after cross-sectional ranking;
- gain stability across folds;
- incremental residual CORR and MMC proxy;
- sign consistency across early and late folds;
- multi-horizon relationship at 1, 3, 7, 20, 30, and 60 days.

A feature that predicts a short squeeze is not automatically useful for a 20-day tournament target. Reject families with stable negative incremental performance or a clear horizon mismatch.

### 6. Account for feature subsampling

When `colsample_bytree` is low, adding many columns can dilute the probability that trees see the strongest variables. Compare a reduced selected stack and a small preregistered `colsample_bytree` grid before concluding that the larger stack is better. Prefer robust improvements across folds over the best single configuration.

### 7. Make beta and neutralization serveable

If residual targets are used, verify train/live alignment of the beta vector, starter column order, intercept convention, and missing-value handling. Compare global, rolling, and exponentially weighted beta only inside purged CV. A per-date target residualization method is not automatically live-serveable because future targets are unavailable at prediction time.

### 8. Promote cautiously

Keep candidates in separate slots. Use test mode and local artifacts for experiments. Fetch official scores when the local cache is incomplete. Score records may have unequal coverage, unresolved days, and approximately month-long resolution. Require several comparable resolved score days plus positive local OOS evidence before promotion.

## Required report

Every model-evolution report should contain:

- architecture matrix for all models;
- paired score counts and coverage caveats;
- fold-level CORR mean/std/Sharpe;
- neutralized CORR lambda ladder;
- MMC or MMC proxy;
- feature-family ablation table;
- horizon ribbon for candidate families;
- prediction rank correlation and rank-change stability;
- explicit promotion, retention, or retirement gate.

## Pitfalls

- **Changing everything at once:** feature, target, objective, early stopping, and output semantics must not all change in one experiment.
- **Equating LambdaRank with Numerai CORR:** LambdaRank optimizes an NDCG-style proxy, not the final leaderboard metric.
- **Binning residuals too early:** quintile binning discards within-bin magnitude and can add noise.
- **Unmatched early stopping:** baseline and variant must use the same purged validation protocol.
- **Calling a model diverse because it is uncorrelated:** diversity with negative MMC is failure, not contribution.
- **Using a short-horizon feature for a long target:** always run the multi-horizon diagnostic first.
- **Trusting an incomplete score cache:** confirm model identity and fetch official scores before drawing conclusions.
- **Defining multi-output heads as raw-horizon blends:** raw targets share starter-correlated structure, so shared splits learn only crowd signal. Use L2-residualized heads instead. See `references/multi-output-vector-leaf-research.md`.
- **Assuming different bases give orthogonal residuals:** shared splits need compatible partitions, not uncorrelated labels. Verify experimentally.
- **Fitting pooled beta before CV:** leaks held-out outcomes into training labels. Fit on the fitting subset only.
- **Adding sector/volatility bases without checking availability:** historical classifications may not exist in the pipeline — a go/no-go blocker before committing to that head.

## Reference

See `references/numerai-model-evolution.md` for the reusable comparison matrix, experiment order, and promotion gates distilled from a three-model Numerai Crypto investigation.
