---
name: router-service-recovery
description: Fix common failures of m5-router.service — preset.ini parse errors (orphan lines, invalid flags) and port 8080 conflicts from rogue llama-server processes that block GUI model selection.
---

# Router Service Recovery Skill

When `m5-router.service` fails to start, follow these steps:

1. **Check for errors in journal**
   ```bash
   journalctl --user -u m5-router.service --since "5 min ago" --no-pager | grep -E "(fail|error|not recognized)"
   ```
   Two common error types:
   - `failed to parse server config` — orphan line (bare filename without `key = value`) in INI
   - `option 'X' not recognized in preset 'Y'` — key `X` is not a valid `llama-server` CLI flag

2. **Edit `router-preset.ini`**
   - Path: `~/llm-server/router-preset.ini`
   - **Every key must be a valid `llama-server` flag.** Run `llama-server --help` to verify. Common invalid keys accidentally added: `backend`, `compression`, `t/s`, filenames.
   - Remove any orphan lines (bare filenames without `key = value` syntax).
   - Ensure model sections have standard keys: `n-gpu-layers`, `cache-type-k`, `cache-type-v`, `flash-attn`, `no-mmap`/`mmap`.
   - **Do not copy RoPE/sampling params from one model to another.** Each architecture has its own values (see step 6).

3. **Check for port conflicts**
   ```bash
   lsof -i :8080
   ```
   If another `llama-server` process is listening, kill it:
   ```bash
   kill <PID>
   ```

4. **Restart the service**
   ```bash
   sudo systemctl restart m5-router.service
   sudo systemctl status m5-router.service
   ```

5. **Verify models are loaded**
   ```bash
   curl http://localhost:8080/v1/models
   ```

6. **Validate model-specific params (RoPE, context, sampling)**
   When adding a new model, do NOT copy parameters from other sections. Each architecture differs:
   - Research the model's official config (HuggingFace model card `config.json`) for `rope_theta`, context length, etc.
   - If `rope_theta` is baked into GGUF metadata, llama-server uses it automatically — no `rope-freq-base` or `rope-scale` needed.
   - Example: Mistral Small 4 uses `rope_theta=1e8` (baked in, 128K native ctx). Leanstral uses `rope_freq_base=8192` + `rope_scale=128`. Copying one to the other is wrong.
   - Verify via `/v1/models` endpoint — check the `args` array for unexpected flags.

**Pitfalls**
- Do not add `t/s` or rate limiting entries to the INI; they are measurements, not settings.
- The preset only accepts CLI flags from `llama-server --help`. Verify each entry.
- Invalid keys like `backend`, `compression`, `t/s` cause immediate crash with `option 'X' not recognized`.
- Do not copy RoPE/sampling params between models — each architecture has its own values.
- After 2 failed patch attempts, stop and read the full file to ensure correctness.
- **Port conflict symptom:** If router starts but GUI won't show/select models, check for standalone `llama-server` process on port 8080 (PID from `lsof -i :8080`). Kill it before restarting m5-router.service. Router needs exclusive binding to serve multiple models.

**Verification**
- Ensure `m5-router.service` is `active (running)`.
- Open WebUI on port 8088 should list all models.
- Check journal for `Available models (N)` count and no errors.

## Adding Custom Chat Templates

When a model's built-in chat template has bugs (e.g. Qwen 3.5 tool calling crashes, thinking bleed, prefix cache invalidation), override it with a custom jinja template.

1. **Obtain the template.** Often found in GitHub issue threads or HuggingFace repos. Use the GitHub API to extract from comments if the HF link is dead:
   ```bash
   curl -s "https://api.github.com/repos/OWNER/REPO/issues/NUMBER/comments" | python3 -c "
   import json, sys
   comments = json.load(sys.stdin)
   body = comments[N]['body']  # N = comment index containing the template
   start = body.index('\`\`\`\n') + 4
   end = body.index('\n\`\`\`', start)
   print(body[start:end])
   " > ~/llm-server/model-chat-template.jinja
   ```

2. **Add to router-preset.ini** under the model section:
   ```ini
   jinja = true
   chat-template-file = /home/cricri/llm-server/model-chat-template.jinja
   ```
   Both lines are required. `jinja = true` enables the jinja engine; `chat-template-file` points to the override.

3. **Restart the router:**
   ```bash
   systemctl --user restart m5-router.service
   ```

4. **Verify the config was picked up:**
   ```bash
   curl -s http://localhost:8080/v1/models | python3 -c "
   import json, sys
   d = json.load(sys.stdin)
   for m in d['data']:
       args = ' '.join(m['status']['args'])
       print(f'{m[\"id\"]:25s} jinja={\"--jinja\" in args}  template={\"chat-template-file\" in args}')
   "
   ```

5. **Test the template.** Send a chat completion via curl:
   ```bash
   # Basic chat (check thinking/reasoning_content)
   curl -s http://localhost:8080/v1/chat/completions \
     -H "Content-Type: application/json" \
     -d '{"model":"MODEL_ID","messages":[{"role":"user","content":"Hello"}],"max_tokens":100}'

   # Tool calling (write payload to file to avoid shell escaping hell)
   python3 -c "
   import json
   payload = {
       'model': 'MODEL_ID',
       'messages': [{'role': 'user', 'content': 'What is the weather in Paris?'}],
       'tools': [{'type': 'function', 'function': {'name': 'get_weather', 'description': 'Get weather', 'parameters': {'type': 'object', 'properties': {'city': {'type': 'string'}}, 'required': ['city']}}}],
       'max_tokens': 200
   }
   json.dump(payload, open('/tmp/tool_test.json', 'w'))
   "
   curl -s http://localhost:8080/v1/chat/completions -H 'Content-Type: application/json' -d @/tmp/tool_test.json
   ```

**Pitfalls**
- The template file path must be accessible inside the distrobox container. `/home/cricri/` is bind-mounted, so paths like `/home/cricri/llm-server/xxx.jinja` work.
- For complex JSON payloads (tools, multi-turn), always write to a temp file and use `curl -d @file` — shell escaping of nested JSON is a nightmare.
- Models auto-load on first request. The first call will be slow (model loading), subsequent calls are fast.
- llama-server does NOT parse XML tool call output back into OAI `tool_calls` array. The XML appears in `content`. This is expected — the template ensures correct formatting for the model, but the server doesn't do structured parsing.

## Switching the Router's Distrobox Container

When moving m5-router.service from one distrobox container to another (e.g. switching from AMDVLK to RADV Vulkan, or upgrading to a new llama.cpp build):

1. **Check if the target container was created via distrobox.** If `distrobox enter CONTAINER -- whoami` fails with "unable to find user", the container was created with raw podman and needs to be recreated:
   ```bash
   podman stop CONTAINER && podman rm CONTAINER
   distrobox create --name CONTAINER --image IMAGE:TAG \
     --additional-flags "--device /dev/dri" \
     --volume /mnt/data2:/mnt/data2 \
     --yes
   ```
   Key flags: `--device /dev/dri` for GPU access, `--volume /mnt/data2:/mnt/data2` for secondary model storage.

2. **Verify the new container works:**
   ```bash
   distrobox enter CONTAINER -- llama-server --version
   distrobox enter CONTAINER -- ls /usr/share/vulkan/icd.d/
   ```

3. **Update `start-native-router.sh`** for the target container's Vulkan driver:
   - RADV only: `VK_ICD_FILENAMES="/usr/share/vulkan/icd.d/radeon_icd.x86_64.json"`
   - Remove ROCm env vars (`HSA_OVERRIDE_GFX_VERSION`, `ROCM_PATH`) if the container is Vulkan-only.

4. **Update `m5-router.service`** — replace all container name references:
   ```ini
   ExecStart=/usr/bin/distrobox enter NEW_CONTAINER -- /home/cricri/llm-server/start-native-router.sh
   ExecStop=/usr/bin/distrobox enter NEW_CONTAINER -- bash -c "pkill -TERM -f llama-server || true"
   ExecStopPost=/usr/bin/distrobox enter NEW_CONTAINER -- bash -c "pkill -9 -f llama-server || true"
   ```

5. **Deploy the updated service:**
   ```bash
   systemctl --user stop m5-router.service
   cp ~/llm-server/m5-router.service ~/.config/systemd/user/
   systemctl --user daemon-reload
   systemctl --user start m5-router.service
   ```

6. **Verify:** `curl http://localhost:8080/v1/models` should list all models.

7. **Stop old container:** `distrobox stop OLD_CONTAINER --yes`

**Pitfalls**
- Containers created with raw `podman` lack distrobox integration (no user, no init, no /dev bind). Always use `distrobox create` to recreate them.
- `distrobox create` with `--root` requires sudo with a terminal. Omit `--root` for rootless podman (user containers).
- `--pull=false` is not a valid distrobox flag. Omit it to use locally-available images.
- The VK_ICD_FILENAMES must match what's actually available inside the container. Check with `ls /usr/share/vulkan/icd.d/` and `ls /etc/vulkan/icd.d/` inside the container.

**References**
- See `~/llm-server/llm-models-combined.md` for model performance.
- Router preset file: `/home/cricri/llm-server/router-preset.ini`