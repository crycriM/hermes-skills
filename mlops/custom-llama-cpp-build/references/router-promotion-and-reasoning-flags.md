# Promoting a custom llama.cpp build onto the live router (m5-router)

Validated standalone on a test port first, then promote to the production router.

## Steps

1. **Point `~/llm-server/start-native-router.sh` at the new build** — two edits, both required:
   - `export LD_LIBRARY_PATH="/home/cricri/sources/llama.cpp-<branch>/build/bin:$LD_LIBRARY_PATH"`
   - `exec /home/cricri/sources/llama.cpp-<branch>/build/bin/llama-server \` (the `exec` line)
   - Set `VK_ICD_FILENAMES="/usr/share/vulkan/icd.d/radeon_icd.json"` — the old `.x86_64.json` path in historical scripts does NOT exist on the host (only `radeon_icd.json`). If you leave the old path in, the loader falls back to default ICD scanning and still finds the host RADV, so it can "work anyway" — but set the real path anyway.

2. **Keep `start-native-router.sh` KNOWN_KEYS validation current.** The script rejects ANY preset key not in the KNOWN_KEYS pipe-list *before* launching (`ERROR: Unknown preset keys`). When a new build adds a preset flag, add it to KNOWN_KEYS too. This session added `reasoning-effort` and `reasoning-preserve`.

3. **Edit `router-preset.ini`** — the target entry becomes the new model/draft/spec/reasoning config (see the reasoning-flag table below).

4. **Restart + verify**:
   ```
   systemctl --user restart m5-router.service
   systemctl --user status m5-router.service   # active (running)
   curl -s http://127.0.0.1:8080/health        # {"status":"ok"}
   curl -s http://127.0.0.1:8080/v1/models     # new model id/section present
   ```

5. **Verify spec decoding is GENUINELY engaged** — do not trust `/health` alone. The model loads lazily (per request), and the router's server logs may not land in `journalctl --user -u m5-router.service` in a filterable way (distrobox swallows the verbose llama-server stdout). Prove spec-decode via the native `/completion` endpoint, NOT OpenAI `/v1`:
   - Multi-model router mode: raw `/completion` (no `model`) → `400 model name is missing`. You MUST pass `"model":"<alias>"`.
   - OpenAI `/v1/chat/completions` → no `timings` field at all; and with `reasoning=on` the `content` comes back EMPTY (tokens go to `reasoning_content`).
   ```
   curl -s http://127.0.0.1:8080/completion \
     -d '{"model":"qwen38-27b","prompt":"<|im_start|>user\nName one color.<|im_end|>\n<|im_start|>assistant\n","n_predict":60}' \
     | python3 -c 'import sys,json; t=json.load(sys.stdin)["timings"]; print(t["draft_n"], t["draft_n_accepted"])'
   ```
   `draft_n_accepted > 0` = spec decoder (DFlash2/MTP) is live. A valid reply also shows the reasoning trace (` thinking\n...\n response\n...`) when `reasoning=on`.

6. **Throughput caveat**: first-token `predicted_per_second` on a short reasoning turn is dominated by graph warm-up + the reasoning block and understates sustained rate. For real throughput use `llama-bench` (offline, own process) or a long multi-turn completion — not a one-shot short prompt.

## Reasoning flag evolution (build ~10569+, strix-halo-vulkan branch)

New builds replaced the deprecated `chat-template-kwargs={"enable_thinking":…,"reasoning_effort":…}` overrides with native CLI flags:

| Old (deprecated) | New native preset key |
|---|---|
| `chat-template-kwargs={"enable_thinking":true}` | `reasoning = on` |
| `chat-template-kwargs={"reasoning_effort":"low"}` | `reasoning-effort = low` |
| `chat-template-kwargs={"preserve_thinking":true}` | `reasoning-preserve = true` |

- `reasoning-effort` accepts: `default | minimal | low | medium | high | xhigh | max`.
- The `enable_thinking` kwarg now emits `Setting 'enable_thinking' via --chat-template-kwargs is deprecated. Use --reasoning on / --reasoning off instead`.
- Keep `chat-template-kwargs` only for genuinely template-specific kwargs with no native flag.
- Reason tokens land in `message.reasoning_content` → OpenAI `/v1/chat/completions` `content` empty while thinking.
- `reasoning-preserve` keeps the reason trace across full history; pair with a template that declares `supports_preserve_reasoning` (e.g. `chat_template_sharp.jinja`).

## DFlash2 config (worked preset for Qwen3.8-27B)

`[qwen38-27b]` on the strix-halo-vulkan build — target `Qwen3.8-27B-UD-Q5_K_XL.gguf` (qwen35 arch), draft `Qwen3.8-27B-DFlash2-Q4_K_M.gguf` (`dflash.selector_top_k=16` ⇒ engine auto-sets `is_dflash2`), `chat_template_sharp.jinja`:

```
spec-type = draft-dflash
spec-draft-n-max = 4
cache-type-k = f16          # DFlash2 tuning; draft cache q8_0
cache-type-v = f16
cache-type-k-draft = q8_0
cache-type-v-draft = q8_0
reasoning = on
reasoning-effort = low
reasoning-preserve = true
batch-size = 4096
ubatch-size = 4096
threads-batch = 32
threads = 16
```
