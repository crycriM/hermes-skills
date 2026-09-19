#!/usr/bin/env bash
# Capture a full `hermes --tui` launch into a typescript so flash-and-exit
# errors are preserved instead of vanishing from the screen.
set -u
LOG=~/.hermes/logs/tui-user-capture.log
rm -f "$LOG"

echo "Recording TUI launch... saved to $LOG"
echo ""
echo "IMPORTANT — how to exit:"
echo "  * Inside the TUI: press Ctrl+C once when the prompt is idle (or type /quit)"
echo "  * Recording auto-stops 120s after launch either way"
echo "  * DO NOT press Ctrl+Z (freezes the recorder)"
echo "  * If stuck anyway: kill it from another terminal with:"
echo "      pkill -f tui-capture.sh; pkill -f 'timeout 120 script'"
echo ""

cleanup() {
  # Restore terminal sanity if we get killed mid-session
  stty sane 2>/dev/null || true
}
trap cleanup EXIT INT TERM

timeout 120 script -qec "hermes --tui" "$LOG"
RC=$?

echo "--- exit code: $RC ---"
echo "--- readable tail (errors usually near the end) ---"
python3 - "$LOG" <<'EOF'
import re, sys
data = open(sys.argv[1], 'rb').read().decode('utf-8', 'replace')
for pat in (r'\x1b\[[0-9;?]*[a-zA-Z]', r'\x1b\][^\x07]*\x07', r'\x1b[()][0-9A-Za-z]'):
    data = re.sub(pat, '', data)
lines = [l.rstrip() for l in data.replace('\r', '\n').split('\n') if l.strip()]
seen = []
for l in lines:
    if not seen or seen[-1] != l:
        seen.append(l)
print('\n'.join(seen[-70:]))
EOF