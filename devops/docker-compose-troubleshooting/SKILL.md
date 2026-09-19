---
name: docker-compose-troubleshooting
description: General Docker Compose troubleshooting patterns — port conflicts, init.sql permissions, DB readiness, uv + VIRTUAL_ENV interference.
category: devops
---

# Docker Compose Troubleshooting

General patterns for debugging Docker Compose services, especially TimescaleDB/Postgres containers.

---

## Port Already Allocated

**Symptom:** `Bind for 0.0.0.0:PORT failed: port is already allocated`

**Diagnosis:**
```bash
ss -tlnp | grep PORT
docker ps --filter "publish=PORT" --format '{{.Names}}'
docker compose -f docker-compose.yml ps -a
```

**Fix:** Stop the conflicting container, then restart:
```bash
docker stop CONFLICTING_CONTAINER_NAME
docker compose up -d SERVICE
```

---

## init.sql Permission Denied

**Symptom:** Docker logs show `psql: error: /docker-entrypoint-initdb.d/init.sql: Permission denied`

**Cause:** The Docker entrypoint runs as the `postgres` user (non-root). Files mounted from the host inherit host permissions which may not be readable by the container's postgres user.

**Fix:**
```bash
chmod 644 docker/sql/init.sql
docker compose down -v && docker compose up
```

---

## Container Exits Immediately After Start

**Symptom:** `docker ps -a` shows container as `Exited (1)`.

**Diagnosis:**
```bash
docker logs CONTAINER_NAME | tail -30
```

Common causes: init.sql errors, missing extensions, port conflicts.

---

## DB Not Ready When Tests Run

**Symptom:** Tests fail with connection refused or "database does not exist".

**Fix:** Wait for health check before proceeding:
```bash
sleep 15
docker compose exec timescaledb pg_isready -U volsurface -d volsurface
```

Or use the healthcheck:
```bash
docker compose up --wait timescaledb
```

---

## TimescaleDB-Specific

### Extension Not Installed

**Symptom:** `relation "_timescaledb_catalog.hypertable" does not exist`

**Cause:** `CREATE EXTENSION IF NOT EXISTS timescaledb;` hasn't run yet (init.sql may be empty or not executed).

**Check:**
```bash
docker compose exec timescaledb psql -U volsurface -d volsurface -c "SELECT extname FROM pg_extension WHERE extname='timescaledb'"
```

**Fix:** Run in init.sql or manually:
```bash
docker compose exec timescaledb psql -U volsurface -d volsurface -c "CREATE EXTENSION IF NOT EXISTS timescaledb;"
```

### Role Does Not Exist

**Symptom:** `psql: error: FATAL: role "volsurface" does not exist`

**Cause:** `POSTGRES_USER` env var doesn't match the role created during initialization.

**Check:**
```bash
docker inspect CONTAINER --format '{{json .Config.Env}}' | python3 -c "import sys,json; print('\\n'.join(json.loads(sys.stdin.read())))"
```

### `_timescaledb_catalog.hypertable` Column Name Compatibility (pg16+)

**Symptom:** Test queries like `SELECT 1 FROM _timescaledb_catalog.hypertable WHERE name = 'quotes'` fail with `column "name" does not exist`, even though the table is a valid hypertable.

**Cause:** TimescaleDB on PostgreSQL 16+ renamed the `name` column in `_timescaledb_catalog.hypertable` to `table_name`. Older test fixtures that query `WHERE name = %s` or `WHERE name = $1` will fail on pg16 images.

**Fix — add a generated column after all `create_hypertable` calls:**

In your init.sql, place this line **after** all `SELECT create_hypertable(...)` statements:

```sql
ALTER TABLE _timescaledb_catalog.hypertable
    ADD COLUMN IF NOT EXISTS name text GENERATED ALWAYS AS (table_name) STORED;
```

**⚠️ Order matters:** adding the generated column before `create_hypertable` causes a `duplicate key value violates unique constraint "dimension_hypertable_id_column_name_key"` error, because the dimension registration mechanism sees duplicate timestamp columns across tables.

**🚫 Never rename the catalog table.** Attempting `ALTER TABLE _timescaledb_catalog.hypertable RENAME TO hypertable_real` followed by a shadow view causes SIGSEGV on any `pg_class`-related query (e.g., `\dt`, `information_schema.tables`, `information_schema.columns`) because the view breaks TimescaleDB's internal catalog lookups. The crash pattern in logs:

```
server process (PID X) was terminated by signal 11: Segmentation fault
DETAIL: Failed process was running: SELECT n.nspname as "Schema", c.relname as "Name" ...
LOG:  terminating any other active server processes
LOG:  database system was interrupted; last known up at ...
LOG:  database system was not properly shut down; automatic recovery in progress
```

**Verification:**
```bash
docker compose exec timescaledb psql -U volsurface -d volsurface \
  -c "SELECT 1 FROM _timescaledb_catalog.hypertable WHERE name = 'quotes'"
```

---

## uv + Docker Environment Gotchas

### `uv run` Ignores Project `.venv`

**Symptom:** `uv run pytest` fails with `ModuleNotFoundError` even though package is installed in project `.venv`.

**Cause:** `uv run` respects the `VIRTUAL_ENV` environment variable. If it points to a different venv (e.g., from another session), it ignores the project's `.venv`.

**Fix:** Use the project venv directly:
```bash
.venv/bin/python -m pytest tests/ -v
```

Or unset the variable:
```bash
unset VIRTUAL_ENV && uv run pytest tests/ -v
```

### Installing Packages into Project venv

```bash
uv pip install PACKAGE --python .venv/bin/python
```

---

## Test Design: Pre-Check Dependencies Before Testing Constraints

When testing a constraint (e.g., "UPDATE fails because of trigger"), always verify the prerequisite (table exists) first. Otherwise the test passes for the wrong reason.

**Bad:**
```python
def test_update_fails(cursor, table):
    success, error = try_update(cursor, table)
    assert not success  # Could fail because table doesn't exist!
```

**Good:**
```python
def test_update_fails(cursor, table):
    assert table_exists(cursor, table), f"Table '{table}' must exist first"
    success, error = try_update(cursor, table)
    assert not success, f"Expected UPDATE on '{table}' to fail (immutability)"
```

---

## Test Design: Check Extension Existence Before Querying Extension Catalogs

TimescaleDB catalog tables (`_timescaledb_catalog.*`) only exist after `CREATE EXTENSION timescaledb`. Tests that query them should check `pg_extension` first to avoid `UndefinedTable` exceptions masking the real assertion.

**Bad:**
```python
def hypertable_exists(cur, table_name):
    cur.execute("SELECT 1 FROM _timescaledb_catalog.hypertable WHERE name = %s", (table_name,))
    return cur.fetchone() is not None  # Raises UndefinedTable if extension not loaded
```

**Good:**
```python
def hypertable_exists(cur, table_name):
    cur.execute("SELECT 1 FROM pg_extension WHERE extname = 'timescaledb'")
    if not cur.fetchone():
        return False  # Extension not loaded yet — not a hypertable
    cur.execute("SELECT 1 FROM _timescaledb_catalog.hypertable WHERE name = %s", (table_name,))
    return cur.fetchone() is not None
```
