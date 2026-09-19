# TimescaleDB pg16 Compatibility — `name` vs `table_name` in `_timescaledb_catalog.hypertable`

## Problem

TimescaleDB on PostgreSQL 16 renamed the column `name` to `table_name` in the internal catalog table `_timescaledb_catalog.hypertable`. Any test or query that uses the old column name:

```sql
SELECT 1 FROM _timescaledb_catalog.hypertable WHERE name = 'quotes';
```

will fail with `column "name" does not exist`.

## Fix: Generated Column

Add a generated `name` column that aliases `table_name`:

```sql
ALTER TABLE _timescaledb_catalog.hypertable
    ADD COLUMN IF NOT EXISTS name text GENERATED ALWAYS AS (table_name) STORED;
```

## Critical: Order of Operations

The ALTER TABLE **must** happen AFTER all `create_hypertable()` calls, not before.

**Wrong order** (causes errors on subsequent `create_hypertable` calls):
```sql
-- Step 1: Add compat column
ALTER TABLE _timescaledb_catalog.hypertable ADD COLUMN ...;

-- Step 2: Create hypertables — DIMENSION UNIQUE constraint violation!
SELECT create_hypertable('quotes', 'timestamp');
SELECT create_hypertable('instruments', 'timestamp');  -- FAILS
```

**Correct order**:
```sql
-- Step 1: Create all hypertables first
CREATE TABLE quotes (...);
SELECT create_hypertable('quotes', 'timestamp');

CREATE TABLE instruments (...);
SELECT create_hypertable('instruments', 'timestamp');

-- Step 2: Add compat column AFTER all hypertables exist
ALTER TABLE _timescaledb_catalog.hypertable
    ADD COLUMN IF NOT EXISTS name text GENERATED ALWAYS AS (table_name) STORED;
```

## Why This Works

`GENERATED ALWAYS AS (table_name) STORED` creates a physical column that stays in sync with `table_name` automatically. It's stored (not virtual), so it survives restarts and behaves like a real column for querying, indexing, and foreign keys.

The `IF NOT EXISTS` guard makes the migration idempotent — safe to re-run on a DB that already has the column.

## Approach That Does NOT Work

**Renaming the catalog table and replacing with a view:**

```sql
-- ❌ DO NOT DO THIS
ALTER TABLE _timescaledb_catalog.hypertable RENAME TO hypertable_real;
CREATE VIEW _timescaledb_catalog.hypertable AS ...;
```

This causes `pg_class` catalog queries (e.g., `\dt`, `information_schema.tables`, `pg_class` scans) to crash with SIGSEGV because internal TimescaleDB catalog references get confused. Queries that work fine initially will start segfaulting on unrelated operations.

## Testing the Fix

After applying the migration, verify the compat column works without breaking the DB:

```sql
-- Should return 1 row per hypertable
SELECT 1 FROM _timescaledb_catalog.hypertable WHERE name = 'quotes';
SELECT 1 FROM _timescaledb_catalog.hypertable WHERE name = 'instruments';
SELECT 1 FROM _timescaledb_catalog.hypertable WHERE name = 'forwards';

-- Standard operations should still work
\dt                                  -- no segfault
SELECT * FROM information_schema.tables WHERE table_schema = 'public';  -- no segfault
```
