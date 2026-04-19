---
name: codebase-skeleton
description: Extract compressed codebase skeletons — file tree + function/class signatures, type hints, decorators, and truncated docstrings. Feeds small-context LLMs with codebase awareness in ~1 token per 10 LOC.
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [codebase, skeleton, signatures, AST, context-compression, small-context]
    related_skills: [codebase-inspection]
prerequisites:
  commands: [python3]
---

# Codebase Skeleton Extractor

Compress a source code repository into a compact text representation showing **only** structural elements — no function bodies. Designed to give small-context LLMs (minimax2.7, etc.) full codebase awareness without blowing the context window.

## When to Use

- Giving a small-context model (minimax2.7, etc.) awareness of a codebase
- Preparing context for code review, refactoring, or feature planning
- Generating a "map" of a codebase for onboarding
- Any task where you need the structure but not the implementation

## Quick Start

```bash
# Full skeleton with stats
python3 ~/.hermes/skills/software-development/codebase-skeleton/scripts/codebase-skeleton.py /path/to/repo --ext py --stats

# Tree only (just the file listing)
python3 ~/.hermes/skills/software-development/codebase-skeleton/scripts/codebase-skeleton.py /path/to/repo --tree-only

# Save to file for later injection into LLM context
python3 ~/.hermes/skills/software-development/codebase-skeleton/scripts/codebase-skeleton.py /path/to/repo --ext py -o /tmp/skeleton.txt --stats
```

## Options

| Flag | Description |
|------|-------------|
| `--ext py` | Filter to specific extensions (can repeat: `--ext py js ts`) |
| `--skip "*test*,vendor"` | Additional glob patterns to skip |
| `--no-imports` | Omit import statements (saves tokens) |
| `--max-lines N` | Truncate output to N lines |
| `--tree-only` | File tree only, no signatures |
| `--format json` | Structured JSON output |
| `--format text` | Human-readable (default) |
| `--format tree` | Same as `--tree-only` |
| `--stats` | Append file/line/token statistics |
| `-o FILE` | Write to file instead of stdout |

## What It Extracts

**Python (via `ast` stdlib):**
- File tree with `tree`-style formatting
- All `import` / `from ... import` statements
- Module-level constants (UPPER_CASE assignments, annotated assignments)
- Class definitions with base classes and keyword arguments
- Class attributes (annotated assignments at class level)
- Method and function signatures with full type hints and default values
- Decorators
- Truncated docstrings (first 3 lines, max 200 chars)

**Other languages:** Not yet supported. Falls back to listing the file path with `[unsupported]` marker. Tree-only mode works for all files regardless.

## Typical Compression

- A 10K LOC Python codebase compresses to ~2-4K tokens
- Roughly 10:1 LOC-to-token ratio
- With `--no-imports`: up to 20:1 for import-heavy codebases

## Workflow for Small-Context Models

1. Generate skeleton: `python3 codebase-skeleton.py /repo --ext py --no-imports --stats -o /tmp/skeleton.txt`
2. Check token count from stats line
3. If too large: use `--max-lines` or `--skip` to reduce
4. Inject skeleton into system prompt or first user message
5. Model can then ask follow-up questions about specific files

## Pitfalls

1. **Syntax errors in source files** — the script handles them gracefully (marks as `[parse error]`) but the file is skipped
2. **Private methods filtered** — methods starting with `_` (except dunders like `__init__`, `__call__`) are excluded to save space. If you need them, patch the script
3. **Constants only shows UPPER_CASE** — regular assignments at module level are skipped to avoid noise
4. **No cross-file type resolution** — type hints are kept as raw strings (`Optional[str]`, not resolved to imports). The model needs `--no-imports` only if imports are truly redundant
5. **Non-Python files** — currently parsed as unsupported. Use `--tree-only` to at least show the file tree for mixed-language repos
