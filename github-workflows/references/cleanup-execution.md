# Cleanup Execution: Splitting Monoliths & Safe Refactoring

Patterns discovered during large-scale codebase cleanup (~329 files, ~115K LOC Python monorepo).

## 1. Git-Based Monolith Splitting (Preferred)

When splitting a monolithic file into focused modules, **do not use subagents**. They can get interrupted mid-operation and produce incomplete splits with missing methods.

Instead, use direct git line-range extraction:

```bash
# Find class boundaries
git show HEAD:path/to/file.py | grep -n '^class '

# Extract each class by line range
git show HEAD:path/to/file.py | sed -n '50,112p' > new_module.py

# Verify line counts
git show HEAD:path/to/file.py | sed -n '50,112p' | wc -l
```

**Benefits**: Atomic, verifiable (wc -l confirms completeness), no context window limits.

### Creating Split Files

```bash
# 1. Write module header (imports, docstring) with cat heredoc
cat > new_module.py << 'EOF'
"""Module docstring."""

from other_module import Dependency

EOF

# 2. Append class body from git
git show HEAD:orig_file.py | sed -n 'START,ENDp' >> new_module.py

# 3. Verify compilation
python3 -m py_compile new_module.py
```

### Compatibility Shim Pattern

Keep the original file as a thin compatibility shim to avoid breaking ALL downstream importers:

```python
# MOVED: Split into focused modules.
# This shim preserves backward compatibility.
from package.new_module_a import ClassA
from package.new_module_b import ClassB
from package.new_module_c import ClassC
__all__ = ['ClassA', 'ClassB', 'ClassC']
```

Then update importers to point to the new files one by one.

## 2. When NOT to Split

### ValiConfig / Central Config (200+ import sites)
Do NOT split files that have 200+ import sites. Updating every file is error-prone and creates massive diff noise. Leave these as-is.

### Domain Exception Classes
Do NOT consolidate exception classes that are caught by name in `except` blocks:
```python
except SignalException as e:   # ← must stay named
except BracketOrderException:  # ← must stay named
```
Consolidation would break all catch blocks silently.

### Tightly-Coupled Classes (45+ methods with self-references)
Files where methods call each other extensively via `self` are too tightly coupled for safe extraction. Instead, add section markers:
```python
# ============================================================================
# VALIDATION METHODS
# ============================================================================
```

## 3. Method Verification After Split

After a subagent or automated split, ALWAYS verify:

```bash
# List ALL methods in original manager class
git show HEAD:file.py | sed -n 'CLASS_START,CLASS_ENDp' | grep -n "    def " | wc -l

# Compare with split file
grep -c "    def " new_file.py

# If counts differ, something was lost. Also check individual method names:
diff <(git show HEAD:file.py | sed -n 'CS,CEp' | grep "    def " | sort) \
     <(grep "    def " new_file.py | sort)
```

## 4. P0 Quick Wins (always do first)

Before attempting complex splits, clean the low-hanging fruit:
- Delete `if __name__ == "__main__":` debug blocks from library/server files
- Remove `if False:` dead code branches
- Delete commented-out imports
- Remove one-off debugging scripts (`*_to_snap.py`)

These are zero-risk and reduce file sizes immediately.

## 5. Section Markers for Monoliths That Can't Be Split

For files too tightly coupled for extraction, insert clear section dividers:

```python
# ============================================================================
# CORE PROCESSING
# ============================================================================

# ============================================================================
# VALIDATION METHODS
# ============================================================================

# ============================================================================
# FILL ENGINE
# ============================================================================

# ============================================================================
# DISK IO & SYNC
# ============================================================================
```

This makes navigation and future maintenance easier without changing any logic.

## 6. Execute_Code vs Subagents

| Task | Tool | Why |
|------|------|-----|
| Read & analyze file structure | `execute_code` | No context-window truncation issues |
| Split by line range | `terminal` (git show + sed) | Deterministic, verifiable |
| Complex refactoring with imports | `delegate_task` | Subagents can search/replace across files |
| Section marker insertion | `patch` | Simple targeted edits |

**Pitfall**: `execute_code` has a 50KB stdout cap — reading large files directly will truncate. Use `terminal` with piped commands for large file extraction.
