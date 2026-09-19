---
name: ai-coding-agents
description: "Delegate coding tasks to AI coding agents: Claude Code CLI, Codex CLI, and OpenCode CLI. Covers feature implementation, refactoring, PR review, and autonomous sessions."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [Coding-Agent, Claude, Codex, OpenCode, Autonomous, Refactoring, Code-Review, Feature-Implementation]
    related_skills: [claude-code, codex, opencode, hermes-agent]
---

# AI Coding Agents

Delegate coding tasks to AI coding agents: Claude Code CLI, Codex CLI, and OpenCode CLI.

## 1. Claude Code CLI

Delegate coding to Claude Code CLI (features, PRs). Covers PTY mode, automation, code review, and refactoring.

- `claude` CLI invocation
- PTY mode for interactive sessions
- Feature implementation and PR creation
- Code review and refactoring delegation
- Claude Code settings (`~/.claude/settings.json`) — model, attribution block, per-project config

See: `references/claude-code.md`  
See: `references/claude-code-settings.md`

## 2. Codex CLI

Delegate coding to OpenAI's Codex CLI. Similar workflow to Claude Code but with different capabilities and constraints.

- `codex` CLI invocation
- Session management
- Feature implementation and bug fixes

See: `references/codex.md`

## 3. OpenCode CLI

Delegate coding tasks to OpenCode CLI agent for feature implementation, refactoring, PR review, and long-running autonomous sessions.

- `opencode` CLI invocation
- Autonomous session management
- Feature implementation and refactoring
- PR review workflows

See: `references/opencode.md`

## 4. Kilo Code CLI

Delegate coding tasks to Kilo Code CLI (fork of OpenCode). Kilo is an open-source VS Code extension-compatible coding agent. On this system it's installed at `~/.hermes/node/bin/kilo`.

### IMPORTANT: ACP vs `kilo run`

Kilo supports the ACP (Agent Communication Protocol) **over HTTP only** — `kilo acp` starts a server on a port, it does NOT support `--acp --stdio`. Do NOT use `delegate_task` with `acp_command='kilo'` — the Hermes ACP client tries `--acp --stdio` which Kilo rejects.

**The correct delegation pattern is `kilo run` via terminal**, same as OpenCode:

```python
terminal(command="kilo run 'Implement retry logic and add tests'", workdir="~/project")
```

**For complex tasks with multiple deliverables**, write the prompt to a temp file first, then pipe into `kilo run` in background:

```python
write_file("/tmp/kilo_prompt.txt", content="...")
terminal(command="kilo run < /tmp/kilo_prompt.txt", workdir="~/project", background=true, notify_on_complete=true, timeout=600)
```

On this system, GitHub's official `copilot` CLI is also installed at `~/.hermes/node/bin/copilot` (from `@github/copilot`). That binary DOES support `--acp --stdio`. When the user asks for ACP-based delegation, use `acp_command='copilot'` (the GitHub Copilot CLI), not `kilo`.

### One-Shot Tasks (`kilo run`)

Use `kilo run` for bounded, non-interactive tasks:

```
terminal(command="kilo run 'Add retry logic to API calls and update tests'", workdir="~/project")
```

Attach context files with `-f`:

```
terminal(command="kilo run 'Review this config for security issues' -f config.yaml -f .env.example", workdir="~/project")
```

Force a specific model:

```
terminal(command="kilo run 'Refactor auth module' --model openrouter/anthropic/claude-sonnet-4", workdir="~/project")
```

### Prompt Writing for `kilo run`

A good prompt is self-contained. Include:

1. **Goal** — what to build, specific deliverables
2. **Context** — project structure, file paths, existing patterns to follow
3. **Constraints** — tech stack, toolchain commands, test framework
4. **Verification** — how to check the work

Best practice for complex tasks: write the full prompt to `/tmp/kilo_prompt.txt` with `write_file`, then pipe it into `kilo run` via background terminal. This avoids inline quoting issues and lets you iterate on the prompt without re-sending.

### Interactive Sessions (Background via PTY)

For iterative work requiring multiple exchanges, start the TUI in background:

```
terminal(command="kilo", workdir="~/project", background=true, pty=true)
# Returns session_id

# Send a prompt
process(action="submit", session_id="<id>", data="Implement OAuth refresh flow and add tests")

# Monitor progress
process(action="poll", session_id="<id>")
process(action="log", session_id="<id>")

# Exit cleanly — Ctrl+C
process(action="write", session_id="<id>", data="\\x03")
```

Do NOT use `/exit` — Kilo inherits OpenCode's behaviour where `/exit` opens an agent selector. Use Ctrl+C (`\x03`) or `process(action="kill")`.

### Kilo Code Workflow Pattern

1. **Goal describes the WHAT** — be specific about deliverables, success criteria, and which files to touch
2. **Context describes the WHERE and WHY** — project path, existing files, test expectations, constraints
3. **For simple tasks** (1-2 files): inline `kilo run 'prompt'` with no background needed
4. **For complex tasks** (3+ deliverables): write prompt to file, pipe into `kilo run` in background with `notify_on_complete=true`
5. **Verify results** — the agent's summary is self-reported. Re-read written files and re-run tests after completion. Previous `kilo run` sessions have claimed success while writing nothing — always verify output files exist.
6. Exit interactive sessions with Ctrl+C or kill, never `/exit`.

### Known Install Paths

- Node global: `~/.hermes/node/bin/kilo` (symlink to `../lib/node_modules/@kilocode/cli/bin/kilo`)
- Also on this system: `~/.hermes/node/bin/copilot` (GitHub Copilot CLI, supports `--acp --stdio`)
- Check with: `which kilo` or `npm list -g | grep @kilocode`

### Pitfalls

- Kilo's ACP mode is **HTTP-only** (`kilo acp` starts a server on a port). No `--acp --stdio`.
- The `copilot` binary (from `@github/copilot`) IS a separate tool that supports `--acp --stdio` — use it for ACP-based Hermes delegation.
- Kilo writes a splash screen to stdout first. When capturing output, skip the ASCII art.
- Kilo may ask for permission to write to external directories — prefer writing inside the project working directory.
- `kilo run` does NOT need `pty=true`. Interactive `kilo` (TUI) does.
- The model Kilo uses is configured in its own config (`~/.local/share/kilo/`), NOT Hermes' config. On this system Kilo uses qwen36-35b via the local model manager proxy at :8079.

### Kilo Request Parameters (through model manager proxy)

When Kilo sends requests through the local model manager proxy (`:8079`), it has a specific parameter profile that differs from router preset defaults:

| Parameter | Kilo sends | Router preset (qwen36-27b) | Note |
|-----------|-----------|---------------------------|------|
| `top_p` | 1.0 | 0.95 | Kilo **overrides** this |
| `temperature` | not sent | 0.85 | Falls through to preset |
| `min-p` | not sent | 0.01 | Falls through to preset |
| `repeat-penalty` | not sent | 1.0 | Falls through to preset |
| `top-k` | not sent | 0 | Falls through to preset |
| `max_tokens` | 32000 | — | Always sent |
| `stream_options` | `{"include_usage": true}` | — | Always sent |

The `top_p=1.0` override means the model samples more broadly than the router preset expects. If output quality seems off, this is the first thing to check (router logs show `kwargs=` parameter dump).

### Verification

Smoke test:
```
terminal(command="kilo run 'Respond with exactly: KILO_SMOKE_OK'")
```
