# Second Model: Perp-Inspired Features — Benchmark Results

## Setup
- **Data:** Numerai Crypto v2.0 training, 2020-01-01 to 2026-05-06, 490,696 rows, 1,293 symbols
- **CV:** PurgedCV with 4 valid folds (fold 1 skipped — no data before 2020-01-01), purge_window=25, embargo=5
- **Model:** LGBMRegression (LGBMBaseline, 2000 est, lr=0.02, max_depth=3, num_leaves=15)
- **Evaluation:** Per-date Spearman CORR, neutralized against 22 starters at λ ∈ {0.0, 0.2, 0.5, 0.7, 1.0}
- **Features:** 22 starters (baseline) vs 22 starters + 68 perp features (combined)

## Model Comparison

| Fold 2 (earliest) | Baseline (22 feat) | Combined (97 feat) | Δ (%) |
|--------|-------------------|-------------------|-------|
| raw    | 0.0970            | 0.0754            | −22.3 |
| λ=0.5  | 0.0456            | 0.0423            | −7.2  |
| λ=1.0  | 0.0150            | **0.0246**        | **+64.0** |

| Fold 3 | Baseline | Combined | Δ (%) |
|--------|----------|----------|-------|
| raw    | 0.1370   | 0.1240   | −9.5  |
| λ=0.5  | 0.0916   | 0.0913   | −0.3  |
| λ=1.0  | 0.0536   | **0.0581** | **+8.4** |

| Fold 4 | Baseline | Combined | Δ (%) |
|--------|----------|----------|-------|
| raw    | 0.1430   | **0.1507** | **+5.4** |
| λ=0.5  | 0.0503   | **0.0626** | **+24.5** |
| λ=1.0  | 0.0114   | **0.0208** | **+82.5** |

| Fold 5 (most recent) | Baseline | Combined | Δ (%) |
|----------------------|----------|----------|-------|
| raw    | 0.1433   | **0.1485** | **+3.6** |
| λ=0.5  | 0.0688   | **0.0797** | **+15.8** |
| λ=1.0  | 0.0237   | **0.0311** | **+31.2** |

## Summary (4-fold mean)

| Metric | Baseline | Combined | Δ (points) | Δ (%) |
|--------|----------|----------|-----------|-------|
| raw    | 0.1301   | 0.1247   | −0.0054   | −4.2 |
| λ=0.5  | 0.0641   | 0.0690   | +0.0049   | +7.6 |
| λ=1.0  | 0.0259   | 0.0337   | +0.0078   | +30.1 |

## Feature Importance (Fold 5, top 10)

| Rank | Feature | Importance |
|------|---------|------------|
| 1 | perp_adavol_fvol_feature_sharpe_ratio_60d_s60_ranked | 0.0308 |
| 2 | perp_vol_ewma20_ranked | 0.0274 |
| 3 | feature_volatility_20d_ranked | 0.0261 |
| 4 | perp_adavol_fvol_feature_volatility_60d_s10_ranked | 0.0251 |
| 5 | perp_adavol_fvol_feature_volatility_60d_s60_ranked | 0.0251 |
| 6 | perp_vol_realized10_ranked | 0.0229 |
| 7 | perp_adavol_fvol_feature_volume_avg_60d_s60_ranked | 0.0225 |
| 8 | perp_adavol_fvol_feature_volatility_20d_s10_ranked | 0.0223 |
| 9 | perp_adavol_fvol_feature_sharpe_ratio_60d_s10_ranked | 0.0218 |
| 10 | perp_adavol_fvol_feature_volatility_20d_s60_ranked | 0.0213 |

**Key observations:**
- AdaVol forecast-vol features dominate top-10 (7 of 10)
- Perp vol forecast features (ewma20, realized10) rank 2 and 6
- No funding alpha or copula features in top-20
- Original starter feature (volatility_20d) still ranks #3
- Originality gain (λ=1.0) is strongest on most recent period (+31%)

## Performance
- Total runtime: 77.6s (pyarrow + LGBM on 490K rows × 97 features, 4-fold CV)
- Feature computation: ~17s (copula 13s, AdaVol + others ~4s)
- Training: ~60s for 8 LGBM fits (4 folds × 2 models)

---

## Live Tournament Score History (July 2026)

Official Numerai scores fetched via `scripts/fetch_numerai_scores.py`.
17 overlapping resolved rounds (1284–1300) where both models have corr scores.

### Cross-model corr comparison

| Round | m5_draft | m5_rc | Diff |
|-------|----------|-------|------|
| 1284  | 0.1203   | 0.0821| +0.038 |
| 1285  | 0.1138   | 0.0961| +0.018 |
| 1286  | 0.2159   | 0.1402| +0.076 |
| 1287  | 0.1008   | 0.0927| +0.008 |
| 1288  | 0.0823   | 0.1010| -0.019 |
| 1289  | 0.0976   | 0.0525| +0.045 |
| 1290  | 0.0666   | 0.0299| +0.037 |
| 1291  | 0.1641   | -0.0177| +0.182 |
| 1292  | 0.1126   | 0.0511| +0.062 |
| 1293  | 0.1306   | 0.0542| +0.076 |
| 1294  | 0.1704   | 0.1194| +0.051 |
| 1295  | 0.1076   | 0.0946| +0.013 |
| 1296  | 0.1318   | 0.1130| +0.019 |
| 1297  | 0.1342   | 0.1530| -0.019 |
| 1298  | 0.1052   | 0.0858| +0.019 |
| 1299  | 0.1190   | 0.0960| +0.023 |
| 1300  | 0.0295   | -0.0422| +0.072 |

### Summary statistics

| Metric | m5_draft | m5_rc |
|--------|----------|-------|
| corr mean | 0.1178 | 0.0766 |
| corr percentile mean | 78.1% | 56.5% |
| corr wins | 15/17 | 2/17 |
| mmc mean | 0.0351 | 0.0112 |
| mmc wins | 15/17 | 2/17 |
| season_score mean | 0.0345 | 0.0184 |
| corr_multiplier | 0.05 to 0.10 | 0.05 to 0.10 |
| at_risk | 0.00 (all rounds) | 0.00 (all rounds) |

### Trend analysis

- **m5_draft corr is improving**: first-half mean 0.070 to second-half 0.076,
  last5 mean 0.1230 — strong recent form
- **m5_rc corr is declining**: first-half 0.039 to second-half 0.033, last
  round (1300) was negative (-0.042), percentile dropped to 13%
- **m5_rc best round** was 1297 (corr 0.153, p98.7%) but couldn't sustain it
- The in-sample CV benchmark showed combined features improving lambda=1.0
  by +30%, but live tournament scores show m5_rc underperforming m5_draft on
  raw corr — suggesting the perp features may hurt un-neutralized correlation
  despite improving originality

### Assessment

m5_draft is the clear winner and its trajectory is positive. m5_rc needs work —
its second-half decline and last-round collapse suggest the additional features
may be hurting rather than helping in live tournament conditions. The CV
benchmark advantage at lambda=1.0 (originality) did not translate to better
live corr scores, possibly because the tournament rewards raw corr more than
originality at current corr_multiplier levels.