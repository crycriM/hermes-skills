# Claude Code Settings (`~/.claude/settings.json`)

Location: `~/.claude/settings.json`

Standard fields:
- `"model"` — single string, e.g. `"opus"` or `"sonnet"`. Claude Code accepts only one active model. No multi-model or per-model overrides syntax exists in the spec.
- `"attribution"` — optional block with `"commit"` and `"pr"` fields (both empty strings). Used by Anthropic's attribution system to track which commits/PRs Claude Code produced. Example:
  ```json
  "attribution": {
    "commit": "",
    "pr": ""
  }
  ```

## Per-project settings

Claude Code also reads `<project-root>/.claude/settings.json` which merges with / overrides the global one. Common pattern: global file sets the model, project file sets project-specific attribution or model overrides.

## `CLAUDE.md` vs `settings.json`

- `CLAUDE.md` (at project root or `.claude/CLAUDE.md`): user-written instructions about the project the agent should follow. This is context/behaviour, not JSON config.
- `settings.json`: JSON config for Claude Code itself (model choice, attribution, etc.).
