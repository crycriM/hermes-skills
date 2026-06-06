# ChromaDB "Database or Disk is Full" Troubleshooting

## Symptom
```
chromadb.errors.InternalError: error returned from database: (code: 13) database or disk is full
```

This occurs when running `session_backfill.py` or `vault_indexer.py`. The ChromaDB SQLite database itself may be tiny (~188K), but the **disk partition where it lives** has no free space for WAL (write-ahead log) operations.

## Root Cause
ChromaDB uses SQLite with WAL mode. Even small writes require disk space for WAL files, journal files, and index updates. When the partition is at 100% capacity, ChromaDB cannot write even a single record.

## Location
- `/mnt/data1/cricri/llm-server/chroma-data/chroma.sqlite3` (the database — ~188K)
- The database lives on `/mnt/data1`, which is the partition that fills up

## Fix Steps

### 1. Check disk usage
```bash
df -h /mnt/data1
# Look for "Use%" at or near 100% and "Avail" showing 0
```

### 2. Find large consumers under /mnt/data1/cricri/
```bash
du -sh /mnt/data1/cricri/*/ 2>/dev/null | sort -rh | head -20
# Then drill down:
du -sh /mnt/data1/cricri/models/*/ 2>/dev/null | sort -rh | head -20
du -sh /mnt/data1/cricri/models/*.gguf 2>/dev/null | sort -rh | head -30
```

### 3. Verify which models are NOT in active use
Check the router config:
```bash
cat ~/llm-server/router-preset.ini | grep -E "^\[.*\]"
```
Then compare against running processes:
```bash
ps aux | grep llama-server | grep -v grep
# Note the --model paths being loaded
```

### 4. Remove unused large GGUF files
**Safe to remove**: models not configured in router-preset.ini AND not running.
```bash
rm /mnt/data1/cricri/models/Step-3.5-Flash-REAP-121B-A11B.i1-Q4_K_M.gguf  # was ~68G
```

### 5. Verify space freed
```bash
df -h /mnt/data1
# Should show several GB available (68GB after removing one large model)
```

### 6. Retry the backfill
```bash
cd ~/llm-server && ./venv/bin/python session_backfill.py 2>&1
```

## Prevention
- Keep disk usage under 90% on `/mnt/data1`. ChromaDB needs headroom for WAL and SQLite journal files.
- Periodically audit model directories — unused GGUF files are the primary space consumer.
- Consider moving rarely-used models to an external drive if space becomes tight.

## Historical Instances
- **May 17, 2026**: `/mnt/data1` at 100% (890G/938G). Removed `Step-3.5-Flash-REAP-121B-A11B.i1-Q4_K_M.gguf` (~68G) — unused model, not in router config or running. Back to 93%, freed ~68GB.
