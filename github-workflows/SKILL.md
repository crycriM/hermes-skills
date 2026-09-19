---
name: github-workflows
description: "Comprehensive GitHub/Git operations: auth, repo management, PR lifecycle, code review, issues, codebase inspection, and history scrubbing."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [GitHub, Git, PR, Issues, Code-Review, Authentication, Repository, Codebase, History]
    related_skills: [github-auth, github-pr-workflow, github-code-review, github-issues, github-repo-management, codebase-inspection, git-history-scrub]
---

# GitHub Workflows

Comprehensive guide to GitHub/Git operations: authentication, repository management, PR lifecycle, code review, issues, and history scrubbing.

## 1. Authentication & Setup

Configure GitHub access via HTTPS tokens, SSH keys, and `gh` CLI login.

- Generate personal access tokens (classic or fine-grained)
- Configure SSH keys for GitHub
- `gh auth login` for CLI authentication
- Token storage and rotation

See: `references/github-auth.md`

## 2. Repository Management

Clone, create, fork repos; manage remotes, releases, and configuration.

- `git clone`, `gh repo create`, `gh repo fork`
- Remote management (add, rename, remove)
- Release creation and management
- Repository configuration and secrets

See: `references/github-repo-management.md`

## 3. PR Lifecycle

Branch, commit, open, CI, merge — the full PR workflow.

- Branch creation and naming conventions
- Commit message conventions
- Opening PRs via `gh pr create`
- CI status checks and required approvals
- Merging strategies (squash, rebase, merge commit)
- PR closing and cleanup

See: `references/github-pr-workflow.md`

## 4. Code Review

Review PRs: diffs, inline comments via `gh` or REST API.

- Reading diffs efficiently
- Inline and summary comments
- Review request workflows
- Requesting and providing feedback

See: `references/github-code-review.md`

## 5. Issues & Project Management

Create, triage, label, assign GitHub issues.

- Issue creation with templates
- Label management and triage
- Assigning and prioritizing
- Linking issues to PRs and commits

See: `references/github-issues.md`

## 6. Codebase Inspection

Inspect and clean up large codebases: LOC stats with pygount, deduplication audits, monolith splitting via git line-range extraction, safe refactoring patterns, and stale artifact detection.

See: `references/codebase-inspection.md`

## 7. Git History Scrubbing

Rewrite git history to remove secrets, large files, and sensitive data before public publishing.

- `git-filter-repo` usage
- Secret detection and removal
- Large file cleanup
- Force push considerations

See: `references/git-history-scrub.md`
