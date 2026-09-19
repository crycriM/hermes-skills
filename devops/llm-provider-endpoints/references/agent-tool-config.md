# Disabling / verifying agent tools in kilo + opencode config

The natural home for this is the `ai-coding-agents` umbrella. Capture here because it is config-file work on the same `~/.config/kilo/kilo.jsonc`/`~/.config/opencode/opencode.jsonc` files this skill edits.

Both files are JSONC (comments + trailing commas allowed).

## Verify a config edit without guessing
- `kilo debug config` / `opencode debug config` prints the fully resolved merged config — confirm the key appears and exit code is 0 (parse/schema error exits non-zero).
- `opencode debug agent <name>` shows the agent's OWN resolved tools/permission map, NOT the runtime model-facing set — do not cite it as proof a tool is enabled/disabled. It also errors `Agent <name> not found` unless that agent is defined in the config, so it can't inspect built-in agents by bare name.
- Validate JSONC in Python with a STRING-AWARE comment+trailing-comma stripper: URLs contain `//` (`https://...`), so a naive regex comment-strip destroys valid content. Strip trailing commas with `re.sub(r',(\s*[}\]])', r'\1', txt)` AFTER removing comments.

## Disabling an interactive tool (the `question` / AskUserQuestion tool)
The top-level `tools` key is schema-valid and accepted by both CLIs but does NOT reliably propagate into the agent's model-invokable toolset. Model-invokable tools are gated at runtime by the PERMISSION system, and global config permission is merged into every agent, so the definitive kill-switch is a top-level entry:

```json
"permission": { "question": "deny" }
"tools":      { "question": false }
```

Keep BOTH: the documented `tools` key and the `permission` deny (the mechanism that actually blocks the tool). `deny` wins over an existing `*` allow catch-all. Agent-scope `tools` under `agent.<name>.tools` IS honored and visible in `debug agent`.

Caveat: some built-in agents never offer the `question` tool at all (e.g. kilo's default `code`). So a captured tool list lacking `question` does NOT prove your config disabled it, and its presence in `debug agent` output does NOT prove it is enabled at runtime.

## Empirically confirm which tools reach the model
Spin a throwaway OpenAI-compatible HTTP server that appends the `tools` array of each `/v1/chat/completions` request to a log; point a scratch config at it (isolated HOME + XDG_CONFIG_HOME/XDG_DATA_HOME/XDG_CACHE_HOME, mirroring `~/.cache/opencode`), then `opencode run --model fake/fake "probe"`. Read the log for the exact tool names offered. Return a minimal valid `chat.completion` JSON body or opencode loops/retries against the fake server.

## Terminal pitfall
`pkill -f <pattern>` also matches your OWN shell's command line when it contains `<pattern>`, SIGTERMing the shell running the command. Kill by PID instead.
