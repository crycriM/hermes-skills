#!/usr/bin/env bash
# ComfyUI health probe: service state, readiness, GPU device, custom-node pack health.
# Usage: verify-comfyui.sh [unit-name] [base-url] [log-path]
set -uo pipefail

UNIT="${1:-comfyui.service}"
BASE="${2:-http://127.0.0.1:8188}"
LOG="${3:-$HOME/.local/share/comfyui/comfyui.log}"

fail=0
say() { printf '%-28s %s\n' "$1" "$2"; }

state=$(systemctl --user is-active "$UNIT" 2>/dev/null)
say "service ($UNIT)" "$state"
[ "$state" = "active" ] || fail=1
say "enabled" "$(systemctl --user is-enabled "$UNIT" 2>/dev/null)"

# memory cap: must NOT be capped, or model loads get OOM-killed
say "MemoryMax" "$(systemctl --user show "$UNIT" -p MemoryMax --value 2>/dev/null)"

# readiness: bounded poll, no blind sleep
code=""
for _ in $(seq 1 40); do
  code=$(curl -s -o /dev/null -w '%{http_code}' -m 3 "$BASE/system_stats" || true)
  [ "$code" = "200" ] && break
  sleep 1
done
say "GET /system_stats" "${code:-no-response}"
[ "$code" = "200" ] || fail=1
say "GET /" "$(curl -s -o /dev/null -w '%{http_code}' -m 10 "$BASE/")"

# device: GPU offload must be real, not CPU fallback
curl -s -m 20 "$BASE/system_stats" | python3 -c '
import json,sys
try:
    d=json.load(sys.stdin)
except Exception as e:
    print("  (could not parse system_stats)", e); raise SystemExit
dev=d["devices"][0]
print("  device      :", dev["name"])
print("  vram_total  :", round(dev["vram_total"]/1024**2), "MiB")
print("  torch       :", d["system"]["pytorch_version"])
print("  python      :", d["system"]["python_version"].split()[0])
' 2>/dev/null

# listener
say "listening (8188)" "$(ss -ltn 2>/dev/null | awk '{print $4}' | grep -c ':8188$')"

# custom node packs
curl -s -m 30 "$BASE/object_info" | python3 -c '
import json,sys
d=json.load(sys.stdin)
print("  nodes registered:", len(d))
print("  GGUF loaders    :", [k for k in d if "GGUF" in k])
' 2>/dev/null

# log health: dead packs and the wrapper actually chosen for the last text encoder load
echo "--- log ---"
if [ -r "$LOG" ]; then
  grep -c "IMPORT FAILED" "$LOG" | awk '{print "  IMPORT FAILED lines (cumulative): "$1}'
  grep -E "Device: |AMD arch|Requested to load|To see the GUI" "$LOG" | tail -6 | sed 's/^/  /'
  echo "  (any 'Requested to load' class that is not the one you expect means detection picked a different wrapper)"
else
  echo "  log not readable: $LOG"
  fail=1
fi

exit $fail
