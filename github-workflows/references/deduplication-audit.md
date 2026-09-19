# Deduplication Audit Pattern

Systematic audit for repeated code, stubs, and stale artifacts. Use after `pygount --format=summary` for a LOC baseline. grep-heavy, no LLM calls needed.

## 1. Find Repeated Constants

```bash
# Count files defining the same constant
grep -rl "STARTER_FEATURES" --include="*.py" | sort

# Check if definitions are identical (first N lines of the block)
grep -A10 "^CONSTANT_NAME" scripts/*.py | head -60
```

## 2. Find Duplicated Functions

```bash
# Count how many times a function is defined (not imported)
grep -c "def function_name" scripts/*.py

# Compare implementations — look for subtle differences
grep -A15 "def function_name" scripts/file_a.py scripts/file_b.py
```

Common differences to spot:
- Parameter name changes (e.g., `cols` vs `feature_cols`)
- Extra guards (e.g., `if c in result.columns`)
- Different default values (e.g., `row.get(col)` vs `row.get(col, "{}")`)
- Different `pl.String` vs `pl.Utf8` usage

## 3. Find Dead Stubs

```bash
# Files containing TODO/stub but no real code
grep -rl "TODO:\|stub" --include="*.py" src/

# Verify no imports from stubs — if zero results, safe to delete
grep -rn "from src.package.stub_module\|import src.package.stub_module" src/ scripts/
```

## 4. Find Unused Packages

```bash
# Empty __init__.py directories with no consumers
grep -rn "from src.package\|import src.package" src/ scripts/ 
# If zero results and only __init__.py exists in the dir, it's dead scaffolding
```

## 5. Find Stale Defaults

```bash
# Compare DEFAULT constants with what production scripts actually use
grep -A8 "DEFAULT_PARAMS" src/models/baseline.py
grep -A10 "LAMBDA_PARAMS" scripts/train_lambdarank.py
# Flag mismatches in lr, max_depth, num_leaves, min_data_in_leaf
```

## 6. Find Misleading References

```bash
# Check README/CLAUDE.md for file paths that don't exist
grep "\.py" README.md CLAUDE.md | while read line; do
    path=$(echo "$line" | grep -oP 'src/\S+\.py')
    [ -n "$path" ] && [ ! -f "$path" ] && echo "MISSING: $path"
done
```

## 7. Find Broken Docker/CMD References

```bash
grep "CMD\|ENTRYPOINT" Dockerfile
# Verify the referenced module/script exists
```

## 8. Find Inconsistent Type Usage

```bash
# Polars: pl.String vs pl.Utf8
grep -rn "pl\.String\|pl\.Utf8" src/ scripts/ --include="*.py"
```

## 9. Cross-Sectional Import Check

```bash
# Verify no src module imports from scripts (should be zero)
grep -rn "from scripts\|import scripts" src/ --include="*.py"

# Verify no circular imports (count src imports per src file)
for f in src/**/*.py; do echo "$f: $(grep -c '^from src\.' $f)"; done
```

## 9. Cross-Sectional Import Check

```bash
# Verify no src module imports from scripts (should be zero)
grep -rn "from scripts\|import scripts" src/ --include="*.py"

# Verify no circular imports (count src imports per src file)
for f in src/**/*.py; do echo "$f: $(grep -c '^from src\.' $f)"; done
```

---

## 10. RPC Boilerplate Detection (Python Monorepos)

For codebases using the Client/Server/Manager triplet pattern (shared_objects/rpc/, vali_objects/*/):

```bash
# Find all _client.py, _server.py, _manager.py files
find ptn -name "*_client.py" -o -name "*_server.py" -o -name "*_manager.py" | sort

# Identify trivial clients (pure passthrough wrappers, < 60 lines)
find ptn -name "*_client.py" -exec wc -l {} \; | awk '$1 < 60 {print $2}'

# Identify files inheriting from RPCClientBase/RPCServerBase
grep -rl "RPCClientBase\|RPCServerBase" ptn/ | sort

# Count how many _client.py files just delegate to _server.py
grep -l "return self._server\." ptn/**/*_client.py | wc -l
```

**Red flags for RPC duplication:**
- `*_client.py` < 60 lines, only wraps `_server.method_rpc()` → candidate for inlining
- Multiple `*_manager.py` files with identical constructor pattern (create 5-7 internal clients)
- `if __name__ == "__main__":` blocks in server files (dead entry points — servers are spawned via `Process(target=...)`)

**Fix pattern:** Create a `BaseManager` class in `shared_objects/` that:
- Holds `running_unit_tests` and `connection_mode` properties
- Has a `_create_client(ClientClass, **kwargs)` helper
- Subclasses call `super().__init__(client_list=[...])` instead of repeating the pattern

## 11. Monolithic File Detection

Large Python files that should be split (heuristic: > 1500 lines OR > 30 methods in a single class):

```bash
# Find files > 1500 lines
find ptn -name "*.py" -exec wc -l {} \; | awk '$1 > 1500 {print $2, $1}' | sort -t' ' -k2 -nr

# Find single-class files > 1000 lines
for f in $(find ptn -name "*.py" -exec wc -l {} \; | awk '$1 > 1000 {print $2}'); do
    classes=$(grep -c "^class " "$f")
    if [ "$classes" = "1" ]; then echo "$f"; fi
done

# Count methods in suspiciously large classes (> 40 methods)
grep -c "    def " ptn/vali_objects/vali_dataclasses/ledger/emission/emissions_ledger.py
grep -c "    def " ptn/vali_objects/utils/limit_order/limit_order_manager.py
```

**Common split points for monolithic files:**
- File has 2-3 top-level classes → one file per class
- File has 40+ methods → split by responsibility (e.g., `_validate_*` → validator.py, disk I/O → disk_io.py)
- File mixes data classes + business logic → separate into `dataclasses/` and `managers/`

## 12. One-Off / Debug Scripts in Production Code

```bash
# Find files with empty hardcoded lists (often debug scripts)
grep -rn "positions_to_snap = \[\]" ptn/

# Find files with if __name__ blocks that shouldn't be runnable directly
grep -l "if __name__ == \"__main__\":" ptn/shared_objects/rpc/*.py ptn/vali_objects/**/*.py 2>/dev/null

# Find files with TODO comments about deprecation/shadow mode
grep -rn "TODO.*shadow\|TODO.*deprecated\|TODO.*remove" ptn/ | grep -i "p2p\|sync\|old\|legacy"
```

## 13. Duplicate Enum and Type Definitions

```bash
# Find OrderType or similar enums defined in multiple places
grep -rn "class OrderType\|class ExecutionType\|class PositionStatus" ptn/ signal_bridge/ --include="*.py"

# Check if signal_bridge and ptn define the same enum
grep -l "class OrderType" ptn/vali_objects/enums/*.py signal_bridge/models.py
```

## 14. Test File Overlap Detection

```bash
# Find test files for the same module with similar names (likely overlap)
ls ptn/tests/vali_tests/ | grep -i "perf_ledger\|position\|order" | sort

# Compare test file sizes — if one is 3x the size of another for same module, investigate
wc -l ptn/tests/vali_tests/test_perf_ledger*.py | sort -t' ' -k1 -nr
```

## When to Apply

After any session that creates new scripts, before merging feature branches, or when a new contributor starts working on the repo. Run sections 1-9 in ~2 minutes — the grep patterns are copy-paste ready.

For large Python monorepos (> 100 files, RPC architecture), also run sections 10-14 to catch structural duplication.
