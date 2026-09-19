# Git Whitelist Recovery

When `git add .` accidentally stages all skills (bypassing `.skill-whitelist`),
recover without losing the intended changes.

## Recovery steps

```bash
cd ~/.hermes/skills

# 1. Undo the bad commit, keep changes staged
git reset --soft HEAD~1

# 2. Unstage everything
git reset HEAD

# 3. Re-add only whitelisted paths
while IFS= read -r path; do
  [[ -z "$path" || "$path" == \#* ]] && continue
  git add -f "$path/" 2>/dev/null
done < .skill-whitelist

# 4. Also add whitelist metadata files
git add .skill-whitelist SKILLS_GIT_WHITELIST.md .gitignore

# 5. Remove any __pycache__ / .pytest_cache that slipped through
git rm -r --cached --quiet $(git diff --cached --name-only | grep -E '__pycache__|\.pytest_cache|\.pyc$') 2>/dev/null

# 6. Verify only whitelisted files are staged
git diff --cached --name-only | while read f; do
  matched=0
  while IFS= read -r wl; do
    [[ -z "$wl" || "$wl" == \#* ]] && continue
    [[ "$f" == "$wl"* ]] && matched=1
  done < .skill-whitelist
  [[ $matched -eq 0 ]] && echo "WARNING: non-whitelisted: $f"
done

# 7. Commit
git commit -m "your message"
```

## Why `git add -f`

The `.skill-whitelist` is a manual enforcement mechanism, not a `.gitignore`.
Files are added with `-f` because many skill files (`.pyc`, configs) match
global gitignore patterns. The whitelist IS the filter.

## Pitfalls

- **`git add -f` bypasses `.gitignore`** — always follow with a `__pycache__`
  sweep or those files end up in the repo.
- **Deleted whitelisted skills** — if a whitelisted directory was deleted (moved
  to `.archive/`), `git add -f` will stage the deletion. This is correct.
- **Amend vs. new commit** — if the bad commit was already pushed, use a new
  revert commit instead of amend to avoid force-push issues.
