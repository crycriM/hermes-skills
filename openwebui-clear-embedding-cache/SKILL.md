---
name: openwebui-clear-embedding-cache
description: Skill to clear Open-WebUI embedding cache to fix 500 errors caused by architecture mismatch.
---
# Skill: Clear Open-WebUI embedding cache to resolve 500 errors

## When to use
- Open-WebUI returns HTTP 500 after a recent start.
- Logs show `embeddings.position_ids | UNEXPECTED` or similar architecture mismatch warnings.
- The embedding model snapshot was built for a different architecture (e.g., CPU AVX‑512 vs GPU ROCm).

## Steps
1. **Identify the snapshot directory**  
   ```bash
   docker exec open-webui ls -R /app/backend/data/cache/embedding/models/models--sentence-transformers--all-MiniLM-L6-v2/snapshots/
   ```
2. **Delete the problematic snapshot** (replace the hash with the one you see):  
   ```bash
   docker exec open-webui rm -rf /app/backend/data/cache/embedding/models/models--sentence-transformers--all-MiniLM-L6-v2/snapshots/<snapshot_hash>
   ```
3. **Restart the container**  
   ```bash
   docker restart open-webui
   ```
4. **Watch the logs** to ensure the model is re‑downloaded:  
   ```bash
   docker logs -f open-webui | grep -i "Loading weights"
   ```
5. **Verify the UI** – open `http://<host>:3000` and run a simple prompt.

## Why it works
The snapshot was cached for a different CPU instruction set. Deleting it forces the container to download a fresh, architecture‑compatible model on next start.

## Caveats
- Deleting the cache removes all previously stored embeddings; you may need to re‑index documents.
- Ensure the container has internet access to download the model.

## Example script (optional)
```bash
#!/usr/bin/env bash
# clear_openwebui_embedding.sh
SNAPSHOT=$(docker exec open-webui find /app/backend/data/cache/embedding/models/models--sentence-transformers--all-MiniLM-L6-v2/snapshots -maxdepth 1 -type d | head -n1)
docker exec open-webui rm -rf "$SNAPSHOT"
docker restart open-webui
echo "Embedding cache cleared and Open‑WebUI restarted."
```

Save this script under `scripts/clear_embedding_cache.sh` for reuse.

## Related skills
- `openwebui-restart` (if you have one)
- `mlops-embedding-model-download`