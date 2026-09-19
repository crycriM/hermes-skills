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
