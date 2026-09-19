# VolSurface / Skewbik — Deployment & Debugging

**volsurface** / **skewbik** — crypto implied-vol surface engine (C++17 core + Python bindings).

## Architecture

- **Backend**: `volsurface.serve.app` (FastAPI + uvicorn) on port 9090
- **Frontend**: `smirk/` (Next.js 14 static export) served on port 3001
- **Database**: TimescaleDB (PostgreSQL) in Docker — `rankit-timescaledb-1`
- **Data pipeline**: `volsurface.ingest.runner` — raw quotes → 5-min snapshots → `computed_iv`

## Deployment Paths

### Backend env var
```
VOLSURFACE_DB_DSN=host=localhost port=5432 dbname=<db> user=<user> password=<pw>
```
Default fallback (if unset): `host=localhost port=5432 dbname=volsurface user=volsurface password=volsurface`

### Frontend env var (`.env.local`)
```
NEXT_PUBLIC_API_URL=http://localhost:9090
NEXT_PUBLIC_WS_URL=ws://localhost:9090/ws/live
```

## Common Pitfalls

### DB connection failure → all API endpoints 500

If `/health` returns `{"status":"ok"}` but `/snapshots` returns 500, the DB is misconfigured:
1. Check Docker container for actual user/db: `docker inspect <container> | python3 -c "import sys,json; d=json.load(sys.stdin); [print(v) for v in d[0]['Config']['Env'] if 'PASS' in v or 'USER' in v or 'DB' in v]"`
2. Test direct connection: `.venv/bin/python3 -c "import psycopg2; psycopg2.connect(<dsn>)"`
3. If the DB user/db doesn't exist, create it or fix `VOLSURFACE_DB_DSN`

### Frontend blank / "Loading snapshots…" forever

Symptoms: UI renders but shows "No surface loaded" and "Loading snapshots…".
Root cause: backend `/snapshots` returns 500 → fetch fails silently → `console.error` only.
Fix: resolve backend DB issue first, then the frontend will populate.

### WebSocket connection vs data flow

The WS to `/ws/live` connects successfully (HTTP 101) even when the backend DB is broken. The "● LIVE" indicator reflects WS transport layer only, not data availability. Check `/snapshots` HTTP endpoint to confirm data flow.

### Static export gotchas (Next.js `output: 'export'`)

- No SSR/ISR — all data loading is client-side `fetch()` in `useEffect`
- Runtime config changes (API URL in localStorage) work via `getApiBase()` in `endpoints.ts`
- `next build` must succeed before `python3 -m http.server --directory out/`
- Verify chunk files exist in `out/_next/static/chunks/` — missing chunks cause blank renders
- **Browser session stale → `about:blank`**: If the browser shows a completely white page with no React content and `document.body.innerHTML` is empty, the browser tab is on a stale session (often `about:blank` after context compaction). Navigate directly to `http://localhost:3001/` to refresh.

### FastAPI lifespan swallows DB init errors (silent 500s)

In `app.py` the lifespan function wraps `db.init_pool()` in `contextlib.suppress(Exception)`. When the DB connection fails (wrong credentials), the exception is swallowed, the pool never gets initialized, and every subsequent query crashes with the confusing "DB pool not initialised" error.

**Fix:** Remove the `suppress(Exception)` wrapper. The real error surfaces on startup instead of being hidden.

### TimescaleDB init.sql piping via `docker exec -i` can fail silently

When running the `init.sql` schema against a Docker container, piping via `docker exec -i <container> psql ...` may silently succeed (return code 0) but fail to actually write tables. The SQL content may not be piped correctly depending on terminal encoding.

**Fix:** Use `docker exec` with the `-f` flag via a host temp file, or use `bash -c 'docker exec -i ... psql ...'` with the SQL content in a heredoc. Always verify tables exist after loading: `docker exec <container> psql -U <user> -d <db> -c "SELECT tablename FROM pg_tables WHERE schemaname='public'"`.

### Calibration is a no-op when C++ bridge is absent

The `/calibrate` endpoint runs `_run_calibration()` which:
1. Loads raw quotes from DB via `db.get_surface_slices()`
2. Falls back to Python SVI (`_fit_slices_svi(grouped, force=True)`) when the C++ `calib_bridge` is unavailable
3. Caches the result and broadcasts over WS

**The problem:** `get_surface_slices()` already does the same raw DB query + SVI fit that the initial `/surface/{snapshot_id}` call does. Since both use the same `mid_iv` data from the DB, the calibration **produces identical params** — it's a no-op.

**When calibration actually changes things:**
1. **C++ bridge available** (`libvs_core_shared.so` present + `LIBVS_CORE_PATH` set): band_mode (NONE/SOFT/HARD) takes effect and produces different SVI params
2. **Strikes excluded** (right-click a quote in the Smile panel): the SVI refits to a subset of quotes, producing different params
3. **Model type changed** (RAW → NATURAL/JW/ESSVI): different SVI parameterization

**Frontend WS push only updates `slices`, not `vol_grid`/`model_type`:** The `useSurface` hook's WS live-pusher (line 45-50 of `useSurface.ts`) calls `setSurface({ ...cur, slices: latestLiveSlices })` — it does NOT update `vol_grid`, `model_type`, or other surface fields. The calibration WS broadcast includes `vol_grid` and `model_type` in the message, but the frontend handler only stores `slices` via `setLatestLiveSlices`. The proper way the calibrated surface reaches the UI is via the `page.tsx` WS handler which calls `refetch()` — a full GET `/surface/{snapshot_id}` — but only when `awaitingCalibSnapshotRef.current === m.snapshot_id`.

### Frontend snapshot fetch has no user-visible error state

In `page.tsx` line 44-52, the snapshot load uses raw `fetch()` with `.catch(console.error)` — no user-visible error state. When the API returns 500, the user sees "Loading snapshots…" forever with no indication that the backend is broken.
