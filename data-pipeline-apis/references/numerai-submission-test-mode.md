# Numerai Submission Test Mode & Prediction Comparison

## Test Mode Pattern (Run Without Uploading)

When testing model changes, you need to run the full prediction pipeline without actually uploading to Numerai. This avoids wasting submissions and lets you compare predictions safely.

### Pattern: Monkey-Patch Upload/Save in Module Namespace

**Problem:** The submission scripts import `upload_submission` and `save_submission` directly:
```python
from src.numerai.submit import build_submission, validate_submission, save_submission, upload_submission
```

Patching `src.numerai.submit.upload_submission` won't work because the function is already bound in the script's namespace.

**Solution:** Patch in the script's own module namespace using `sys.modules[__name__]`:

```python
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--test", action="store_true", help="Run without uploading")
    args = parser.parse_args()
    
    if args.test:
        import sys
        self_mod = sys.modules[__name__]
        
        def mock_upload(path, model_name=None):
            print(f"  [TEST MODE] Skipping upload of {path}")
            return "test_submission_id"
        
        def mock_save(sub_df, round_num):
            round_num = int(round_num)
            out_dir = PROJECT_ROOT / "data" / "submissions"
            out_dir.mkdir(parents=True, exist_ok=True)
            out_path = out_dir / f"test_m5_draft_{round_num}.csv"
            sub_df.write_csv(out_path)
            print(f"  [TEST MODE] Saved to: {out_path}")
            return out_path
        
        # Patch in this module's namespace
        self_mod.upload_submission = mock_upload
        self_mod.save_submission = mock_save
        
        main()
    else:
        main()
```

**Key points:**
- Use `sys.modules[__name__]` to get the current module object
- Assign mock functions to the module's attributes
- The `main()` function will use the patched versions
- Save test predictions with `test_` prefix to distinguish from real submissions

**Usage:**
```bash
# Run m5_draft in test mode
uv run python3 scripts/submit_live.py --test

# Run m5_rc in test mode
uv run python3 scripts/submit_s2_live.py --test
```

**Output files:**
- `data/submissions/test_m5_draft_{round}.csv`
- `data/submissions/s2/test_m5_rc_{round}.csv`

## Prediction Comparison Methodology

After running test predictions, compare them against previously submitted predictions to measure model stability and understand the impact of feature changes.

### Spearman Correlation (Rank Stability)

**Purpose:** Measure how much the ranking of predictions changed between rounds.

```python
import polars as pl
from scipy.stats import spearmanr

# Load predictions from two rounds
preds_old = pl.read_csv("data/submissions/submission_1292.csv")
preds_new = pl.read_csv("data/submissions/test_m5_draft_1294.csv")

# Join on symbol
joined = preds_old.join(preds_new, on="symbol", suffix="_new")

# Compute Spearman correlation
corr, pval = spearmanr(joined["prediction"], joined["prediction_new"])
print(f"Spearman correlation: {corr:.4f} (p-value: {pval:.2e})")
```

**Interpretation:**
- **0.90+**: Very stable — model is consistent, changes are minor
- **0.75-0.90**: Moderate stability — some rank shifts but overall similar
- **<0.75**: Significant change — feature engineering had major impact

### Rank Difference Analysis

**Purpose:** Identify which symbols moved the most and in which direction.

```python
# Compute ranks (cast to Int64 to avoid overflow in subtraction)
joined = joined.with_columns([
    pl.col("prediction").rank("ordinal").cast(pl.Int64).alias("rank_old"),
    pl.col("prediction_new").rank("ordinal").cast(pl.Int64).alias("rank_new"),
])

# Compute rank difference (positive = moved down, negative = moved up)
joined = joined.with_columns([
    (pl.col("rank_new") - pl.col("rank_old")).alias("rank_diff"),
])

# Summary stats
print(f"Mean absolute rank change: {joined['rank_diff'].abs().mean():.1f}")
print(f"Max rank change: {joined['rank_diff'].abs().max():.0f}")

# Top movers (biggest rank increases = moved down in ranking)
print("\nTop 5 biggest rank drops:")
top_movers = joined.sort("rank_diff", descending=True).head(5)
for row in top_movers.iter_rows(named=True):
    print(f"  {row['symbol']:10s}: rank {row['rank_old']:.0f} → {row['rank_new']:.0f} (Δ={row['rank_diff']:+.0f})")

# Top climbers (biggest rank decreases = moved up in ranking)
print("\nTop 5 biggest rank climbs:")
bottom_movers = joined.sort("rank_diff", descending=False).head(5)
for row in bottom_movers.iter_rows(named=True):
    print(f"  {row['symbol']:10s}: rank {row['rank_old']:.0f} → {row['rank_new']:.0f} (Δ={row['rank_diff']:+.0f})")
```

**Interpretation:**
- **Mean rank change < 25**: Stable model, minor fluctuations
- **Mean rank change 25-50**: Moderate shifts, worth investigating
- **Mean rank change > 50**: Major changes, likely due to new features or data

### Cross-Model Comparison

**Purpose:** Measure how different two models are (for ensemble diversity).

```python
# Compare m5_draft vs m5_rc for the same round
draft_preds = pl.read_csv("data/submissions/test_m5_draft_1294.csv")
rc_preds = pl.read_csv("data/submissions/s2/test_m5_rc_1294.csv")

cross = draft_preds.join(rc_preds, on="symbol", suffix="_rc")
corr, pval = spearmanr(cross["prediction"], cross["prediction_rc"])
print(f"m5_draft vs m5_rc correlation: {corr:.4f}")
```

**Interpretation:**
- **0.70-0.85**: Good diversity — models are related but make different predictions
- **>0.90**: Too similar — models are redundant, ensemble won't help much
- **<0.70**: Very different — may indicate one model is unstable or broken

### Typical Results (Numerai Crypto)

Based on round-to-round comparisons (2026-06):

| Model | Spearman ρ | Mean Rank Δ | Max Rank Δ | Interpretation |
|-------|-----------|-------------|------------|----------------|
| m5_draft (1292→1294) | 0.9186 | 22.5 | 169 | Very stable |
| m5_rc (1292→1294) | 0.9247 | 22.0 | 186 | Very stable |
| m5_draft vs m5_rc (1294) | 0.7672 | — | — | Good diversity |

**Key observations:**
- Both models are highly stable (~0.92 correlation) across rounds
- m5_rc is slightly more stable than m5_draft
- Cross-model correlation (0.77) shows good ensemble diversity
- Biggest movers (100+ rank changes) are typically due to:
  - New OI/volume data affecting feature values
  - Different market conditions between rounds
  - Model sensitivity to recent data

### When to Investigate Further

**Red flags:**
- Spearman correlation < 0.75 between rounds (model is unstable)
- Mean rank change > 50 (major shifts in predictions)
- Cross-model correlation > 0.90 (models are redundant)

**Actions:**
1. Check if new features were added or data sources changed
2. Verify training data hasn't been corrupted
3. Compare feature distributions between rounds
4. Check if specific symbols have missing data
