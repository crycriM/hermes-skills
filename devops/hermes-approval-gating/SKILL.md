---
name: hermes-approval-gating
description: Use when tuning Hermes approval/clarify waits per profile.
version: 1.0.0
author: PinceMi
license: MIT
platforms: [linux, macos, windows]
tags: [hermes, approvals, clarify, profile, configuration, timeout, unattended, permissions]
metadata:
  hermes:
    tags: [hermes, approvals, clarify, profile, configuration, timeout, unattended]
    related_skills: [hermes-agent, multi-agent-profile-config, hermes-skill-gating]
triggers:
  - "approval timeout"
  - "permissions timeout"
  - "clarify timeout"
  - "user interaction timeout"
  - "approvals mode"
  - "agent doesn't wait for my answer"
  - "command approval"
---

# Hermes Approval & Interaction Gating

Two independent waits bound user interaction, and a third family of settings decides whether a run
waits for a human at all. Most requests for "a longer permissions timeout" are one of these axes
confused with another — settle the axis before touching a number.

## When to Use

- A lane whose human answers hours later, and an approval card or a `clarify` question expires first.
- An unattended or cron turn that "ignores" commands, or asks questions nobody can see.
- "It keeps asking for permission" / "it never asks" — mode-versus-timeout confusion.
- Any request to change a Hermes profile's permission or user-interaction behaviour, and to verify
  the change landed in that profile.

## The knobs

| Key | Default | Meaning |
|---|---|---|
| `approvals.mode` | `manual` when unset (shipped profiles often set `smart`) | `smart` \| `manual` \| `off`. Gates flagged **shell commands** on interactive surfaces. |
| `approvals.timeout` | 300 s | How long an approval card waits for a human. On expiry the command does **not** run (fails closed). Clamped to ~1 year (`agent.deadline.MAX_SAFE_TIMEOUT_S`). |
| `agent.clarify_timeout` | 3600 s | How long a `clarify` question waits. `0` or negative = unlimited. On expiry the agent unblocks with a "user did not respond" sentinel and continues instead of hanging. |
| `approvals.cron_mode` / `single_query_mode` / `unattended_mode` | `deny` | What happens with nobody to answer: `deny` refuses the command rather than waiting. No timeout value changes this. |

A legacy top-level `clarify.timeout` is honoured **only when explicitly set**; `agent.clarify_timeout`
is the canonical key. Neither knob is `terminal.timeout` (per-command execution cap) nor
`agent.gateway_timeout` (turn/busy window) — those are not permission waits.

## Procedure

1. **Pick the axis.** (a) A human *will* answer, just late (a messaging lane checked hours later) →
   raise `approvals.timeout` / `agent.clarify_timeout`. (b) Nobody is watching (cron, `-q`,
   unattended) → change the **mode** (`cron_mode` / `single_query_mode` / `unattended_mode`); a
   longer timeout is inert there. (c) The agent must never ask → `approvals.mode: off`
   (equivalent to `--yolo`).
2. **Write with the CLI, against the profile's own home.**
   ```bash
   hermes -p <profile> config set approvals.timeout 3600
   hermes -p <profile> config set agent.clarify_timeout 3600
   ```
   `-p/--profile` is pre-parsed and sets `HERMES_HOME` for the whole command; **omitting it silently
   edits the DEFAULT profile** even when the shell's CWD sits in a profile directory. Never hand-edit
   the YAML — the CLI writer preserves comments and key order, and a stray indent can break the live
   gateway.
3. **Read back through the runtime, not the file.** `hermes config get` only echoes what you wrote;
   the readers clamp and normalize. Run `bash scripts/probe-profile-timeouts.sh <profile>` — it prints
   the approvals block and both resolved windows using the same functions the gateway calls
   (`tools.approval_context._get_approval_timeout`, `tools.clarify_gateway.get_clarify_timeout`).
4. **No restart needed.** Both readers hit the config cache on every call, and the cache is keyed on
   the file's stat signature (mtime_ns, size, inode, ctime), so an in-place rewrite *and* an atomic
   replace both invalidate it. `hermes -p <profile> gateway status` shows who serves the profile —
   under the default multiplexer a named profile has NO gateway of its own, which is normal, not a
   fault.

## Pitfalls

- **`mode: auto` is not a mode.** Only `smart`, `manual` and `off` exist; any other value is logged
  and **silently normalized to `manual`**. A lane configured for `auto` prompts on every destructive
  command and looks like a broken timeout. Fix the mode name, not the number.
- **A timeout is not a mode.** Raising `approvals.timeout` does nothing in cron, single-query (`-q`)
  and unattended turns while `cron_mode` / `single_query_mode` / `unattended_mode` sit at `deny`.
  Symptom: an unattended run silently skips commands instead of hanging or asking.
- **The two waits are independent.** Extending `approvals.timeout` does not extend a `clarify`
  question (separate key, separate default of one hour) and vice versa.
- **Approval prompts gate shell commands only.** File writes, patches and reads never raise one, so
  "it edits without asking" is expected behaviour, not a misconfiguration.
- **Verify with the reader, not with `config get`.** Clamping (approval) and normalization (mode)
  happen inside the runtime functions; a file that reads 99999999 can resolve far lower. Report a
  profile setting as applied only after the probe agrees.
- **A clarify prompt that could not be delivered releases the turn immediately** with a sentinel
  rather than waiting out `clarify_timeout` — so a timeout that fired means the card reached the
  human and simply went unanswered.
