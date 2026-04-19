#!/bin/bash
# M5 Thermal & Power Monitor
# Usage: ./monitor.sh [interval_seconds] [log_file]
# Defaults: 2 seconds, ~/llm-server/monitor-<timestamp>.log

INTERVAL="${1:-2}"
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
LOGFILE="${2:-$HOME/llm-server/monitor-${TIMESTAMP}.log}"

# Paths
CPU_TEMP="/sys/class/hwmon/hwmon2/temp1_input"
GPU_TEMP="/sys/class/hwmon/hwmon5/temp1_input"
GPU_POWER="/sys/class/hwmon/hwmon5/power1_input"
GPU_SCLK="/sys/class/hwmon/hwmon5/freq1_input"
NVME1="/sys/class/hwmon/hwmon1/temp1_input"
NVME2="/sys/class/hwmon/hwmon1/temp2_input"
NVME3="/sys/class/hwmon/hwmon1/temp3_input"
WIFI="/sys/class/hwmon/hwmon4/temp1_input"

echo "M5 Monitor - logging to $LOGFILE every ${INTERVAL}s (Ctrl+C to stop)"
echo "timestamp,cpu_c,gpu_c,gpu_w,gpu_mhz,nvme1_c,nvme2_c,nvme3_c,wifi_c" > "$LOGFILE"

trap "echo ''; echo 'Stopped. Log: $LOGFILE'; exit 0" INT TERM

while true; do
    ts=$(date +%H:%M:%S)
    cpu=$(cat "$CPU_TEMP" 2>/dev/null || echo "N/A")
    gpu=$(cat "$GPU_TEMP" 2>/dev/null || echo "N/A")
    pwr=$(cat "$GPU_POWER" 2>/dev/null || echo "N/A")
    clk=$(cat "$GPU_SCLK" 2>/dev/null || echo "N/A")
    n1=$(cat "$NVME1" 2>/dev/null || echo "N/A")
    n2=$(cat "$NVME2" 2>/dev/null || echo "N/A")
    n3=$(cat "$NVME3" 2>/dev/null || echo "N/A")
    wf=$(cat "$WIFI" 2>/dev/null || echo "N/A")

    # Convert millidegrees to degrees, milliwatts to watts
    [ "$cpu" != "N/A" ] && cpu_d=$(echo "scale=1; $cpu/1000" | bc) || cpu_d="N/A"
    [ "$gpu" != "N/A" ] && gpu_d=$(echo "scale=1; $gpu/1000" | bc) || gpu_d="N/A"
    [ "$pwr" != "N/A" ] && pwr_d=$(echo "scale=1; $pwr/1000000" | bc) || pwr_d="N/A"
    [ "$clk" != "N/A" ] && clk_d=$(echo "scale=0; $clk/1000000" | bc) || clk_d="N/A"
    [ "$n1" != "N/A" ] && n1_d=$(echo "scale=1; $n1/1000" | bc) || n1_d="N/A"
    [ "$n2" != "N/A" ] && n2_d=$(echo "scale=1; $n2/1000" | bc) || n2_d="N/A"
    [ "$n3" != "N/A" ] && n3_d=$(echo "scale=1; $n3/1000" | bc) || n3_d="N/A"
    [ "$wf" != "N/A" ] && wf_d=$(echo "scale=1; $wf/1000" | bc) || wf_d="N/A"

    line="$ts,$cpu_d,$gpu_d,$pwr_d,$clk_d,$n1_d,$n2_d,$n3_d,$wf_d"
    echo "$line" >> "$LOGFILE"
    printf "%s  CPU:%5.1fC  GPU:%5.1fC  PPT:%6.1fW  CLK:%4sMHz  NVMe:%5.1f/%5.1f/%5.1fC\n" \
        "$ts" "$cpu_d" "$gpu_d" "$pwr_d" "$clk_d" "$n1_d" "$n2_d" "$n3_d"
    sleep "$INTERVAL"
done
