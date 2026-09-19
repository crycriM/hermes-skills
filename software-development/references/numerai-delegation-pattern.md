# Numerai Crypto Bot — Multi-Phase Delegation Pattern

## What this is

A proven template for breaking a complex full-stack implementation into 6 delegate_task calls, each handled by a local 35B model in ~500-1400s. Used to build a 6000+ LOC Numerai crypto prediction bot with 197 tests.

## The task sequence

| Phase | Module | Duration | Tests added | Context size |
|-------|--------|----------|-------------|-------------|
| 1 | numerapi auth + submission pipe | 974s | 23 | ~200K tokens |
| 2 | Symbol resolver (ucid mapping) | 502s | 33 | ~845K tokens |
| 3 | PIT store (DuckDB schema) | 267s | 18 | ~522K tokens |
| 4 | CCXT market data backfill | 1367s | 30 | ~1.2M tokens |
| 5 | Purged CV + Spearman/Sharpe | 1342s | 37 | ~1.5M tokens |
| 6 | LGBM baseline + neutralizer | 1282s | 56 | ~1.8M tokens |

## What made it work

### 1. Context structure for each task

Every delegate_task context contained:

- **Project state:** exact files and their contents (read_file output), git log, test count
- **Plan excerpt:** the relevant section from the plan document, verbatim
- **Confirmed specs:** data from the spec addendum (ucid, 30D target, 20D2L scoring, etc.)
- **File-by-file implementation spec:** what each file should contain, function signatures, class names
- **TDD workflow:** "write failing test first → confirm FAIL → implement → confirm PASS → commit"
- **Exact commands:** `pytest tests/test_X.py -v`, `pytest tests/ -q`, `python3 -m scripts.smoke_test`
- **Commit message:** exact string for `git add -A && git commit -m "..."`

### 2. Reliance on the existing test suite

After each phase, running the full suite (`pytest tests/ -q`) caught cross-phase regressions. The smoke test (`scripts/smoke_test.py`) verified the submission pipe was intact. This meant the next subagent started from a known-good state.

### 3. Mock complexity was the bottleneck

Phase 4 (market data) hit max_iterations (50) because the CCXT mock with date-aware `side_effect` was too complex. The subagent spent many iterations debugging the interaction between the `_fetch_ohlcv` while-loop and the mock's date filtering. The fix was to clip candles to the `until` timestamp in the source code itself (defensive coding), which simplified the mock.

**Lesson:** If a delegated TDD task requires complex mocks (date filtering, pagination, rate limiting), either:
- Make the source code defensive (clip/validate at boundaries) so mocks can be simpler
- Or split the mock-heavy test into a separate earlier task

### 4. Sequential, not parallel

All 6 phases ran sequentially. The subagent-driven-development skill's 2-stage review (spec + quality) was skipped in favor of:
- Trusting TDD (tests verify correctness)
- Running the full suite after each phase (regression detection)
- Quick manual review of the diff

For this user, the review overhead wasn't justified — they preferred delivery speed.

## Context template (adapt per phase)

```python
delegate_task(
    goal="Implement [feature name] using strict TDD",
    context=f"""
PROJECT: /path/to/project
EXISTING STATE:
- git log: {git_log}
- test count: {test_count}
- test results: {test_output}

THE PLAN (from docs/plan.md):
```
[relevant plan section]
```

CONFIRMED SPECS:
- [key facts the subagent needs]

IMPLEMENT:
1. src/module/file.py — [class/function spec]
2. tests/test_file.py — [test spec]

TDD STEPS:
1. Write failing test FIRST in tests/test_file.py
2. Run: pytest tests/test_file.py -v (confirm FAIL)
3. Write minimal implementation in src/module/file.py
4. Run: pytest tests/test_file.py -v (confirm PASS)
5. Run: pytest tests/ -q (confirm no regressions)
6. Run: python3 -m scripts.smoke_test (if applicable)
7. Commit: git add -A && git commit -m "feat: add [feature]"
""",
    toolsets=['terminal', 'file']
)
```

## Files created in this pattern

The full file tree from the Numerai implementation — use as a template for similar data+ML pipeline projects:

```
project/
├── pyproject.toml, Dockerfile, .gitignore
├── src/
│   ├── module1/     # API wrappers (auth, download, submit)
│   ├── module2/     # Data structures (resolver, PIT store)
│   ├── module3/     # Data acquisition (market data, on-chain)
│   ├── module4/     # Validation (CV, metrics)
│   └── module5/     # Models (LGBM, neutralizer, registry)
├── tests/
│   ├── test_module1.py  (7-16 tests each)
│   ├── test_module2.py  (12-21 tests each)
│   ├── ...
│   └── test_moduleN.py
├── scripts/
│   └── smoke_test.py    # end-to-end pipeline verification
└── data/
    ├── raw/
    ├── pit_store/
    ├── models/
    └── submissions/
```
