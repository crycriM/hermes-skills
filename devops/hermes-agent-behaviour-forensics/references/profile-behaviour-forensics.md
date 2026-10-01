# Profile behaviour forensics — "the agent didn't do X"

How to decide whether a capability was genuinely unavailable or the model simply never used it,
**before** changing any config. Every artefact is per-profile: a secondary profile's logs are NOT in
the host journal, so `journalctl` looking empty means nothing.

## Where the evidence lives

- `~/.hermes/profiles/<name>/logs/agent.log` (INFO+, the turn-by-turn record),
  `errors.log` (WARNING+), `gateway.log` (platform/adapter traffic).
- `~/.hermes/profiles/<name>/state.db` — open read-only while the gateway runs (it holds the WAL):
  `sqlite3.connect('file:' + path + '?mode=ro', uri=True)`.
  Tables that matter: `messages` (`session_id`, `role`, `content`, `tool_calls`, `tool_name`,
  `timestamp`), `sessions`, `system_prompts` (columns: `hash`, `prompt`), `gateway_routing`.
  Note `system_prompts` has no session column — match a distinctive phrase, not a session id.

## Step 1 — did the model actually call the tool?

Tool results persist with `tool_name` set; the assistant's requests persist in `tool_calls` as JSON.

```sql
-- last real invocations of a tool, across every session
SELECT session_id, id, timestamp, substr(content,1,300) FROM messages
 WHERE tool_name='<tool>' ORDER BY id DESC LIMIT 10;

-- what the model actually asked for in one session
SELECT id, timestamp, substr(tool_calls,1,200) FROM messages
 WHERE session_id='<sid>' AND tool_calls LIKE '%<tool>%' ORDER BY id DESC;
```

If every hit for `<tool>` sits inside a `tool_describe`/`tool_search` call, the tool was never
invoked — stop looking for a tool bug. Corroborate in `agent.log`: `Turn ended: reason=guardrail_halt`
plus `identical_call_streak_halt` is the loop guardrail firing, not a tool error.

## Step 2 — was it available?

- The registry logs `<check_fn> returned False; dependent tools will be unavailable this turn` at
  INFO once per turn while the check is false, and a WARNING when it drops a tool that was previously
  available. Absence of those lines across recent turns ⇒ the gate passed.
- Decoy: `tool_describe`'s `'X' is a directly-listed tool, not a deferred one` is built from static
  name knowledge (`_core_tool_names()` / registry entry), never the turn's schema. It does not prove
  the tool was offered.
- Decoy: `tool_search` matches only DEFERRED tools. Zero matches for a built-in says nothing about
  whether that built-in is enabled.

## Step 3 — gate checks are often runtime-bound

Gates such as `check_vision_requirements()` resolve the main provider, so a bare interpreter with no
 turn bound reports `False` while the live turn reports `True`. Reproduce the turn: call
`set_runtime_main(provider, model, base_url=..., api_key=...)` first, then evaluate. Same trap for any
`check_fn` whose probe needs the profile's endpoint. `scripts/profile_tool_gate_probe.py` does this.

## Step 4 — probe with the runtime interpreter

Use the interpreter the `hermes` launcher names (`~/.hermes/tools/python-*/bin/python3`) with
`sys.path.insert(0, '~/.hermes/hermes-agent')` and `HERMES_HOME=~/.hermes/profiles/<name>`.
`hermes-agent/venv/bin/python` is not the runtime interpreter; imports of Hermes modules fail there
on third-party deps, which reads as a broken install when it is only the wrong python.

## Step 5 — prompt edits: prove they land, then expect a rebuild

A profile-home `AGENTS.md` is injected like `SOUL.md` (both read from HERMES_HOME), even though
`AGENTS.md` elsewhere is a git-root→cwd chain. Prove a line reached the model:

```sql
SELECT instr(prompt, '<distinctive phrase>') FROM system_prompts
 ORDER BY length(prompt) DESC LIMIT 3;
```

A non-zero offset is proof. A prompt edit only reaches a LIVE session after the gateway rebuilds its
cached agent — new session, or restart. Never expect a mid-conversation prompt change to apply; the
cached prefix is the cache invariant.

## Step 6 — turn the diagnosis into a fix

Order by blast radius, cheapest first, and ask the user before editing profile config or restarting a
gateway:

| Finding | Fix |
|---|---|
| Model never called an available tool; bridge tools present | One-line `AGENTS.md` directive naming the tool as directly callable |
| Same, recurring across sessions | `tools.tool_search.enabled: off` (or `defer: []`) for that profile |
| Gate genuinely false (no aux provider, no credentials) | Configure the missing provider/model, or accept the tool is absent |
| Tool returned an error every time (bad paths, wrong args) | Fix the prompt/skill guidance that produces the argument, not the gate |
