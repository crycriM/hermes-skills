# Open-Core / Plugin Boundary Refactoring

Splitting a monolithic open-core module into a stable protocol + naive default
(open core) + sophisticated implementation (proprietary plugin).  Drawn from
the skewbik `TimeChange` refactoring (Feb 2027).

## When this applies

A module currently ships one implementation in the open core that does **both**
simple (identity/static) and calibrated/sophisticated work.  The business
model requires the sophisticated work to be a proprietary plugin, while the
open core keeps a usable baseline.

## Steps

### 1. Identify the split boundary

- **Open core keeps:** identity/simple/static implementations that require zero
  external data or calibration.  Registry default stays here.
- **Plugin takes:** calibration routines, OLS fits, event databases, anything
  that needs data ingestion or periodic re-fitting.

**Granularity principle: the open core gets the coarser, market-wide model;
the plugin gets the finer, per-token refinement.**  Don't push hourly
resolution into the open core just because you have it — the open core should
capture the simplest pattern that's useful plugin-free (e.g. day-of-week
rates), and the plugin adds the data-intensive overlay (e.g. intraday Fourier
harmonics).

In the TimeChange case:
- Open core: `IdentityTimeChange` (τ = T, registry default) + `DayOfWeekTimeChange`
  (7 rates, one per day of week, normalised mean=1, fit from daily RV).
- Plugin: intraday Fourier fit projecting 168 hourly coefficients from a
  24h harmonic decomposition, calibrated per-token from hourly RV, plus
  event-variance calendar.

The first attempt put a 168-element hourly schedule in the open core — that
was wrong.  The open core should have the 7-parameter day-level model; the
plugin has the hourly resolution.

### 2. Keep the protocol interface stable

The `Protocol` class in `protocols.py` must NOT change signature during the
split — the plugin implements the same protocol the open core defined.  If the
interface itself needs revisiting, do that in a separate change BEFORE the
split.

**Check for stale duplicates.**  If there's a second copy of the protocol
definition elsewhere in the codebase (e.g. `plugins/__init__.py` had a
different `TimeChange` with `to_total_variance`/`from_total_variance` instead
of `tau(T,t)`), fix it.  Stale copies silently diverge and cause `isinstance`
checks to fail for conforming plugins.

### 3. Restructure the open-core module

- Keep the protocol and identity default in `protocols.py`
- In the market-layer module (`market/time_change.py`), keep:
  - The identity/naive class
  - Add a step-up class (if warranted) with committed reference data
  - Helper functions used by both open-core and plugin
- Remove from the open-core module:
  - Calibration methods other than `fit(daily_rv)` (the 7-param fit is simple
    enough to be open-core — normalisation by mean, no OLS)
  - Event-database logic
  - Any data ingestion code

**What goes in the step-up class.**  The step-up class should use the
**coarsest** model that still captures the open-core value.  For time-change
this was 7 day-of-week rates (not 168 hourly values).  If the step-up class
needs a per-token `fit()`, think hard about whether it belongs in the plugin.

### 4. A reference-data commit is OK in open core

A committed static array (like `DEFAULT_DAY_RATES`: 7 floats — one activity
rate per day of week — encoding the BTC-USD weekday/weekend pattern) is fine.
It's a published convention, not a calibration output.  The plugin calibrates
*against* this reference, not *replaces* it.

**What size of reference data is OK?**  A small, human-interpretable set (7
values) is clearly reference data.  A 168-element array that already contains
the entire hourly pattern blurs the boundary — that's a calibrated model
baked into a static array, which defeats the purpose of the split.

### 5. Update the registry

If the registry shipped the old monolithic implementation as the default,
switch it back to the identity default.  The step-up class (e.g.
`DayOfWeekTimeChange`) should be importable but not the registry default —
plugins register themselves via entry-point discovery.

### 6. Update all documentation

**This is the step that is most often forgotten.**  Every doc that describes
the boundary must be updated:

- `ROADMAP-v2.md` — the issue body for the plugin (e.g. #6)
- `PROJECT-PLAN.md` — architecture diagram, boundary table, phase table, repo layout
- `PLUGINS.md` — the plugin listing
- `planning.md` — working task tracking
- Any inline module docstrings that describe "v1 (plugin): ..."

Each doc update must reflect the new boundary precisely; stale boundary
descriptions cause confusion in later sessions.

### 7. Update tests

- Remove tests for removed functionality (e.g. `fit(flat_rv)` calibration tests)
- Add tests for the new step-up class (structural + seasonal + custom schedule)
- Keep all existing identity/fallback tests unchanged
- Run the full suite (including C++ if the project has a compiled core)

### 8. Watch for name collisions

If the open core and plugin once shared a class name (`HourlyTimeChange` in
both), the plugin should rename its class or use a distinct import path.
Type-checkers and entry-point discovery both assume unique names across the
plugin seam.

## Pitfalls

- **Granularity boundary reversed.**  The most common mistake: putting the
  finer-resolution model in the open core "because it's already implemented."
  The open core should have the coarser, market-wide model; the plugin gets
  the finer, per-token refinement.  If your step-up class has 168 parameters
  and the plugin has 7, the boundary is backwards.
- **Stale protocol duplicates.**  A second `TimeChange` protocol definition in
  `plugins/__init__.py` had diverged from `protocols.py`.  Check every file
  that defines a protocol with the same name.
- **Registry default = identity only.**  Don't set the step-up class as the
  registry default — that undermines the plugin sale.  The step-up class is
  importable by name for power users, but the registry returns the simplest
  fallback.
- **Doc rot.**  The biggest risk after a split is stale documentation that
  still describes the old monolithic architecture.  Update every doc in one
  pass, then verify by grepping for the old class name.
- **Forgotten `planning.md` / working notes.**  These often have stale
  descriptions of the module.  Grep for the old class name project-wide.
- **Plugin dependency on removed code.**  If a plugin calls methods that were
  removed from the open-core module, the plugin must either vendor its own
  copy or import from a different path.  Plugin devs should pin against a
  stable open-core version.

## Plugin language tier

Not all plugins are Python.  Decide the implementation language based on
computational profile:

| Language | When to use | Examples |
|----------|------------|----------|
| Python   | Orchestration, calibration, data ingestion, filtering — logic that calls the C++ core via bindings, runs at the API/serving layer | Information-time calendar (#6), Kalman/UKF parameter filter (#7), ForwardCurve reconciliation (#5), Digital sources (#9) |
| C++      | Compute-bound Monte Carlo, heavy path simulation, per-snapshot re-pricing across strike/expiry grids | Short-end GARCH-FHS engine (#8) — 100k–1M MC paths × strikes × expiries every 5 min |

**The C++ core stays plugin-agnostic.**  A C++ plugin builds as a separate
shared library that links against the open-core C++ ABI.  It registers itself
through the same Python entry-point discovery mechanism — the Python wrapper
imports the C++ plugin's binding module and wraps it behind the same
`typing.Protocol`.  The surface assembly never knows which language it's
calling.

**When a C++ plugin is appropriate:**

- The plugin must run **every snapshot, in the sync path**, and a Python loop
  over compiled leaf functions is too slow.
- The per-snapshot workload is **O(strikes × expiries × paths)** and a naive
  Python layer adds unacceptable overhead.
- The plugin ships its own compiled SIMD loops / Monte Carlo kernel (e.g. FHS
  with 100k+ paths).

**When Python is fine:**

- The plugin runs **off the sync path** (background, async, or on-demand).
- The workload is **calibration/optimisation** that calls the existing C++
  pricer/solver via nanobind — most time is already spent in compiled code.
- The logic is **orchestration** (combining multiple core calls, filtering,
  transforming data).

## Separate repository layout

Each plugin lives in its **own private repository**, never in the open-core
repo (not even gitignored).  Rationale:

- The open-core repo must be publishable as Apache-2.0 with no proprietary
  code in its history.  A gitignored `plugins/` directory still leaves traces
  (config references, import stubs, mentions in docs).
- Plugin devs pin against a **tagged release** of the open core, not against
  `HEAD`.  Breaking changes are surfaced at pin-update time, not at runtime.
- Heavy C++ plugins (FHS) may additionally run **out-of-process** as a service,
  which kills any derivative-work entanglement argument under the Apache
  license.
- The open core's `docs/` and `private/` directories describe the plugin
  boundary (see `PLUGINS.md`, `PROJECT-PLAN.md`, `ROADMAP-v2.md`) so that
  plugin developers know the contract without accessing plugin repos.

**Plugin repo naming convention:**

```
volsurface-plugin-{name}      # e.g. volsurface-plugin-timechange
```

Each plugin repo implements one or more protocols from `volsurface.plugins`
and registers itself via Python entry points in its `pyproject.toml`.  The
open core's plugin registry discovers them by name at startup; if none are
installed, it falls back to the naive/identity defaults.

### 6. Update all documentation

**This is the step that is most often forgotten.**  Every doc that describes
the boundary must be updated:

- `ROADMAP-v2.md` — the issue body for the plugin (e.g. #6)
- `PROJECT-PLAN.md` — architecture diagram, boundary table, phase table, repo layout
- `PLUGINS.md` — the plugin listing
- `planning.md` — working task tracking
- Any inline module docstrings that describe "v1 (plugin): ..."

Each doc update must reflect the new boundary precisely; stale boundary
descriptions cause confusion in later sessions.

### 7. Update tests

- Remove tests for removed functionality (e.g. `fit(flat_rv)` calibration tests)
- Add tests for the new step-up class (structural + seasonal + custom schedule)
- Keep all existing identity/fallback tests unchanged
- Run the full suite (including C++ if the project has a compiled core)

### 8. Watch for name collisions

If the open core and plugin once shared a class name (`HourlyTimeChange` in
both), the plugin should rename its class or use a distinct import path.
Type-checkers and entry-point discovery both assume unique names across the
plugin seam.
