# Validating Pipeline Assumptions Against Real Data

## When to Use This

You wrote code based on documentation (API docs, datasheets, example notebooks) and now have access to real data. Documentation is always stale or incomplete — treat it as a hypothesis, not ground truth.

Run this validation whenever:
- You download a real dataset for the first time after implementing from docs
- An example notebook uses different paths, column names, or API calls than your implementation
- Something silently works but produces unexpected output

## Step-by-Step Validation

### 1. Inspect Real Data First, Before Fixing Anything

```python
# Download the actual dataset
df = download_training_data()  # or whatever your download function is

# Print everything — shape, columns, dtypes, sample values
print(f'Shape: {df.shape}')
print(f'Columns: {list(df.columns)}')
print(f'Index: {df.index.name}')
print(df.head(3))
print(df.dtypes)
```

**Do NOT skip this.** Your mental model of the data is wrong in ways you can't anticipate.

### 2. Catalog Differences

Compare what you assumed against reality. Common mismatches:

| Assumption | Reality | Impact |
|---|---|---|
| API class `CryptoAPI` | Actually `NumerAPI` | Auth module broken |
| File `train_targets.parquet` | Actually `train.parquet` | Download fails |
| Column `feature_rsi_20d` | Actually `feature_relative_strength_index_20d` | Feature selection broken |
| Target `target` | Actually `target_binned_return_20` | Training fails |
| Index is `ucid` | Actually `symbol` | Join logic wrong |
| Ranking `rank(pct=True)` | Uses `tie_kept_rank()` | Submission format wrong |
| Output `parquet` | Actually `csv` | Upload format wrong |

### 3. Systematically Fix ALL Affected Modules

One mismatch = at least 3 fixes:
1. **Source code** — the implementation itself
2. **Tests** — tests that assert the wrong column name, path, or behavior
3. **Downstream consumers** — anything that depends on the output of the broken module

Trace the dependency chain:
```
Data download → column names → feature selection → model training → prediction → submission format
```

A column name change breaks every module downstream. Fix in order, re-running tests after each.

### 4. Update Tests to Use Real Data Fixtures (Selectively)

- Synthetic data is fine for unit tests (fast, deterministic)
- Add ONE integration test that loads a small slice of real data and runs the pipeline
- Pin the real data test to a specific date/symbol so it's reproducible
- Fake API keys in CI — skip the integration test if env vars aren't set

### 5. Common Pitfalls

- **Assuming docs are complete.** The `list_datasets()` call may not return all available paths. Some datasets exist but aren't listed.
- **Assuming example notebooks are current.** Example notebooks match the API version when they were written. API may have evolved.
- **Assuming the index/column you see in a DataFrame head() is the full truth.** Always check `nunique()`, `dtypes`, and `min()/max()` before committing to logic.
- **One-column fix in one place, forgetting the other.** Searching `grep -rn "old_column_name" src/` after changing a column name catches what you missed.
- **Assuming test data mirrors production.** Synthetic test data won't have the edge cases (NaN, extreme values, empty groups) that real data has.

## When You Find a Mismatch

1. Fix the source code first (the implementation that reads/writes the data)
2. Run tests — they should FAIL (proving the test catches the mismatch)
3. Fix the tests to match reality
4. Commit both fixes together so a later `git bisect` sees them as one unit
5. Update the plan document's "Confirmed Specs" section with the real values
