# Git Archaeology — Recovering Source Files from History

When you inspect a repository and find source files missing from the working tree, **do not conclude they never existed**. Check git history first — the files may have been moved, deleted, or consolidated in a past commit.

## When to Use

- You search for `*.py` files and find fewer than expected
- The working tree has mostly `__pycache__`, `node_modules`, or empty `__init__.py` placeholders
- A previous session's context summary references files that don't exist
- The project README or CLAUDE.md mentions modules/features with no corresponding source

## The Workflow

### 1. Check the full commit history

```bash
git log --oneline --all | head -30
```

Look for commits whose messages mention the project, feature, or "move"/"cleanup"/"refactor".

### 2. Filter for relevant commits

```bash
git log --oneline --all | grep -i "rankit\|scaffold\|move\|cleanup"
```

### 3. See what files a commit touched

```bash
# Show files changed in a specific commit
git show <commit_hash> --stat

# Show only source files (skip pycache, venv, etc.)
git show <commit_hash> --stat | grep -E "\.(py|ts|js|rs|go|md)$" | head -20
```

### 4. Check what existed in a particular commit's tree

```bash
# List all files tracked in a given commit
git ls-tree -r <commit_hash> --name-only

# Filter by directory
git ls-tree -r <commit_hash> --name-only | grep "src/"
```

### 5. See the diff between two versions

```bash
# What changed between the commit before deletion and current HEAD
git diff <good_commit>..HEAD --stat

# Focus on a specific directory
git diff <good_commit>..HEAD --stat -- src/
```

### 6. Check what a single commit actually did

```bash
# The parent (^) is the state before, the commit is the state after
git diff <commit_hash>^..<commit_hash> --stat | head -30
```

Good for understanding "moved rankit" or "cleanup" commits.

### 7. Restore deleted files

```bash
# Restore an entire tree from a known-good commit
git checkout <good_commit> -- path/to/restore/
```

This stages the files. After verifying, you can:
```bash
git reset HEAD .  # unstage if you just wanted to inspect
# or
git commit -m "restore: ..."  # keep the restoration
```

### 8. Verify the restore

```bash
# Count source files
find path/to/restore/src/ -name "*.py" | wc -l

# Quick syntax check
python3 -m py_compile path/to/restore/src/main.py 2>&1 || true
```

## Key Git Commands Reference

| Goal | Command |
|------|---------|
| See all commits | `git log --oneline --all` |
| Show files in a commit | `git show <hash> --stat` |
| List files in a tree | `git ls-tree -r <hash> --name-only` |
| Diff two commits | `git diff <a>..<b> --stat` |
| Diff a commit vs parent | `git diff <hash>^..<hash> --stat` |
| Restore files from history | `git checkout <hash> -- <path>` |
| See staged changes | `git diff --cached --stat` |
| Find commits by message | `git log --oneline --all --grep="keyword"` |
| Find commits affecting file | `git log --oneline --all -- <path>` |

## Pitfalls

1. **Don't restore pycache** — when doing `git checkout <commit> -- dir/`, you'll also restore `__pycache__` and `.egg-info` if they were committed. Either:
   - Restore specific subdirectories (`git checkout <hash> -- src/ tests/`)
   - Or clean up after: `find . -name "__pycache__" -exec rm -rf {} + 2>/dev/null; find . -name "*.egg-info" -exec rm -rf {} +`

2. **Check git root first** — `git rev-parse --show-toplevel` tells you the repo root. If you're inside a subdirectory, all paths are relative to the repo root, not your current directory.

3. **Restored files appear as staged modifications** — after `git checkout <hash> -- <path>`, the files are staged by checkout. Use `git reset HEAD -- <path>` to unstage if you only wanted to inspect.

4. **"pathspec did not match"** — means the path didn't exist in that commit. Check `git ls-tree -r <hash> --name-only | grep <keyword>` to find the actual path.