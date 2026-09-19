# Hermes TUI `/tools` toolset validation

Validation lives in `tui_gateway/methods_tools.py` (tools.configure handler, ~line 1580):

```
valid_toolsets = {ts_key for ts_key, _, _ in CONFIGURABLE_TOOLSETS} | _get_plugin_toolset_keys()
unknown = [name for name in toolset_targets if name not in valid_toolsets]
```

`CONFIGURABLE_TOOLSETS` is defined in `hermes_cli/tools_config.py` (line ~96).

## Valid names (as of v0.20.4, 2026-08)

bfl, browser, clarify, code_execution, computer_use, context_engine, cronjob,
delegation, discord, discord_admin, file, homeassistant, image_gen, memory,
session_search, skills, spotify, stt, terminal, todo, tts, video, video_gen,
vision, web, x_search, yuanbao

(plus any plugin-provided toolset keys, e.g. spotify via `known_plugin_toolsets`
in config.yaml)

## Names that are NOT toolsets

- `messaging` — there is no toolset by this name. Messaging/bot tools are
  per-platform toolsets (telegram, discord, whatsapp, signal, mattermost, matrix,
  ...) defined in `toolsets.py`, and they only exist on the gateway side; the TUI
  cannot enable/disable them via `/tools`.
- `moa` — Mixture-of-Agents is a model mode, not a toolset. Configured in the
  `moa:` section of config.yaml; selectable from the TUI model picker. It appears
  in `agent/auxiliary_client.py` as a provider/mode concept.

## Request/response flow for `/tools disable|enable`

1. User types `/tools disable messaging moa` in the TUI.
2. Frontend `ui-tui/src/app/slash/commands/ops.ts` (line ~734) calls RPC
   `tools.configure` with `{action, names, session_id}`.
3. Python `tui_gateway/methods_tools.py` computes `unknown` and returns it in
   the response `{changed, enabled_toolsets, info, missing_servers, reset, unknown}`.
4. Frontend (line ~747) renders `unknown toolsets: messaging, moa` as a
   transcript sys line. Not an error — information only. Nothing is persisted for
   unknown names (`_apply_toolset_change` only touches valid ones).
5. If any name IS valid, the config is saved and (when a live session exists) the
   visible transcript is reset — which is why the warning can appear to "flash and
   disappear" at launch/command time. That reset is the history reset, not a crash.

## Debugging route for "unknown toolsets" reports

- Confirm the exact typed command in the session transcript (it's a response to
  `/tools`, never a launch error).
- To list what the user actually has enabled: `hermes tools` (CLI) or the
  `enabled_toolsets` field of the tools.configure response.
- The only "unknown toolsets" string in the TUI frontend bundle is the lowercase
  one from ops.ts:747. A capital "Warning:" prefix in a user report is paraphrase.

## TUI toolset env plumbing

- `hermes_cli/main.py::_normalize_tui_toolsets` → forwards toolsets to the TUI
  only via `HERMES_TUI_TOOLSETS`, and only when toolsets were passed explicitly
  (`-t/--toolsets`). Plain `hermes --tui` sends none; the TUI then builds its own
  catalog from the tui_gateway's platform-tools/prefill data.