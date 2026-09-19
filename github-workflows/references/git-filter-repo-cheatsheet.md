# git-filter-repo Cheatsheet

All invocations assume `cd $REPO` first and a confirmed backup at
`/tmp/$REPO.backup.<date>.git`.

## Path-based removal (the common case)

```bash
# Remove specific files
git filter-repo --invert-paths --path path/to/file --path another/file --force

# Remove by glob
git filter-repo --invert-paths --path-glob '*.sqlite3' --force
git filter-repo --invert-paths --path-glob 'secrets/*' --force
git filter-repo --invert-paths --path-glob '*.gguf' --force

# Remove an entire directory subtree
git filter-repo --invert-paths --path-glob 'chroma_db/*' --force
```

## Blob-based removal (when you know the SHA but not the path)

```bash
git filter-repo --invert-paths --blob <blob-sha> --force
```

Use `git rev-list --all --objects | grep <filename>` to find blob SHAs.

## Replace text across all files

```bash
# Replace in all blobs (useful for redaction before going public)
git filter-repo --replace-text /path/to/expressions.txt --force
# expressions.txt format: one regex per line, literal: prefix to disable regex
```

## Replace author/committer names and emails (mass identity scrub)

```bash
# Use a callback script for complex mappings
git filter-repo --mailmap /path/to/mailmap --force

# Or inline
git filter-repo --replace-message '<regex>' '<replacement>' --force
```

## Extract a subdirectory into its own repo (split a monorepo)

```bash
git filter-repo --subdirectory-filter path/to/extract --force
```

The new repo's first commit will be the earliest commit that touched
that subdirectory.

## Preserve or rewrite refs

```bash
# Keep all branches and tags
git filter-repo --invert-paths --path foo --force    # default: keeps all refs

# Operate only on a specific branch
git filter-repo --invert-paths --path foo --branch main --force
```

## Verify after running

```bash
# These should be empty for paths you removed
git log --all --full-history --pretty=format: --name-only --diff-filter=A \
  | grep <path>
git log --all --full-history -- <path>

# Blob lookup should be empty
git cat-file -t <blob-sha> 2>&1   # should error "Not a valid object"

# Repo still works
git status
git log --oneline -5
```

## Force-push safely

```bash
# ALWAYS prefer this
git push --force-with-lease origin <branch>

# Only if you're 100% sure no one else is pushing
git push --force origin <branch>
```

`--force-with-lease` is a "compare-and-swap" — if remote advanced past
your local view, it refuses. That's the safety net.

## Common flags

| Flag | Purpose |
|---|---|
| `--invert-paths` | Remove matching paths (default keeps them) |
| `--path <p>` | Match exact path |
| `--path-glob <g>` | Match glob pattern |
| `--blob <sha>` | Match by blob SHA |
| `--force` | Skip safety prompts (use after manual backup) |
| `--preserve-commit-encoding` | Don't touch commit messages |
| `--preserve-commit-authors` | Don't rewrite author info |
| `--replace-text <file>` | Regex replacements in blob contents |
| `--mailmap <file>` | Remap author identities |
| `--subdirectory-filter <dir>` | Extract subdir as new repo |
| `--branch <name>` | Operate only on named branch |

## Recovery if filter-repo goes wrong

```bash
# If you have a backup bare clone:
git clone /tmp/$REPO.backup.<date>.git $REPO.recover
cd $REPO.recover
git remote set-url origin <upstream-url>
git push --force origin main    # restore old history
```

The backup is the safety net. Without it, filter-repo is one-way.

## Combine with tag rewriting

Filter-repo by default rewrites all branches but not annotated tags
that aren't reachable. If you have old release tags pointing at the
old history, they may need manual update:

```bash
git tag -d <old-tag>
git tag <new-tag> <new-commit-sha>
git push --force origin <new-tag>
```

## Performance

Filter-repo scales with the size of the object graph, not the size of
the working tree. A 500-commit repo with 50k objects takes a few
seconds. A 50k-commit monorepo with millions of objects can take
several minutes. The progress is shown on stderr — don't interrupt.

## When NOT to use filter-repo

- **You only need to untrack files going forward** → `git rm --cached`
  in a normal commit is enough
- **You want to rewrite a single commit's message** → `git rebase -i`
  is simpler
- **You want to drop a single commit** → `git rebase -i` to drop the
  line, or `git revert` to apply an inverse commit

Filter-repo is for the case where you need to **remove specific content
from every commit that ever contained it**.
