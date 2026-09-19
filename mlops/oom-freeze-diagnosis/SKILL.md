---
name: oom-freeze-diagnosis
description: Diagnose Strix Halo OOM freeze from model stacking, no swap.
tags: [strix-halo, oom, freeze, memory, amdgpu, diagnostics]
---

# OOM Freeze Diagnosis

Diagnose and prevent complete system lockups caused by LLM model stacking, memory exhaustion, and AMDGPU TTM deadlock on Strix Halo APU (128 GB unified memory).

## The Four-Ingredient Hard Freeze

A complete system freeze (mouse/keyboard/SSH all dead, hard reset required) requires four conditions:

1. **3+ LLM models loaded** — each model allocates TTM-pinned GPU memory that's invisible to `ps`/`free`. The GGUF file size is not the real cost — see TTM section below.
2. **No swap** — swap.img or swap partition missing or failed to activate at boot. Without swap, every allocation contention becomes a potential deadlock.
3. **AMDGPU TTM memory pressure** — GPU VRAM allocation (`amdgpu_ttm_tt_populate`) deadlocks when the kernel tries to page, because the GPU can't release pages without kernel allocations, and the kernel can't allocate because it's waiting for GPU pages.
4. **High `ttm.pages_limit`** — the kernel param `ttm.pages_limit=32505856` (124 GB) allows the GPU to pin nearly all 128 GB of system RAM, leaving no headroom for the kernel to recover.

The OOM killer fires but can't free enough memory because VRAM-backed allocations (TTM-pinned) don't page. The kernel enters a deadlock where `__alloc_pages_may_oom` is called repeatedly but the only candidate processes are TTM-backed themselves. No panic, no crash dump — just a dead machine.

**Key insight:** stacking 3 models (qwen38-27b + qwen36-35b + qwen35-9b) leaves ~55 GB of free RAM by `free`/`ps` metrics. The real memory pressure comes from TTM-pinned GPU memory that these tools cannot see. The TTM layer can pin up to 124 GB of system RAM (controlled by the kernel boot param `ttm.pages_limit=32505856`), and `ps` RSS values only show the process's userspace resident set — not the GPU-allocated pages.

## Diagnostic Workflow

### Step 1: Check boot list

```bash
journalctl --list-boots
```

A frozen boot leaves **zero journal entries** for the period around the freeze. The boot that was running when the freeze happened will have its LAST ENTRY timestamp well before the actual freeze. If the machine was force-restarted, there will be a fresh boot (index 0).

**Smoking gun:** Boot -1 (the freeze boot) has LAST ENTRY hours or days before the freeze, with no entries in the reported window. Boot 0 (recovery) is fresh from the restart time.

### Step 2: Check the recovery boot for OOM kills

```bash
journalctl -b 0 -p warning --no-pager | grep -iE "oom|out of memory|killed process"
```

If the recovery boot immediately shows OOM kills (within seconds of restart), it confirms critical memory pressure. Look for:

- `open-webui.service: Failed with result 'oom-kill'`
- `rag-service.service: Failed with result 'oom-kill'`
- `Out of memory: Killed process N (llama-server)`
- `Out of memory: Killed process N (chrome)`

### Step 3: Check for AMDGPU TTM involvement

```bash
journalctl -b 0 -p warning --no-pager | grep -i "amdgpu_ttm_tt_populate\|amdgpu_bo_create\|amdgpu_bo_create_user"
```

If the OOM callstack includes `amdgpu_ttm_tt_populate` and `amdgpu_bo_create`, the GPU TTM layer was a participant in the deadlock. This is the distinguishing factor between a recoverable OOM (system slows down, OOM killer picks a victim, services restart) and a hard freeze (hard reset required).

### Step 4: Check swap status

```bash
free -h                # Swap: 0B 0B 0B → no swap
swapon --show          # (empty) → no swap at all
journalctl -b 0 -p err | grep -i "swap"  # "Failed to activate swap" → swap missing at boot
```

**How swap makes OOM recoverable:** With swap, the kernel pages out cold anonymous memory to disk, freeing RAM for the OOM killer's target. Without swap, every allocation contention becomes a potential deadlock, especially with GPU TTM involvement.

## The Signature Pattern

| Symptom | Recoverable OOM | Hard Freeze |
|---------|----------------|-------------|
| Machine responsiveness | Slow but terminal/SSH works | Completely dead |
| OOM killer fires | Yes, picks a victim, services restart | Yes, but can't free enough |
| GPU TTM in callstack | No | Yes |
| Swap available | Yes | No |
| Journal entries around freeze | Present up to the OOM event | Missing — freeze doesn't flush journals |
| Recovery | Wait for OOM, or kill a process | Hard reset |

## Pitfalls

1. **Don't assume a blank journal means the system was idle.** Frozen systems don't flush journald buffers. The absence of entries around the reported time IS the evidence.

2. **The recovery boot's OOM massacre is diagnostic, not a separate problem.** When the PC restarts after a freeze, remaining services try to re-allocate memory simultaneously. The OOM kills in the recovery boot confirm the freeze was memory-related.

3. **Swap.img activation failure is silent.** `swap.img.swap` can fail at boot without any user-visible error. The only symptom is `free -h` showing `Swap: 0B`. Check `/etc/fstab` and `journalctl -b 0 -p err | grep swap`.

4. **Startup race with swap.img.** If `/swap.img` is on a filesystem that mounts late, swap won't be available at boot. Put swap on the root filesystem partition.

## Prevention

1. **Fix swap before stacking models.** Check `free -h` before loading multiple LLMs:
   ```bash
   ls -lh /swap.img                    # check if file exists
   sudo swapon /swap.img               # activate if exists but inactive
   sudo fallocate -l 32G /swap.img     # recreate if missing
   sudo chmod 600 /swap.img && sudo mkswap /swap.img && sudo swapon /swap.img
   grep swap /etc/fstab                # verify fstab entry
   ```

2. **Don't stack 3 big models without swap.** On 128 GB Strix Halo, qwen38-27b + qwen36-35b + qwen35-9b + Chrome + Open WebUI + RAG exceeds the OOM surge threshold. With swap, it's a slow degrade; without swap, it's a hard freeze.

3. **Monitor memory pressure before adding models.** If free memory < 15 GB and no swap is available, refuse to load another model.

4. **Consider staggering model loads.** A delay between model server starts lets the OOM killer clean up background processes before the next model's VRAM allocation starts.