# YAML Quote Pitfall in SKILL.md Descriptions

Reproduced July 2026. Source: ponytail skill package (Kilo Code user report).

## The bug

A SKILL.md that loads fine in Claude Code fails with a parsing error in Kilo Code.
The root cause: Kilo Code uses `js-yaml` (strict), while Claude Code uses a lenient
regex-based frontmatter extractor.

## Reproduction

This frontmatter causes `js-yaml` to fail:

```yaml
---
name: example
description: >
  Use when the user says "hello", "world", or "test".
---
```

The `"..."` sequences inside the `>` folded block scalar confuse `js-yaml`,
which interprets the double quotes as YAML string delimiters within the scalar.

**Error output** (Kilo Code / OpenCode):
```
Failed to parse YAML frontmatter: incomplete explicit mapping pair;
a key node is missed; or followed by a non-tabulated empty line
```

## Fix

Remove all double quotes from description text:

```yaml
---
name: example
description: >
  Use when the user says hello, world, or test.
---
```

Alternatively, wrap the entire description in single quotes:

```yaml
description: 'Use when the user says "hello", "world", or "test".'
```

## Cross-agent YAML parser matrix

| Agent | Parser | Double quotes in `>` scalars |
|-------|--------|------------------------------|
| Claude Code | Lenient regex | OK |
| Codex CLI | Tolerant | OK |
| Hermes Agent | Tolerant | OK |
| OpenClaw | Tolerant | OK |
| Kilo Code | `js-yaml` (strict) | **FAILS** |
| OpenCode | `js-yaml` (strict) | **FAILS** |

## Verification

```bash
# Python's PyYAML is also strict — good pre-flight check
python3 -c "
import yaml
with open('path/to/SKILL.md') as f:
    parts = f.read().split('---', 2)
yaml.safe_load(parts[1])
print('OK')
"
```

If PyYAML parses it, `js-yaml` will too.

## Related issues

- [OpenCode #8331](https://github.com/anomalyco/opencode/issues/8331) — same root cause
- [OpenCode #6858](https://github.com/anomalyco/opencode/issues/6858) — `: ` pattern in descriptions
- Reddit r/ClaudeAI: "SKILL.MD Issue" (Nov 2025) — quote marks in descriptions break imports
