# Router Collision Resolution

## Problem: Concurrent cron jobs causing 503/502 errors from router :8079

### Diagnosis

Symptoms: `HTTP 503: Failed to load model` / `HTTP 502: timed out` / `HTTP 500: proxy error` from cron jobs. The router can't serve concurrent model loads.

**Step 1: Identify collision windows**
```bash
# List all cron jobs with their schedules
cronjob action=list

# Look for jobs firing at the same time
# Common collision windows: 10:00 AM, 11:00 AM, 22:00 PM
```

**Step 2: Determine which jobs are LLM-bound (cause contention)**
- `no_agent` cron jobs (shell scripts, no LLM): negligible router load — they're safe
- Cron jobs with `model` field (e.g., `qwen36-35b`, `qwen36-27b`): LLM-bound, cause contention
- Cron jobs without `model` field: use the profile's default model — also LLM-bound

**Step 3: Check which jobs are LLM-bound at the collision time**
```bash
# Look at the cron job config for each colliding job
python3 -c "
import json
with open('/home/cricri/.hermes/cron/jobs.json', 'r') as f:
    data = json.load(f)
for job in data['jobs']:
    if job.get('id') == '<job_id>':
        print(f\"ID: {job['id']}, Name: {job['name']}, Schedule: {job.get('schedule_display')}, Model: {job.get('model')}, no_agent: {job.get('no_agent')}\")
"
```

### Fix: Stagger LLM-bound cron jobs

**Principle**: Move LLM-bound jobs to different minutes within the same hour. `no_agent` jobs (shell scripts) can stay at the top of the hour — they don't load models.

**Example (2026-07-03 fix)**:
```
Before (all at 10:00):
  - Error Scanner (LLM: qwen36-35b)    → 0 10 * * *
  - Paris music (LLM: qwen36-27b, Sat)  → 0 10 * * 6
  - Coinalyze OI (no_agent)             → 0 10 * * *

After (staggered):
  - Coinalyze OI (no_agent)             → 0 10 * * *  (stays, no LLM)
  - Error Scanner                         → 5 10 * * *  (10:05)
  - Paris music (Sat)                     → 15 10 * * 6 (10:15)

After (22:00 fix):
  - M5 power quiet (no_agent)            → 0 22 * * *  (stays)
  - august-nightly-dream (no_agent)      → 5 22 * * *  (22:05)
```

### When the fix is insufficient

If staggered jobs still collide (one LLM job takes >1 minute to start), the remaining risk is:
- Retry logic (3 attempts) in the cron job's prompt handles transient errors
- If retry is insufficient, the next session will get a new 503 and should re-stagger

### Prevention going forward

- Before creating new cron jobs, check `cronjob action=list` for existing jobs at the intended time
- LLM-bound cron jobs should land on different minutes (5, 10, 15, 30, etc.)
- `no_agent` shell scripts have zero router impact — they're safe at any minute
