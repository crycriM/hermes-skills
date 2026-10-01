# Retiring or replacing a model lane

Sweep order, live layer first, historical stores last. `grep -rn -i '<lane>' <paths>` at each layer; the
app layer must come back with NO hits before you tell anyone "the config is already clean" — otherwise
you are answering from one layer of a stack.

## 1. Hermes app config (the wiring)

```bash
grep -rn -i '<lane>' ~/.hermes/config.yaml ~/.hermes/profiles/*/config.yaml ~/.hermes/cron/jobs.json
```

Keys that wire a model to an endpoint, all of them separate wirings:

- `model.default` + `model.provider` + `model.base_url` — the interactive default.
- `providers.<name>.default_model` beside `providers.<name>.base_url` — the endpoint's default lane
  (this is how a local OpenAI-compatible server, e.g. a llama.cpp router on `:8079/v1`, is reached).
- `model_aliases.<alias>.{provider,base_url,model}` — friendly names passed by clients (delegation,
  desktop picker, external CLIs).
- `delegation.{provider,model,base_url}` — subagent children (they do not inherit the parent's model).
- `auxiliary.<tool>.{provider,model}` — vision, compression, skills_hub, title_generation, mcp, approval,
  flush_memories, session_search, web_extract, triage_specifier, curator, monitor. A stale one fails
  silently mid-task rather than at startup.
- cron jobs: per-job `"model"` (or `null` = inherit) in `cron/jobs.json`.

Edit through the CLI config path, never by hand-indenting the YAML of a live profile. Leave profiles on
remote providers alone unless the request names them.

## 2. The serving stack (where a local lane actually lives)

```bash
grep -rn -i '<lane>' ~/llm-server/router-preset.ini ~/llm-server/model-manager-config.yaml \
  ~/llm-server/MODEL_MANAGER_SPEC.md ~/llm-server/README.md ~/llm-server/*.py
```

- `router-preset.ini` — the `[<lane>]` section, `load-on-startup`, model path, `ctx-size`. Deleting the
  section is the removal; the replacement lane normally already exists, so never rename a section onto an
  existing name (duplicate `[names]` are ambiguous).
- `model-manager-config.yaml` — per-model reasoning tuning (`max_reasoning_tokens`,
  `logit_bias_strength`, `target_thinking_tokens`). An entry with no matching preset section is dead
  config; a missing entry just means default behaviour, so dropping it cannot break a loader.
- Derived numbers to recompute: preload totals in comments/docstrings, section counts in the spec and
  README, memory-headroom arithmetic, "active models" lists in docs. Stale counts mis-plan the next load.
- Back up before every edit:
  `cp -a <file> backups/<file>.before-<what>-$(date +%Y%m%d-%H%M%S)`, and quote the backup path in the
  report so the removal stays reversible.

## 3. Skills and knowledge docs

```bash
grep -rn -i '<lane>' ~/.hermes/skills --include='*.md'
```

Split the hits and treat the two classes differently:

- **Prescriptive** — "run cron / benchmarks / delegation on <lane>", active-model lists, preload
  arithmetic, cross-references that name the section as a config precedent → retarget to the surviving
  lane, or rewrite as a rule that does not depend on the section existing.
- **Historical** — journal excerpts, monitoring trees, dated worked examples carrying measured numbers,
  incident logs → leave them. They are the evidence the docs exist to keep; rewriting them falsifies the
  record. Say which class you kept.

## 4. Historical stores — never rewrite

- `~/.hermes/backups/`, `~/.hermes/state-snapshots/` — old config copies; they hold the retired lane by
  definition.
- `~/.hermes/logs/`, `~/.hermes/sessions/`, `~/.hermes/state.db` — `state.db` alone returns thousands of
  hits (FTS index over every past session). Session history is not configuration.
- Pruning these is a separate destructive decision: offer it, do not fold it into the sweep.

## 5. Verify

```bash
grep -rn -i '<lane>' <live config paths>                          # must exit 1 (no hits)
grep -c '^\[' ~/llm-server/router-preset.ini                      # section count after the delete
bash ~/llm-server/start-native-router.sh --help 2>&1 | head -30   # "Loaded N custom model presets" + list
ss -tlnp | grep -E ':(8080|8079)'                                 # service still owns the ports
ps -eo pid,ppid,cmd | grep llama-server | grep -v grep           # no stray probe child left behind
curl -s http://127.0.0.1:8079/api/models                          # replacement lane present
```

N in the banner must equal the number of uncommented sections, and the advertised model list must no
longer name the retired lane.

## 6. Effect timing and the restart decision

A preset deletion is inert until BOTH the router restarts (the INI is read at boot) and `model-manager`
restarts (the proxy builds its `:8079` model list at its own startup). Until then the retired lane still
appears in `/api/models` and in the router's advertised list — never call the removal live on the
strength of the edited file. Report it as pending, with the GB the restart re-preloads, and hand the
window to the user; `scripts/restart-router-when-idle.py` is the unattended path.

If a scope question goes unanswered (a clarify that times out), proceed on the literal instruction:
back up, make only edits with no immediate live effect, defer the restart, and report every judgement
call — which layers you changed and which hit classes you deliberately kept.
