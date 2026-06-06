# Session Indexing Log — May 14, 2026

Cron job: full re-index + service restart.

**Observations:**
- Vault indexer: 12,629 chunks in skills collection (253 batches). Clean run, ~60s.
- Session backfill: 1 new session indexed (5 chunks). Sessions now at 613.
- `pkill -f "rag_service.py"` returned exit code -15 (itself SIGTERM'd) without killing the process. Process survived and port 8001 stayed bound.
- Fallback: `kill -15 3193727` worked. Service restarted cleanly.
- Lesson: verify port is free after pkill before starting the new service instance.

**Action taken:**
- Patched `rag-service-maintenance` skill v1.2.0 → v1.3.0:
  - Replaced the "pkill is cleaner and more reliable" section with a verified pkill approach that checks port status after killing and falls back to explicit PID kill + SIGKILL if needed.
  - Updated expected collection counts to current values (skills: 12629, sessions: 613).
