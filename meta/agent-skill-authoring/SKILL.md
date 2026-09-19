---
name: agent-skill-authoring
description: Author and maintain SKILL.md files for AI agents. Use when writing, editing, or debugging SKILL.md files, or when a skill fails to load in a specific agent.
---

# Agent Skill Authoring

Write SKILL.md files that work across agents — Claude Code, Codex, OpenCode, Kilo Code,
OpenClaw, Hermes, and others.

## Minimum viable SKILL.md

```yaml
---
name: my-skill
description: What this skill does. When to use it — include trigger phrases.
---
```

`name` must match the parent directory name. Lowercase, hyphens only.

## Cross-agent YAML compatibility

**Pitfall: double quotes in `>` folded descriptions break strict parsers.**

Some agents (Kilo Code, OpenCode) use `js-yaml`, a strict YAML parser.
Claude Code uses a lenient regex-based parser. A description that works in
Claude Code can silently fail in Kilo Code.

The problematic pattern:

```yaml
# BROKEN on strict parsers — js-yaml chokes on "..." inside > scalars
description: >
  Use when the user says "ponytail help", "what commands", or "how do I".
```

The fix: remove all double quotes from description text. Trigger phrases
work identically without quotes:

```yaml
# Works everywhere
description: >
  Use when the user says ponytail help, what commands, or how do I.
```

If you must include characters that confuse YAML (`: `, `#`, `"`), wrap the
entire description in single quotes:

```yaml
description: 'Quick workflow: commit + push. Triggers: commit, push, submit.'
```

### Other agents known to use strict YAML parsers

- **Kilo Code** — `js-yaml`; crashes on `"..."` inside `>` scalars
- **OpenCode** — `js-yaml`; same issue, documented in
  [opencode#8331](https://github.com/anomalyco/opencode/issues/8331)
- **Claude Code** — lenient regex parser; tolerant of quotes
- **Codex CLI** — tolerant
- **Hermes Agent** — tolerant

### Quick check

Run this against a SKILL.md to test with Python's YAML parser (also strict):

```bash
python3 -c "import yaml; yaml.safe_load(open('path/SKILL.md').read().split('---',2)[1]); print('OK')"
```

If this passes, the file works with strict parsers.

## Auditing a skill repo (bulk frontmatter rewrites)

When "fixing" a SKILL.md inside a git repo that publishes skills to many
agents (e.g. `skills/` plus generated per-platform copies), start from
`git status` + `git diff`, not from a hand rewrite:

1. **Classify each modified file**: a description-only frontmatter rewrite
   (mechanical) vs a legitimate content edit. Diff with `git diff -- <file>`;
   if only the `description:` block changed, it's mechanical.
2. For description-only regressions, restore the canonical version — do not
   re-type it: `git checkout HEAD -- skills/<name>/SKILL.md`. Touch only that
   file; siblings may be independently edited.
3. **Keep legitimate additive edits — especially generated copies**
   (`.openclaw/skills/`, `.agents/`, etc.) whose bodies already mirror a
   canonical skill. Reverting them makes them stale and fails the repo's
   freshness test.
4. Verify: `git diff --stat` empty for the restored files, YAML still parses,
   then run the repo test suite (`node --test tests/*.test.js`); a
   *freshness* test asserts generated copies match canonical bodies verbatim.

**Pitfall: bulk frontmatter flattening strips meaning.** A tool collapsing a
`description: >` folded scalar onto one line also drops trigger quote-markers,
inline-code backticks (`` `ponytail:` ``), and semantic quotes ("later means
never") from the value — silently changing what triggers the skill and what it
promises. Diff against HEAD to catch it; never re-type the description from
memory, the length and phrasing are canonical.

## Bundled skills (read-only)

Skills shipped with Hermes (source=`builtin`) are read-only — you cannot patch them, and `skill_manage(action='create')` with the same name will fail or match the existing bundled skill. If a bundled skill needs updating, recommend `hermes curator adopt <name>` in a foreground session, or file a PR to the Hermes repo.

## Hermes skill ownership model

When you create a skill via `skill_manage(action='create')`, the result is **user-owned** — subsequent writes (patch, write_file, remove_file) are blocked by the curator with "the skill is not curator-managed".

To make the skill autonomously maintainable, run immediately after creation:

```bash
hermes curator adopt <skill-name>
```

This opts the skill into curator management so future sessions can patch it, add support files, and update references without manual intervention.

**Same rule applies to support files** — `write_file` under a user-owned skill's `references/`, `templates/`, or `scripts/` directory is also blocked until the skill is adopted.

## References

- `references/yaml-quote-pitfall.md` — detailed reproduction and agent matrix
