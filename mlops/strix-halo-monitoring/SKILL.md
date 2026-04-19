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
| `apu/power_mode` | APU power mode | "balanced" or "performance" |

## Tools

- `lm-sensors` package provides `sensors` command -- shows all readings formatted
- Custom monitor script at `~/llm-server/monitor.sh` -- logs CSV + live terminal output
  - Usage: `~/llm-server/monitor.sh [interval_sec] [logfile]`
  - Default: 2s interval, auto-named log with timestamp
  - Logs: timestamp, CPU C, GPU C, GPU watts, GPU MHz, NVMe temps

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
