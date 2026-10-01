# Driving the halogen lane from a client

Client-side depth for `SKILL.md`: the reasoning-effort wire protocol, the
`max_tokens`/context reservation rule, and the per-client wiring for Kilo Code,
Zed (ACP) and opencode. Read this when pointing a client at `:8741` or when an
effort picker appears to do nothing.

## Client-side reasoning control (verified live 2026-09-29, API 0.14.2)

Thinking is chosen **per request by the client**; the engine advertises it in `/health`
(`chat_template.thinking_control: true`, plus `supported[]`). Levels:
`none | minimal | low | medium | high | xhigh`, **default `xhigh`** — an omitted field means
thinking ON. Every shape below was verified to take effect on both wires:

- top-level `reasoning_effort`, `chat_template_kwargs.reasoning_effort`, and the nested
  `reasoning: {effort: ...}` object (`/v1/responses`, the Codex shape) — all equivalent.
- budgets: `max_thinking_tokens`, `thinking_budget_tokens`, `thinking_budget`,
  `thinking_token_budget` (`token_budget_aliases` and `thinking_control_aliases` in `/health`).
- hard off: `enable_thinking: false` — no `reasoning_content` key at all in the response message.

An unknown level is a **400 that names the valid set**
(`reasoning_effort 'banana' unsupported; use minimal|low|medium|high|xhigh|none`): the level is
validated by the engine, not by the template. `token_budget_covers_reasoning: true`, so
`max_tokens` caps the CoT too, and `thinking_answer_room = max(1024, 15% of max_tokens)` is what a
shared budget leaves the answer. A forced tool call disables thinking
(`tool_calls.forced_call_disables_thinking: true`).

Measured on one hard prompt (12-term recurrence + proof), greedy, n=1 per level — reasoning tokens:

none 0 · low 1083 · minimal 1180 · medium 1240 · default 1596 · xhigh 2431 · high 3097.

The effect is real and large; the levels are **not strictly ordered in a single sample**, so repeat
before quoting any per-level calibration.

Two gotchas:

- With effort `none` the CoT does not disappear, it moves into `content` (3,337 chars against 616
  at default, same prompt). Answer length is therefore not a thinking proxy — read
  `usage.completion_tokens_details.reasoning_tokens`.
- model-manager does **not** proxy this lane's chat completions (it only starts/stops it and drives
  the GUI buttons), and its preset `reasoning-effort` keys are llama.cpp-router business, so clients
  must point at `:8741` directly and set the field themselves.

## Clients must size `max_tokens` to the prompt (the 400 that kills agent sessions)

`serve_api.py` rejects `prompt + max_tokens > HALOGEN_CTX` with
`400 max_tokens N does not fit: prompt is P tokens and the context is C, leaving room for R.`
(a prompt alone over the ctx gets `the prompt does not fit: ... tokens over`). Hard error,
never truncation, so the client must reserve output itself. Do NOT raise the lane's context for
a client that asks for a 32k reservation.

Verified 2026-09-29 with a logging echo server while driving Kilo Code CLI 7.8.1 at
`http://localhost:8741/v1`:

- Kilo sends `max_tokens = min(model.limit.output, 32000) || 32000`, so a custom model entry with
  no `limit` reserves 32000 on *every* request (measured: 32000 with no limit, 8192 with
  `limit.output: 8192`).
- Kilo's auto-compaction is a no-op while `limit.context === 0`: the trigger is
  `count(tokens) >= limit - reserved` and the predicate returns false when the context is unknown.
  A session with an unknown context therefore grows past the point where 32000 output fits and
  every subsequent turn 400s — no compaction ever fires to rescue it.
- Fix in `~/.config/kilo/kilo.jsonc`, per local model entry:
  `"qwen3.8-flash-next-halogen": {"name": "qwen38-flash", "limit": {"context": 131072, "output": 16384}}`.
  `kilo config check` accepts the block; `limit.input` is optional. Then compaction fires at
  `context*threshold_percent/100 - reserved` (reserved = `compaction.reserved` or
  `min(20000, maxOutputTokens)`), so a 131072 context + 60% threshold + 16384 output compacts
  around 62k tokens, comfortably before the wall.
- Keep the output limit from getting too small: `thinking_answer_room = max(1024, 15% of max_tokens)`
  means 8192 leaves only ~1229 tokens of visible answer after xhigh reasoning (logs show
  `closed at N by answer room`).

## Driving it from Kilo Code (CLI 7.8.1)

Kilo's effort picker is **cosmetic** for a custom `@ai-sdk/openai-compatible` provider until the
model declares its reasoning metadata. Captured on the wire (logging proxy, scratch config — no
user config touched): `--variant low|medium|high|max`, no variant, a Kilo-recognised id
(`deepseek-v4-flash`), and a per-model `options` block ALL produced the same body keys —
`max_tokens, messages, model, stream, stream_options, tool_choice, tools`. No `reasoning_effort`,
ever, so the lane stays on the engine default (`xhigh`). That is also what "the selection is stuck
on low, whichever level I click" looks like: no variant map, so the click does nothing.

A `variants: {"low": {"body": {...}}}` block is worse than useless — it passes through as a literal
top-level `body` key in the request.

**The fix is config-only.** On the model entry in `~/.config/kilo/kilo.jsonc`:

```jsonc
"qwen3.8-flash-next-halogen": {
  "name": "qwen38-flash",
  "reasoning": true,
  "reasoning_options": [
    { "type": "effort", "values": ["none", "minimal", "low", "medium", "high", "xhigh"] }
  ]
}
```

With that, `--variant X` lands as `reasoning_effort: X` — verified for none/low/medium/high/xhigh.

- Kilo's effort enum is `none|minimal|low|medium|high|xhigh|max`, and **`max` is a trap**: the
  engine answers 400 (`use minimal|low|medium|high|xhigh|none`) and Kilo surfaces it as an error.
  Use `xhigh` as the top level. A level outside the declared list is dropped, except those in
  Kilo's default set (`max` survived undeclared).
- The default model in `kilo.jsonc` must be the real id: `"model": "local/qwen38-flash"` (the
  display name) fails with `Model not found ... Did you mean: qwen3.8-flash-next-halogen?`, and a
  bare `kilo run` dies on it. The same trap sits on `agent.<name>.model`, `small_model` and
  `subagent_model` — five keys in all, fixed 2026-10-01. Signature over ACP: `session/new` comes
  back on `venice/claude-sonnet-4-6` with a 4-item generic effort list instead of the local model
  with its six. A display name does not error there, it silently falls back.
- The engine accepts ANY model id (200 for `deepseek-v4-flash`), so the id is a label only; the
  served model is not selected by name.
- `kilo run --variant` is the way to test this headlessly; the proxy harness and captured bodies
  live in `~/.hermes/cache/scratch/halogen-effort/`.

### Advertising the modes (so the picker works with no per-model config)

Two routes, both verified on CLI 7.8.1; pick one.

**Catalog route.** Kilo reads its model catalog from `${KILO_MODELS_URL:-https://models.dev}/api.json`
or straight from the file named by `KILO_MODELS_PATH`. Serve a *merged* catalog — models.dev's
providers plus an injected `local` provider whose model carries `reasoning_options` — and the picker
advertises the levels itself. `~/.hermes/cache/scratch/halogen-effort/refresh-kilo-catalog.py` builds
it (225 providers + local; openrouter/venice metadata kept). Verified: none/low/medium/high/xhigh
**and minimal** all reach the wire. A file older than the 5-minute freshness window still works —
explicit naming is honoured, no refetch is required. models.dev **403s a bare urllib UA**, so send a
browser-ish one or the refresh dies.

**Plugin route (no env vars, nothing global).** A plugin listed in the config's `plugin` array whose
`config` hook stamps `reasoning: true` + `reasoning_options` onto the local model. Verified:
none/low/medium/high/xhigh on the wire. Kilo does **not** auto-discover `<config-dir>/plugin/` or
`<config-dir>/plugins/` — it must be listed in `plugin` (where ponytail already lives).

Limits of both routes:

- Neither can remove Kilo's own extra `max` variant for openai-compatible providers; picking it is
  a 400 from the engine.
- The plugin/config route drops **`minimal`** before the wire while the catalog route sends it —
  the catalog is what populates the variant map, the config hook only extends it. The engine treats
  minimal ≈ low, so advertise `["none","low","medium","high","xhigh"]` and lose nothing real.

### Wiring the env var: interactive shells vs agent-run kilo

- **`~/.bashrc` has an interactive-shell guard** (line 13 on this box): everything below it is
  invisible to non-interactive shells (Kilo Code, cron, scripts) — which is why the Venice keys sit
  *above* it. Put the `export KILO_MODELS_PATH=...` above the guard, or it does nothing for anything
  but your own terminal.
- Verified end-to-end through the real `kilo.jsonc` and the real lane: an interactive shell's
  `kilo models` lists `local/qwen3.8-flash-next-halogen` from the injected catalog, and
  `kilo run --variant none --thinking` prints **no thinking block** while `--variant xhigh` prints
  one. The picker genuinely drives the engine.
- **Agent-run `kilo run` does not inherit `~/.bashrc`.** Hermes' terminal sources the files in
  `terminal.shell_init_files` (without an explicit list: `~/.profile`, `~/.bash_profile`,
  `~/.bashrc`; an explicit list disables `auto_source_bashrc`), and `~/.hermes/config.yaml` +
  `~/.hermes/.env` are **not agent-writable** — the user has to add the hook. Until it is wired,
  prefix the variable per invocation (`KILO_MODELS_PATH=$HOME/.config/kilo/models-catalog.json
  kilo run ...`) or rely on the plugin route.
- `kilo models --verbose` does **not** show the catalog's reasoning fields for a custom provider
  (it printed `reasoning: null`, `limit.output 24576`). Judge this wiring by the wire, not by that
  listing.

## Driving it from Zed (ACP) — effort is a session configOption

Zed installs its own copy of the CLI (`~/.local/share/zed/external_agents/registry/kilo/v<ver>/kilo`,
downloaded from the GitHub release) and spawns it as **`kilo acp`**, a stdio JSON-RPC server.
`initialize` → `session/new` returns `configOptions` — that is what Zed renders as pickers:

| id | category | type | notes |
|---|---|---|---|
| `model` | model | select | 149 entries on this box, incl. `local/qwen3.8-flash-next-halogen` |
| `effort` | `thought_level` | select | **per current model**, agent-validated |
| `mode` | mode | select | code / ask / debug / plan |

The effort list follows the *selected* model. Measured 2026-10-01 with the Zed registry binary (7.8.1):

- `local/qwen3.8-flash-next-halogen` **with the catalog env**: `none, minimal, low, medium, high, xhigh`, current `none`
- same model **with no metadata at all**: `none, low, medium, high, xhigh, max` — i.e. the picker always
exists, and `max` (a 400 from the engine) is what the missing metadata costs
- `venice/qwen-3-8-27b`: `none, low, medium, xhigh` · `opencode-go/deepseek-v4.1-flash`: `low, high, max`

`session/set_config_option {configId:"effort", value:…}` out of range is refused agent-side
(`Invalid params: effort not found: none`), so the list is real, not cosmetic. Verified through a logging
proxy that the selection reaches the engine: `reasoning_effort: none` / `reasoning_effort: xhigh` on
`/v1/chat/completions`, with `max_tokens 24576` taken from the config `limit` block.

Two traps:

- **A fresh ACP session on the local model starts at effort `none` = thinking OFF**, even though the
  engine's own default with the field omitted is `xhigh`. Pick a level in Zed, or you get no CoT.
- Declaring `reasoning_options` in `kilo.jsonc` does **not** change the ACP list (verified: identical
  with and without it) — the order of merit is catalog > config > nothing. The catalog is the only
  route that yields the clean six (keeps `minimal`, drops `max`).
- Per-agent `"variant"` in `kilo.jsonc` does **not** set the ACP session default, and the config's
  `"model": "local/qwen38-flash"` (a **display name**) does not resolve: `session/new` came back on
  `venice/claude-sonnet-4-6` every time. Use the real model id `local/qwen3.8-flash-next-halogen`.

Probes (reusable, no user config touched): `~/.hermes/cache/scratch/halogen-effort/` —
`acp_probe.py` (initialize + session/new dump), `acp_effort_probe.py` (per-model effort lists),
`acp_drive.py` (set model → set effort → prompt, with `KILO_CONFIG` scratch config),
`logproxy.py` (8752 → 8741 body logger).

## Driving it from opencode (CLI 1.18.34, verified 2026-10-01)

opencode looks like Kilo on the wire but the knobs are in different places. All bodies below
captured with a logging echo proxy in front of `:8741` (stdlib forward proxy, logs every body);
the real config was left alone and a scratch `XDG_CONFIG_HOME` was used.

- **Model id must be the real id.** `local/qwen38-flash` is the *display name*; opencode answers
  only `UnknownError: Unexpected server error` (no `did you mean`, unlike Kilo). Use
  `local/qwen3.8-flash-next-halogen`. Same for every `agent.<name>.model`.
- Baseline body keys for a custom `@ai-sdk/openai-compatible` model with no extra metadata:
  `max_tokens, messages, model, stream, stream_options` (+ `tool_choice, tools` when the agent
  has tools). No reasoning field at all — same silent drop as Kilo.
- **Per-model `options` ARE forwarded** (this is the lever Kilo does not have):
  `"options": {"reasoningEffort": "none"}` → wire `reasoning_effort: none`. Camel-case is
  required; a snake-case `reasoning_effort` key is dropped. `"options": {"max_tokens": N}` →
  wire `max_tokens: N`.
- **`limit.output` is NOT `max_tokens`.** Tested 4096 / 8192 / 24576 / absent: the wire always
  carried `max_tokens: 16384` (opencode's own default for a custom provider). `"options":
  {"max_tokens": N}` is the knob that actually moves it. Still set `limit.context` (131072) so
  compaction has a real window — opencode's trigger with an unknown context was NOT measured.
- **`variants` on the model entry work** and are the opencode equivalent of the Kilo effort
  picker:
  ```jsonc
  "variants": {
    "none":  { "reasoningEffort": "none" },
    "minimal": { "reasoningEffort": "minimal" },
    "low": { "reasoningEffort": "low" },
    "medium": { "reasoningEffort": "medium" },
    "high": { "reasoningEffort": "high" },
    "xhigh": { "reasoningEffort": "xhigh" }
  }
  ```
  `opencode models --verbose` advertises them; `opencode run --variant xhigh` lands
  `reasoning_effort: xhigh` on the wire (same for none/low). With the block present but no
  `--variant`, the main request sends nothing (= engine default xhigh) while the *title-generation*
  request sends `none`. Advertise the engine's own set and never `max` — the engine 400s it.
- A non-native agent (`agent.ask`, `agent.code` — Kilo roles that opencode has no built-in for)
  still gets opencode's default system prompt (a 31k-char system message was on the wire) and
  `mode: "all"`, so those entries are usable once the model id is fixed.
- Killing the test proxy: `pkill -f "proxy.py 8742"` matches the shell running it — kill by PID.
  Reusable harness: `scripts/client-logging-proxy.py` (8742 → 8741, bodies to JSONL, sibling of
  this file). Run a throwaway config with `XDG_CONFIG_HOME=<scratch>`: `OPENCODE_CONFIG` and
  `OPENCODE_CONFIG_CONTENT` are MERGED, not substituted, so the real config keeps winning
  (verified 1.18.34).
