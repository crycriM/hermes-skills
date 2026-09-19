# DuckDB JSON Column Pitfalls

Documented 2026-06-03 during Numerai Crypto feature store development.

## Symptom

```python
conn = duckdb.connect("features.duckdb")
rows = conn.execute("SELECT COUNT(*) FROM features WHERE source = 'derivatives'").fetchone()
# Returns 0 despite SELECT source showing 'derivatives'
```

But `TRIM()` works:
```python
rows = conn.execute("SELECT COUNT(*) FROM features WHERE TRIM(source) = 'derivatives'").fetchone()
# Returns correct count (e.g. 15439)
```

## Root Cause

Invisible **trailing whitespace bytes** in the VARCHAR column. DuckDB uses byte-exact string comparison (`==`), not SQL-style whitespace-agnostic comparison. This can happen when:

1. A prior write used a Python string that happened to have a trailing space/newline
2. The `INSERT OR REPLACE` preserved it
3. The column was written by a different process that serialized the value differently

## Detection

Check ASCII codes of first character:
```python
conn.execute("SELECT source, ascii(source) FROM features LIMIT 5").fetchall()
# 'd' = 100 — correct
```

If the trailing char caused the issue, `ascii(source)` would show the correct first char but string comparison would still fail.

## Fix Options

### Option 1: TRIM in queries (quick fix)
```python
conn.execute("SELECT ... FROM features WHERE TRIM(source) = 'derivatives'")
```

### Option 2: Sanitize on write
Add a trigger or sanitize the Python string before INSERT:
```python
source = source.strip()
```

### Option 3: Re-export with explicit cast
```python
result = conn.execute(
    "SELECT symbol, date, derived::VARCHAR FROM features WHERE TRIM(source) = 'derivatives'"
).fetchall()
```

## JSON Column Export Issue

When exporting DuckDB JSON columns (stored as VARCHAR internally) to Parquet:

```python
# WRONG — creates empty parquet (0 rows)
conn.execute("COPY (SELECT * FROM features) TO 'export.parquet'")
```

**Fix:** Cast JSON columns to VARCHAR explicitly:
```python
# RIGHT
df = conn.execute("SELECT symbol, date, derived::VARCHAR FROM features WHERE TRIM(source) = 'derivatives'").fetchdf()
df.to_parquet("derivatives.parquet")
```

Or read with Polars directly for cleaner handling. The `COPY TO` command in DuckDB v1.0.0+ can produce 0-row parquet files when the source query involves columns that DuckDB considers incompatible with the Parquet format despite them being VARCHAR internally.
