# DuckDB PIT Store — Known Caveats

Discovered during Numerai Crypto bot development (2026-06). These affect the
`BackfillEngine` / `SchemaManager` pattern in `src/pit_store/`.

## 1. Column Name Mismatch: `derivatives` vs `derived`

The `Features` schema in `schema.py` defines a `derived JSON` column (singular).
But `DerivativesProvider._process_derivatives()` originally emitted a DataFrame
column named `derivatives` (plural). The `insert_features` fallback logic fills
missing schema columns with NULL:

```python
for col in ("market", "onchain", "social", "derived"):
    if col not in df.columns:
        df = df.with_columns(pl.lit(None).cast(pl.Utf8).alias(col))
```

Since `"derivatives" != "derived"`, this fills `derived` with NULLs. The data
is silently lost — no error, no warning, just NULLs in the DB.

**Fix pattern** in `insert_features()`:

```python
if "derivatives" in df.columns and "derived" not in df.columns:
    df = df.rename({"derivatives": "derived"})
elif "derivatives" in df.columns and "derived" in df.columns:
    df = df.drop("derivatives")
```

## 2. Object-Typed Date Columns Crash `cast(pl.Date)`

When a DataFrame is built from a list of dicts containing `pl.date(YYYY, M, D)`,
the resulting column has dtype `Object` (Polars wraps the Python `datetime.date`
object without inferring Date). Calling `.cast(pl.Date)` on an Object column
fails:

```
polars.exceptions.ComputeError: cannot cast 'Object' type
```

The same happens with `.cast(pl.String)` → `str.to_date()` — Polars can't
cast Object to String either.

**Fix pattern** — extract raw values and rebuild the column with explicit dtype:

```python
if dtype not in (pl.Date,):
    raw_dates = df["date"].to_list()
    df = df.with_columns(
        pl.Series("date", raw_dates, dtype=pl.Date)
    )
```

This works because `pl.Series(values, dtype=pl.Date)` handles Python
`datetime.date` objects natively.

**Prevention:** When creating DataFrames programmatically, always pass dates
via `pl.Series` with explicit `dtype=pl.Date` rather than relying on
auto-inference from `pl.date()` expressions.

## 3. JSON Column Export Requires `::VARCHAR` Cast

When reading from a DuckDB `features` table that has JSON-typed columns
(e.g. `derived JSON`), directly selecting the column and converting to
Polars yields a column with all NULLs:

```sql
-- WRONG — returns NULLs in Polars
SELECT symbol, date, derived FROM features WHERE TRIM(source) = 'derivatives'

-- RIGHT — explicit VARCHAR cast preserves the JSON-as-string
SELECT symbol, date, derived::VARCHAR AS derived FROM features WHERE TRIM(source) = 'derivatives'
```

**Why:** DuckDB stores JSON in an internal binary format. When Polars reads it,
the intermediate representation doesn't deserialize correctly unless `::VARCHAR`
explicitly tells DuckDB to serialize as a string first.

## 4. `WHERE source = '...'` Fails with Whitespace

The `source` column in the `features` table can have trailing or leading
whitespace (exact cause unclear — possibly from Pandas→Polars→DuckDB
serialization of the VARCHAR). Direct equality fails:

```sql
-- Returns 0 rows even though data exists
SELECT COUNT(*) FROM features WHERE source = 'derivatives'

-- Returns correct count
SELECT COUNT(*) FROM features WHERE TRIM(source) = 'derivatives'
```

**Always use `TRIM(source)` in WHERE clauses** when querying the `features`
table, especially after a backfill that inserted data via Pandas or Polars.

## 5. Cross-Process Connection Locking

DuckDB uses file-level locking. A writer process (e.g. backfill script) holds
an exclusive lock on the `.duckdb` file. Any attempt to `connect()` from a
different process fails with:

```
IOException: Could not set lock on file features.duckdb:
Conflicting lock is held in python3.11 (PID 12345)
```

**Workarounds:**
- **Parquet as intermediary:** The reader process can use a pre-exported
  `.parquet` snapshot instead of querying DuckDB directly. This is the
  recommended pattern for training scripts that need read-only access while
  the backfill is running.
- **Sequential execution:** Stop the backfill, run training, restart backfill.

DuckDB does support `read_only=True` mode which allows multiple concurrent
readers, but this conflicts with the write lock. Best to use parquet export
as the data interchange format between backfill and training.

## 6. `INSERT OR REPLACE` Deduplication by Primary Key

The `features` table has `PRIMARY KEY (symbol, date, source)`. When
`insert_features` is called with multiple rows sharing the same (symbol, date,
source), only the last row survives. This matters for funding rate data where
Binance returns 3 rows per day (8h intervals) — only the final 8h entry per
day makes it into the DB.

This is usually desirable (one row per symbol per day), but be aware that
higher-frequency data within the same calendar day is silently collapsed.
