---
name: repo-publication-audit
description: "Systematic audit and cleanup of a repository before making it public — PII/redaction scan, internal-file relocation, README rewriting, .gitignore setup, and post-cleanup verification."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [GitHub, Git, Security, Publishing, Cleanup, PII]
---

# Repository Publication Audit

Systematic process for preparing a private/internal repo for public publishing. Covers PII/redaction scanning, internal-file migration, README rewriting, `.gitignore` creation, and post-cleanup verification.

## 1. Inventory & Scan

1. **Map the tree** — `find . -not -path './.git/*' | sort`
2. **Search for PII and secrets** — grep for personal names, profile URLs, API keys, tokens, passwords, `api_key`, `secret`, `password`, GitHub tokens (`ghp_`, `xoxb-`), AWS keys (`aws_`), etc. across all text files.
3. **Flag findings** — PII (personal LinkedIn, real names), stale/wrong contact info, internal-only references ("Boss", "phase 3"), dev-only files (server.py, .env).

## 2. Redact & Remove

1. **PII removal** — Replace personal URLs/identifiers with placeholders or company-level equivalents. Remove from ALL locations (HTML, JSON-LD, CSS, JS, markdown).
2. **Remove dev-only files** — `server.py`, `icon_gen.py`, build scripts, `.venv/`, `__pycache__/`.
3. **Remove obsolete drafts** — Old content versions, early wireframes, design explorations that don't belong in a public repo.

## 3. Relocate Internal Files

Move all internal-only content to a `private/` directory:
- Draft content, design notes, internal task trackers, implementation docs, SEO checklists.
- Add `private/` to `.gitignore`.

## 4. Rewrite README

Replace internal task-trackers with a public-facing README:
- Project description (what it is, not what you're doing in it)
- File structure overview
- Tech stack notes
- Development instructions (if applicable)
- License/copyright

**Never** include internal todo items, "Boss reviews" references, or "next steps" that assume private context.

## 5. Create .gitignore

Add at minimum:
```
private/
.DS_Store
*.pyc
__pycache__/
.env
```

## 6. Verify

1. **Final tree listing** — Confirm only public-facing files remain at root.
2. **PII re-scan** — `grep -rn 'christian\|marzolin\|ba386b10\|api_key\|secret\|password' . --include='*.html' --include='*.js' --include='*.css' --include='*.md' --include='*.xml' --include='*.svg'` (adjust patterns per project).
3. **Git diff review** — `git diff --stat` to see exactly what changed.

See: `references/pii-scan-patterns.md` — ready-to-use grep patterns for PII and secret scanning.

## 7. Purging a file from an already-published history

The scan above is not only for pre-publication. When something sensitive turns out to be already in a public repo, removing it from the tip is not enough: `git rm --cached` stops future commits only — every old commit keeps the blob, and the remote keeps serving it. Do the full purge, in this order.

1. **Snapshot the repo and any live file first.** `tar czf repo-pre-purge-$(date +%F-%H%M).tar.gz -C <parent> <repo>` (keep `.git/` — it is the only copy of the history you are about to rewrite). This matters because `git filter-repo --force` resets the working tree to the rewritten HEAD: any *uncommitted* modification to a tracked file is silently replaced by the old committed version, and a rewrite that drops a path can take the working copy with it. Back up untracked-but-important files too.
2. **Untrack + gitignore, commit, then rewrite** — `git rm --cached <paths>` (files stay on disk), add the paths to `.gitignore`, commit, then `git filter-repo --path <p1> --path <p2> --invert-paths --force`. Bundle every sensitive path into ONE rewrite: each rewrite invalidates every clone, so a second pass is a second forced push for no gain.
3. **Re-add the remote and force-push** — filter-repo deliberately deletes `origin`. `git remote add origin <url> && git push --force origin main && git branch --set-upstream-to=origin/main main`.
4. **Verify from a fresh mirror clone of the remote**, never from the local repo: `git clone --mirror <url> /tmp/mirror` then `git log --all --oneline -- <paths>` (expect empty) and `git rev-list --objects --all | grep -E '<paths>'` (expect nothing).
5. **State the residual honestly.** GitHub keeps unreachable objects and still answers `git fetch origin <old-sha>` and `git cat-file -p <blob-sha>` for them, so the file can remain retrievable by anyone holding a SHA. Only deleting and recreating the repository — or a GitHub Support GC request — guarantees removal; switching the repo to private cuts public access immediately. Say which one you did and which is still outstanding.
6. **Bound the real exposure window** instead of assuming "public since forever": `GET /repos/<owner>/<repo>/events` shows the PushEvents (first real push date) and the repo object shows `forks_count` / `watchers_count`.

See: `references/history-purge.md` — command sequence, verification, and the residual-exposure decision table.

## Pitfalls

- **`git rm --cached` is not a purge, and a delete commit is not a trace removal.** Removing a file from a public repo requires the filter-repo rewrite plus a force push; the delete commit alone leaves every earlier commit intact, which the post-cleanup verification above will expose.
- **Scan `git ls-files`, not the working tree.** The tree holds untracked files that are not published; the tracked list is what is exposed. It is how a TLS `key.pem` sitting in `reverse-proxy/certs/` gets found — a private key warrants regeneration, not just removal from history, because it was readable for however long the repo was public.
- **Stale email domains** — Draft content versions often reference old/wrong email addresses (e.g., `@example.com` vs `@example.net`). Check every content version file.
- **JSON-LD structured data** — `sameAs` arrays in schema.org JSON-LD often contain personal social profiles. This is in the HTML `<head>` and easy to miss.
- **Hardcoded profile URLs in multiple locations** — A personal LinkedIn URL typically appears in: JSON-LD `sameAs`, About section links, and Footer. All three must be replaced.
- **`.claude/` or `.cursorrules/` metadata** — These tool-specific dirs may contain worktree metadata. Either delete or gitignore them.
- **Mockups/design explorations** — Often contain placeholder PII or internal notes. Decide: keep as public design reference or move to `private/`.
