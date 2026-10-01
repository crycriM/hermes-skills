---
name: hermes-skill-gating
description: Use when gating skills on/off in a Hermes profile.
version: 1.0.0
author: PinceMi
license: MIT
platforms: [linux, macos, windows]
tags: [hermes, skills, profile, configuration, platform]
metadata:
  hermes:
    tags: [hermes, skills, profile, configuration, platform]
    related_skills: [hermes-agent, multi-agent-profile-config]
triggers:
  - "disable a skill"
  - "enable a skill"
  - "skills config"
  - "skills not loading"
  - "per-profile skills"
  - "per-platform skills"
---

# Hermes Skill Gating

Which skills load in a Hermes session is decided by skill frontmatter plus a deny-list stored in the ACTIVE profile's own `config.yaml`. Disabling a skill is a config operation; it is never done by moving, renaming, or deleting a directory.

State is per profile: `~/.hermes/profiles/<name>/config.yaml` for a profile, `~/.hermes/config.yaml` for default. Skills installed on disk are shared conceptually but each profile's deny-list is its own — a profile with 54 builtin skills installed commonly shows 4 enabled.

## When to Use

- The user asks how to enable/disable skills for a profile, for one messaging platform, or "why is skill X still loading".
- A profile should be slimmed down (a chat lane that must not carry 50 builtin skills), or a skill disabled by mistake needs restoring.
- Verify what a given profile will load before trusting its output.

Start at section 1 for the interactive command, section 3 to verify, section 4 for scripted changes.

## 1. Interactive checklist (the normal human path)

```bash
hermes -p <profile> skills config
```

- `-p/--profile` is pre-parsed from argv (before config imports) and sets `HERMES_HOME`, so it works before or after the subcommand. Without it you edit the DEFAULT profile even when the shell's CWD is a profile directory — always pass it explicitly when the target is not default.
- Prompts, in order: scope (`1. All platforms (global default)`, then one entry per messaging platform) → mode (`1. Toggle individual skills`, `2. Toggle by category`) → a curses checklist where `[✓]` means enabled, space toggles, enter saves.
- It requires a real terminal and exits with `requires an interactive terminal` when run through a pipe or a non-interactive subprocess. An agent cannot drive it: hand the user the exact command to run in their own shell instead of trying to automate it or replicating it by hand-editing YAML.
- Essential skills (e.g. `hermes-agent`) are silently dropped before saving — they cannot be disabled from any surface.
- A run whose result equals the current state prints `No changes` and writes nothing.

## 2. Where the state lands

| Scope chosen | Config key written | Effect |
|---|---|---|
| All platforms (global) | `skills.disabled: [name, ...]` | disabled everywhere, all surfaces |
| One messaging platform | `skills.platform_disabled.<platform>: [name, ...]` | unioned on top of the global list |

The agent-side readers are `agent.skill_utils.get_disabled_skill_names()` / `hermes_cli.skills_config.get_disabled_skills()`, both of which subtract the essential-skill set; the same keys drive the CLI listing and the dashboard.

## 3. Verify what will actually load

```bash
hermes -p <profile> skills list --enabled-only
hermes -p <profile> config get skills          # raw deny-lists
```

`--enabled-only` prints exactly the set that profile will load and hides the rest; the flag works before or after the subcommand. `skills list` without it annotates each skill `enabled`/`disabled`, which is the fast way to confirm a single change landed.

## 4. Non-interactive / scripted changes

```bash
hermes -p <profile> config set skills.disabled '["apple-notes","codex"]'
hermes -p <profile> config set skills.platform_disabled.matrix '["xurl"]'
hermes -p <profile> config edit
```

`config set` auto-coerces: a YAML/JSON list literal is parsed into a real list, and a value that looks structured but does not parse is refused with an error rather than stored as a useless string.

## 5. GUI path (for a profile with no TTY handy)

The desktop app / dashboard skills pane toggles the same state through `PUT /api/skills/toggle` with `{"name": ..., "enabled": ..., "profile": ...}` (the profile field lets it target a non-active profile). Useful when the user wants to flip skills in another profile while a gateway is live.

## 6. When changes take effect

Sessions scan skills at start, so a change applies to the next session. A session already running picks it up with `/reload-skills`. No gateway restart is needed.

## Pitfalls

- **`hermes config set skills.disabled foo` with a bare name stores a ONE-item list and silently drops every other entry.** The key is one of the scalar-as-one-item-list slots (`_SCALAR_AS_ONE_ITEM_LIST_KEYS`), so always pass an explicit `["name", ...]` array — or use `hermes skills config`, which rewrites the whole set deliberately.
- **Renaming a skill directory to `<name>.disabled/` does not disable it.** Discovery reads frontmatter and the config deny-list only, so such a skill still loads and merely reports an odd category (e.g. `mlops/.disabled`). To truly remove a skill, move it out of the skills tree.
- **Never hand-edit `config.yaml` under a live gateway.** Use `hermes config set` / `hermes config edit` so the file stays valid YAML; a stray indent breaks the running gateway.
- **Global vs platform confusion.** A skill disabled globally is disabled everywhere and no platform list can re-enable it; check `skills.disabled` first when a per-platform toggle appears to do nothing.
- **Do not answer "can Hermes disable a skill interactively?" from memory.** The bundled `hermes-agent` skill is the authoritative map here — load it and verify against `hermes skills --help` before stating a negative.
