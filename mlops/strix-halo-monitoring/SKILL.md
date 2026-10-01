---
name: strix-halo-monitoring
description: Monitor CPU/GPU temps, power draw, and clock speeds on Bosgame M5 (Strix Halo APU gfx1151) during inference. Includes hwmon sensor map, monitor script, and power safety guidelines.
version: 1.0
---

# Strix Halo APU Thermal & Power Monitoring

Monitor CPU/GPU temps, power draw, and clock speeds on Bosgame M5 (Strix Halo gfx1151, 128GB unified) during inference workloads.

## Context

The Strix Halo APU can pull significant wattage under sustained GPU load. In performance BIOS mode, running large models (Qwen 122B, GLM 4.7 Flash) for 30+ minutes on a shared 16A circuit tripped a home breaker. Monitoring power draw in real-time is essential to avoid this.

## Hardware Sensor Map (hwmon)

| Sensor | hwmon | Key readings |
|--------|-------|-------------|
| k10temp (CPU) | hwmon2 | temp1_input (Tctl) |
| amdgpu (GPU) | hwmon5 | temp1_input (edge), power1_input (PPT mW), freq1_input (sclk Hz) |
| acpitz (ACPI) | hwmon0 | temp1_input |
| nvme | hwmon1 | temp1-4_input (Sensor 2 runs hot ~80C, crit 89.8C) |
| mt7925 (WiFi) | hwmon4 | temp1_input |
| r8169 (NIC) | hwmon3 | temp1_input |

**Fan control is exposed via ec-su_axb35 kernel module** at `/sys/devices/virtual/ec_su_axb35/`. Three fans with RPM, level, mode (curve/manual), and ramp curves. Also provides EC temperature and APU power mode.

## ec-su_axb35 Sensor Map

| Path | Reading | Notes |
|------|---------|-------|
| `temp1/temp` | EC temperature (°C, integer) | Min/max in `temp1/min`, `temp1/max` |
| `fan{1,2,3}/rpm` | Fan RPM (integer) | 0 = off/stopped |
| `fan{1,2,3}/level` | Fan level (integer) | 0-based |
| `fan{1,2,3}/mode` | Fan mode (string) | "curve" or "manual" |
| `fan{1,2,3}/rampup_curve` | Temp thresholds to ramp up | e.g. "60,70,80,88,95" |
| `fan{1,2,3}/rampdown_curve` | Temp thresholds to ramp down | e.g. "50,60,70,78,85" |
| `apu/power_mode` | APU power mode | "quiet" (user preference), "balanced", or "performance" |

## Tools

- `lm-sensors` package provides `sensors` command -- shows all readings formatted
- Custom monitor script at `~/llm-server/monitor.sh` -- logs CSV + live terminal output
  - Usage: `~/llm-server/monitor.sh [interval_sec] [logfile]`
  - Default: 2s interval, auto-named log with timestamp
  - Logs: timestamp, CPU C, GPU C, GPU watts, GPU MHz, NVMe temps

## Fan/heat triage: "the box is loud" with an idle GPU

When the user reports noise/heat, do NOT trust `ps` `%CPU` — it is a *lifetime
average*, so a process idle for an hour still shows the busy hour. Sample
instantaneous CPU by reading `utime+stime` from `/proc/<pid>/stat` twice ~3 s
apart and diffing (CLK_TCK = 100).

Known heat sources on this box, in order of how often they show up:

1. **The volsurface/skewbik compose stack** (`~/projects/volcalibration/skewbik`).
   Services `api`, `ingestor`, `ingestor-ws` (containers `volsurface-api`,
   `volsurface-ingestor`, `volsurface-ingestor-ws`; `volsurface-db` is the
   DB and idles on its own). The API runs a live calibration loop that
   re-fetches OKX/Deribit futures and recalibrates every ~5 s, which pegs
   postgres at 100% CPU. `docker compose stop api ingestor-ws ingestor` drops
   the APU from 98 °C to ~50 °C within 45 s. Compose **service names differ
   from container names** — `config --services` first.
2. **`openusage-telemetry.service`** (user unit, enabled at boot,
   `~/.local/bin/openusage telemetry daemon run`) burns 40-85% CPU
   continuously — the largest CPU-only heat source, and it is not inference.
3. **GPU heat is usually the bellezze Matrix agent**: it runs
   `qwen38-27b-abliterated` (config.yaml ~line 801), so every Matrix DM message
   auto-loads a router child (~20 GB weights, ~50 GiB GTT, GPU 100%). Unload
   with `POST http://127.0.0.1:8080/models/unload {"model":"<name>"}` once the
   turn is done; it reloads on the next message.

Also confirm `apu/power_mode` is `quiet` — it reads `balanced` after a reboot
(it does not persist) and that alone raises fan noise under any load.

Sensor read: for a fast check use `hwmon0`/`hwmon2` temp1_input (ACPI/k10temp)
plus `gpu_busy_percent` and `mem_info_gtt_used`; fan RPM lives under
`/sys/class/ec_su_axb35/fan{1,2,3}/rpm`.

## Power Safety Guidelines

- 16A circuit at 230V = 3,680W max total
- Strix Halo sustained full load: 120-150W+ (check with power1_input during inference)
- BIOS performance mode raises PPT limits = higher sustained draw = breaker risk on shared circuits
- Recommendation: use balanced/default BIOS mode for inference; move other devices to separate circuits for heavy workloads

## Pitfalls

- `sensors-detect` is not needed -- all sensors auto-detected via k10temp and amdgpu drivers
- `power1_input` reports microwatts (µW); divide by 1,000,000 for watts
- `freq1_input` reports Hz; divide by 1,000,000 for MHz
- NVMe Sensor 2 (temp3_input) runs ~80C at idle -- normal for this platform but watch near 89.8C crit threshold
