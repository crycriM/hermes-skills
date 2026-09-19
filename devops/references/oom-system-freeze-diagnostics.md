# OOM / System Freeze Diagnostics

When the user reports "SSH was unresponsive for minutes" or "the machine froze," the router crash is often a **symptom**, not the cause. The chain is usually: memory overcommit → swap exhaustion → OOM killer → scheduler lockup → everything hangs, including SSH.

## Diagnostic checklist

```bash
# 1. System load & uptime — is it currently healthy?
uptime
# Load > 4x CPU cores means severe overcommit

# 2. Memory & swap pressure
free -h
swapon --show
# Swap near 100% = system was (or is) thrashing

# 3. OOM kills in kernel log
dmesg -T 2>/dev/null | grep -i -E '(oom|killed|out of memory|hung_task)' | tail -20
# Or if dmesg -T unavailable:
dmesg --level=err,warn --since "2 hours ago" 2>/dev/null | tail -40

# 4. Top memory consumers (RSS, not VSZ)
ps aux --sort=-%mem | head -10

# 5. Journal errors around the freeze time
journalctl --since "3 hours ago" -p err --no-pager | tail -30
journalctl --since "3 hours ago" -u watchdog* --no-pager 2>&1 | grep -i -E '(timeout|hung|lockup|freeze)' | tail -10

# 6. Check if the inference router itself survived
curl -s --max-time 5 http://localhost:8080/v1/models 2>&1
systemctl --user status m5-router.service 2>&1 | head -5
```

## Common patterns on this system (128GB Strix Halo)

| Symptom | Likely cause | Action |
|---------|-------------|--------|
| SSH unresponsive, machine reachable on network | Scheduler lockup from OOM reclaim | Check `dmesg` for `oom_kill` |
| Router reports model as "loading" forever | Child process was OOM-killed before init | `journalctl` shows killed PID |
| Router shows no models at all | Router itself could not allocate memory | Check `systemctl --user status m5-router` |
| `snapd Watchdog timeout` in journal | Side-effect, not cause — system was too busy to respond | Ignore, fix the OOM instead |

## Why an OOM kill makes SSH unresponsive

1. Kernel enters direct reclaim — scans pages synchronously
2. Swap is full — no room to page out
3. OOM killer selects a victim (usually the largest anonymous RSS consumer: llama-server)
4. Memory is freed, but during the selection/reclaim phase the **entire scheduler can stall** for minutes — no process runs, including sshd

This is distinct from a simple OOM where just one process dies cleanly. Full-system unresponsiveness means you were already deep into swap + reclaim before the kill.

## Prevention

- **Swap headroom:** If swap regularly exceeds 50%, increase it. 8GB is too little for 122GB RAM + multiple large models. 32–64GB gives the kernel room to page out without immediate reclaim pressure. Resize:
  ```bash
  sudo swapoff /swap.img
  sudo dd if=/dev/zero of=/swap.img bs=1M count=32768 status=progress
  sudo mkswap /swap.img
  sudo swapon /swap.img
  ```

- **vm.overcommit_memory:** Default `0` (heuristic) is fine. Do not set to `2` (strict) — it will kill processes on allocation rather than on memory pressure.

- **Model load limits:** The router's `--models-max 4` cap prevents loading too many models simultaneously. The loaded models consume ~15GB (qwen36-35b) + ~0.4GB (qwen35-9b). Loading deepseek-v4-flash (84GB) on top of those is what tips over the edge.

- **Check before loading a large model:** Verify free RAM is sufficient:
  ```bash
  free -h
  # Want at least model_size * 1.2 free (model loads temporarily spike RSS during init)
  ```
