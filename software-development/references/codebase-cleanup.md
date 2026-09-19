# Codebase Cleanup & Multi-File Refactoring

Systematic approach to removing features, data sources, or config across a codebase.

## Workflow: Feature Removal

1. **Search exhaustively** — grep for all references (enum members, params, imports, comments, test fixtures, env vars)
2. **Read key files** — understand the feature's integration points before patching
3. **Patch systematically** — remove from: enum/model → factory/registry → config → eligible lists → CLI scripts → API endpoints → tests → env files
4. **Delete dedicated files** — adapter files, test files, example scripts focused entirely on the removed feature
5. **Verify with grep** — confirm zero stale references remain
6. **Run tests** — distinguish pre-existing failures from new ones
7. **Commit** — atomic commit with clear message listing all changes

## Pitfalls

### Pydantic Settings + .env cleanup
When removing a field from a Pydantic `BaseSettings` class:
- **MUST** also remove from `.env` and `.env.example`
- Pydantic with `extra="forbid"` will reject stale env vars at runtime
- Symptom: `ValidationError: Extra inputs are not permitted` on app startup
- Fix: `sed -i '/FIELD_NAME/d' .env .env.example`

### Stale references in unexpected places
Feature removal often leaves traces in:
- Historical/data fetching modules (adapter name maps)
- Coverage/report modules (fallback lists)
- Test fixtures (mock data using removed enum)
- Comments/docstrings (mentioning removed feature)
- Integration tests (testing the removed feature's behavior)

### Test failure triage
After refactoring:
- Run targeted test files first (engine, filters) to verify core logic
- Distinguish pre-existing failures (mock data, DB, external services) from new ones
- Pre-existing failures are OK to leave; new failures must be fixed before commit

## Pattern: Data Source Removal

When removing an exchange/adapter from a data pipeline:

| Layer | Files to update |
|-------|----------------|
| Model | `models.py` (enum member) |
| Factory | `adapters/__init__.py` (case statement) |
| Adapter | `adapters/<name>.py` (delete file) |
| Config | `config.py` (base URL setting) |
| Pipeline | `job.py` (eligible exchanges list) |
| Reports | `data_coverage_report.py` (fallback lists) |
| Historical | `historical_fetch.py` (name maps) |
| Tests | Adapter test file (delete), filter tests (update fixtures) |
| Env | `.env`, `.env.example` (remove URL) |

## Example: Removing a Feature Flag

```bash
# 1. Search all references
grep -rn "feature_flag\|FEATURE_FLAG" src/ tests/ --include="*.py"

# 2. Patch source files (use patch tool for each)
# - Remove param from function signatures
# - Remove from dataclass fields
# - Remove CLI arguments
# - Remove API endpoint params
# - Remove from return dicts

# 3. Delete dedicated files
rm src/module/example_feature_run.py
rm tests/test_feature.py

# 4. Clean env files
sed -i '/FEATURE_FLAG/d' .env .env.example

# 5. Verify clean
grep -rn "feature_flag\|FEATURE_FLAG" src/ tests/ --include="*.py"
# Should return nothing

# 6. Run tests
uv run pytest tests/test_engine.py tests/test_filters.py -q

# 7. Commit
git add -A
git commit -m "refactor: remove feature_flag from pipeline"
```
