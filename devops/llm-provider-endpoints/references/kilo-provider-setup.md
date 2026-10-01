# Kilo Code provider setup - facts and verification ladder

## Where Kilo looks for things

| What | Path |
|---|---|
| Provider config | `~/.config/kilo/kilo.jsonc` |
| Bundled registry (authoritative env var names + default baseURLs) | `~/.cache/kilo/models.json` |
| Stored credentials | `~/.local/share/kilo/auth.json` |
| NOT config (node_modules / state) | `~/.kilocode/`, `~/.local/share/kilo/` |

`kilo.jsonc` shape for a provider block:

    "provider": {
      "<name>": {
        "options": {
          "apiKey": "{env:VAR_NAME}",
          "baseURL": "https://.../v1",
          "whitelist": ["model-a", "model-b"]
        },
        "models": { "model-a": { "name": "Model A", "tool_call": true } }
      }
    }

The provider id must also appear in `enabled_providers`, or the block is inert.

`{env:VAR}` resolves from `process.env` at load time, so secrets stay in the shell env.
Kilo also reads a bare `VAR_NAME` from the environment directly; that is what
`kilo auth list` reports under "Environment".

## Per-model entry keys that change what gets SENT

A model entry can carry more than `name`: some keys decide what the client puts on the wire, and
omitting them makes a UI control silently do nothing.

    "models": {
      "<model-id-as-served>": {
        "name": "Display name",
        "limit": { "context": 131072, "output": 16384 },
        "reasoning": true,
        "reasoning_options": [ { "type": "effort", "values": ["none", "minimal", "low", "medium", "high", "xhigh"] } ]
      }
    }

- **The map key must be the id the endpoint serves, not the display `name`.** A `model` config value or
  `-m` flag built from the display name fails with `Model not found: <provider>/<display-name>.
  Did you mean: <real-id>?`, and since it is the config default a bare `kilo run` (no `-m`) dies on it.
- **`limit` is what reserves output per request and what arms auto-compaction.** With no `limit`, Kilo
  reserves its 32000 default on every request, and compaction never fires while the context is unknown —
  both halves are load-bearing. Sizing rules and the 400 they prevent: `halogen-flash-lane` →
  "Clients must size `max_tokens` to the prompt".
- **`reasoning: true` + `reasoning_options` is what makes an effort picker send anything.** The variant map
  is built from this metadata; a custom model without it gets no map, so `--variant low|medium|high`
  (or clicking the picker) puts NO `reasoning_effort` on the wire and the endpoint quietly stays on its own
  default. Add the block and `--variant X` arrives as `reasoning_effort: X`.
- **The client's level vocabulary is not the endpoint's.** Kilo's enum is
  `none|minimal|low|medium|high|xhigh|max` and the chosen name is sent verbatim, so a level the endpoint
  rejects is a hard 400 (halogen rejects `max`; `xhigh` is its top). Levels outside the declared `values`
  are dropped, except ones in Kilo's own default set — declare every level the endpoint accepts.
- `"variants": {"low": {"body": {...}}}` is not a config key: it reaches the wire as a literal top-level
  `body` field and does nothing.

## Verification ladder - stop only when a step fails

Each step proves strictly more than the one before. Do not stop early.

1. `bash -c 'source ~/.bashrc; echo $VAR'` - the shell exports it in a NON-interactive context.
2. `kilo auth list` - Kilo matched the var to a provider (listed under "Environment").
3. `kilo models | grep <provider>/` - the catalog loaded. Proves nothing about credentials.
4. `curl` one cheap chat completion against the endpoint with the resolved key - proves the key is authorized AND funded.
5. `kilo run --model <provider>/<model> "<trivial prompt>"` - proves the whole path works in Kilo.

Steps 1-3 pass with a dead or unfunded key. Only 4 and 5 are real proof.

## Provider notes

- **Venice**: env `VENICE_API_KEY`; npm `venice-ai-sdk-provider`; default baseURL `https://api.venice.ai/api/v1`. Catalog is 100+ models, so always set a `whitelist`. Several Venice models return `reasoning_content` instead of `content` on short prompts, so an empty `content` field is not necessarily an error.
- **Local (llama.cpp / model_manager)**: `provider.local.options.baseURL` at `http://localhost:8079/v1`; needs `npm: @ai-sdk/openai-compatible` and an explicit `models` map, since there is no public catalog to fetch.

## Cheap multi-key probe

    bash -c 'source ~/.bashrc
    for k in ex2 ex3; do
      v=$(eval echo \$VENICE_API_KEY_$k)
      curl -s -X POST https://api.venice.ai/api/v1/chat/completions \
        -H "Authorization: Bearer $v" -H "Content-Type: application/json" \
        -d "{\"model\":\"zai-org-glm-4.7-flash\",\"messages\":[{\"role\":\"user\",\"content\":\"say OK\"}],\"max_tokens\":20}" \
        | head -c 300; echo
    done'
