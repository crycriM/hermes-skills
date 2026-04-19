---
name: session-usage-analytics
description: Analyze Hermes session token usage, costs, and performance patterns from the SQLite state database
---

# Session Usage Analytics

Analyze Hermes session token usage, costs, and performance patterns from the SQLite state database.

## When to Use

- Monitor token consumption and costs over time
- Debug unusual token usage spikes
- Understand input/output token ratios
- Analyze session patterns by platform (CLI, Telegram, Discord, Cron)
- Investigate cache utilization efficiency

## Database Location

Hermes stores session data in `~/.hermes/state.db` (SQLite with FTS5 search).

## Key Schema Fields

Sessions table (`sessions`):
- `input_tokens`: Total input tokens across all API calls
- `output_tokens`: Total output tokens across all API calls
- `cache_read_tokens`: Cache hit tokens (read from prompt cache)
- `cache_write_tokens`: Cache miss tokens (written to prompt cache)
- `reasoning_tokens`: Thinking/reasoning tokens (for thinking models)
- `started_at`: Unix timestamp when session started
- `source`: Platform source ('cli', 'telegram', 'discord', 'cron')
- `model`: Model identifier used

Messages table (`messages`):
- `token_count`: Token count per message (if available)
- `role`: Message role ('user', 'assistant', 'tool', 'system')

## Common Queries

### Daily Token Breakdown (Past N Days)

```bash
sqlite3 ~/.hermes/state.db << 'EOF'
.mode column
.headers on
SELECT 
  DATE(started_at, 'unixepoch') as day,
  source,
  SUM(input_tokens) as input,
  SUM(output_tokens) as output,
  SUM(cache_read_tokens) as cache_read,
  SUM(cache_write_tokens) as cache_write,
  SUM(reasoning_tokens) as reasoning,
  COUNT(*) as sessions,
  ROUND(SUM(input_tokens) * 1.0 / NULLIF(SUM(output_tokens), 0), 2) as io_ratio
FROM sessions 
WHERE started_at >= strftime('%s', 'now', '-5 days')
GROUP BY day, source 
ORDER BY day DESC, source
EOF
```

### Top Sessions by Token Usage

```bash
sqlite3 ~/.hermes/state.db << 'EOF'
SELECT 
  id,
  source,
  model,
  input_tokens,
  output_tokens,
  cache_read_tokens,
  message_count,
  tool_call_count,
  datetime(started_at, 'unixepoch') as timestamp,
  title
FROM sessions
WHERE started_at >= strftime('%s', 'now', '-5 days')
ORDER BY cache_read_tokens DESC
LIMIT 5
EOF
```

### Platform-Level Summary

```bash
sqlite3 ~/.hermes/state.db << 'EOF'
SELECT 
  source,
  SUM(input_tokens) as input,
  SUM(output_tokens) as output,
  SUM(cache_read_tokens) as cache_read,
  SUM(cache_write_tokens) as cache_write,
  SUM(reasoning_tokens) as reasoning,
  COUNT(*) as sessions,
  ROUND(SUM(input_tokens) * 1.0 / NULLIF(SUM(output_tokens), 0), 2) as io_ratio,
  ROUND(SUM(cache_read_tokens) * 1.0 / NULLIF(SUM(input_tokens), 0), 2) as cache_efficiency
FROM sessions 
WHERE started_at >= strftime('%s', 'now', '-5 days')
GROUP BY source 
ORDER BY input DESC
EOF
```

### Token Distribution by Model

```bash
sqlite3 ~/.hermes/state.db << 'EOF'
SELECT 
  model,
  SUM(input_tokens) as input,
  SUM(output_tokens) as output,
  SUM(cache_read_tokens) as cache_read,
  COUNT(*) as sessions,
  ROUND(AVG(input_tokens), 0) as avg_input_per_session
FROM sessions 
WHERE started_at >= strftime('%s', 'now', '-5 days')
GROUP BY model 
ORDER BY input DESC
EOF
```

## Interpreting Token Ratios

### Input/Output Ratio

Typical ranges:
- **5-15x**: Normal for tool-heavy autonomous workflows
- **1-5x**: Chat-like interactions, minimal tool use
- **>20x**: Very tool-heavy or context-heavy workloads

**Why input >> output in Hermes:**
- System prompt (~4K tokens) injected every turn
- Tool definitions (~2K tokens) resubmitted each API call
- File contents read by tools become part of context
- Long conversation history with tool results

### Cache/Input Ratio

- **>10x**: Excellent cache utilization (common with repetitive tool calls)
- **5-10x**: Good cache utilization
- **<5x**: Low cache utilization (may indicate unique contexts or cache misses)

**Cache semantics:**
- `cache_read_tokens`: Tokens served from prompt cache (no re-transmission)
- `cache_write_tokens`: Tokens written to cache (one-time cost)
- High cache read indicates efficient reuse of system prompts, tools, and context

### Tool-Heavy Sessions Indicator

Sessions with high input and many tool calls typically have:
- Input: >100K tokens
- Messages: >100
- Tool calls: >50
- Cache/Input ratio: >10x

## Cost Analysis

If you have pricing data (via `estimated_cost_usd` field), analyze costs:

```bash
sqlite3 ~/.hermes/state.db << 'EOF'
SELECT 
  source,
  model,
  SUM(estimated_cost_usd) as total_cost_usd,
  SUM(input_tokens) as input,
  SUM(output_tokens) as output,
  COUNT(*) as sessions,
  ROUND(SUM(estimated_cost_usd) * 1.0 / NULLIF(COUNT(*), 0), 4) as avg_cost_per_session
FROM sessions 
WHERE started_at >= strftime('%s', 'now', '-30 days')
  AND estimated_cost_usd IS NOT NULL
GROUP BY source, model 
ORDER BY total_cost_usd DESC
EOF
```

## Debugging Unusual Token Usage

### High Input Tokens in Single Session

1. Find the session:
```bash
sqlite3 ~/.hermes/state.db << 'EOF'
SELECT id, source, model, input_tokens, output_tokens, cache_read_tokens, message_count, tool_call_count
FROM sessions
WHERE started_at >= strftime('%s', 'now', '-5 days')
ORDER BY input_tokens DESC
LIMIT 1
EOF
```

2. Examine session JSON (if available):
```bash
# Find session file
ls -lht ~/.hermes/sessions/session_<SESSION_ID>.json

# Check message patterns
jq '.messages[] | {role: .role, has_tool_calls: (.tool_calls != null)}' ~/.hermes/sessions/session_<ID>.json | head -50
```

3. Check for large tool results:
```bash
jq '.messages[] | select(.role == "tool") | .content | length' ~/.hermes/sessions/session_<ID>.json | sort -rn | head -10
```

### Low Cache Utilization

Possible causes:
- Session has unique context every turn (no repetition)
- Prompt caching not enabled or not working
- Very short sessions (few turns to build cache)
- Different models/providers used inconsistently

Check if cache is working:
```bash
sqlite3 ~/.hermes/state.db << 'EOF'
SELECT 
  model,
  COUNT(*) as sessions,
  SUM(cache_read_tokens) as total_cache_read,
  SUM(cache_write_tokens) as total_cache_write,
  ROUND(SUM(cache_read_tokens) * 1.0 / NULLIF(SUM(cache_write_tokens), 0), 2) as hit_ratio
FROM sessions 
WHERE started_at >= strftime('%s', 'now', '-7 days')
GROUP BY model
EOF
```

## Python Analysis Script

For complex analysis, use Python with sqlite3:

```python
import sqlite3
from pathlib import Path
from datetime import datetime

db_path = Path("~/.hermes/state.db").expanduser()
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Example: Daily aggregation with cost efficiency
cursor.execute("""
SELECT 
  DATE(started_at, 'unixepoch') as day,
  source,
  SUM(input_tokens) as input,
  SUM(output_tokens) as output,
  SUM(cache_read_tokens) as cache_read,
  SUM(estimated_cost_usd) as cost,
  COUNT(*) as sessions
FROM sessions 
WHERE started_at >= strftime('%s', 'now', '-7 days')
GROUP BY day, source 
ORDER BY day DESC, input DESC
""")

for row in cursor.fetchall():
    day, source, inp, outp, cache, cost, sessions = row
    print(f"{day} {source}: {inp:,} in, {outp:,} out, {cache:,} cache, ${cost:.2f}, {sessions} sessions")

conn.close()
```

## Related Code

- `hermes_state.py`: SessionDB class, database schema
- `run_agent.py`: Token counting logic, `session_input_tokens`, `session_cache_read_tokens`
- `cli.py`: Session metrics display, `/token-usage` command

## Pitfalls

1. **JSON files vs SQLite**: Older Hermes versions used per-session JSON files. Current version uses SQLite. Check both if data seems incomplete.

2. **Time zones**: `started_at` is stored as Unix timestamp. Use `strftime()` for proper date conversion.

3. **NULL values**: Some fields may be NULL (e.g., `estimated_cost_usd`). Use `NULLIF()` in calculations to avoid division by zero.

4. **Cache semantics**: Cache tokens are NOT additional billed tokens — they're metadata about prompt caching efficiency. Don't double-count them as "cost".

5. **Tool result inflation**: Sessions with file reading tools (e.g., `read_file`, `search_files`) can have massive input tokens if large files are read repeatedly. Check tool call patterns in session JSON.

## Verification

After making changes to Hermes' token tracking:

1. Run a test session with known complexity:
```bash
hermes "Count the lines in ~/.hermes/state.db"
```

2. Check that the session was recorded:
```bash
sqlite3 ~/.hermes/state.db << 'EOF'
SELECT id, input_tokens, output_tokens, cache_read_tokens
FROM sessions 
ORDER BY started_at DESC 
LIMIT 1
EOF
```

3. Verify ratios make sense:
   - Simple queries: Input < Output (mostly user text, minimal tools)
   - File operations: Input > Output (file contents as input)
   - Long sessions: Cache read > Input (reusing cached context)

4. Check for missing token counts:
```bash
sqlite3 ~/.hermes/state.db << 'EOF'
SELECT COUNT(*) as zero_token_sessions
FROM sessions 
WHERE input_tokens = 0 OR output_tokens = 0
AND started_at >= strftime('%s', 'now', '-1 day')
EOF
```
Result should be 0 or very low (crons/scheduled tasks may have different patterns).
