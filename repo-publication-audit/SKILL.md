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

## Pitfalls

- **Stale email domains** — Draft content versions often reference old/wrong email addresses (e.g., `@example.com` vs `@example.net`). Check every content version file.
- **JSON-LD structured data** — `sameAs` arrays in schema.org JSON-LD often contain personal social profiles. This is in the HTML `<head>` and easy to miss.
- **Hardcoded profile URLs in multiple locations** — A personal LinkedIn URL typically appears in: JSON-LD `sameAs`, About section links, and Footer. All three must be replaced.
- **`.claude/` or `.cursorrules/` metadata** — These tool-specific dirs may contain worktree metadata. Either delete or gitignore them.
- **Mockups/design explorations** — Often contain placeholder PII or internal notes. Decide: keep as public design reference or move to `private/`.
