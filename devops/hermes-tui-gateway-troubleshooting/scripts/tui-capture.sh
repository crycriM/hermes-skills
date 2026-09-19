#!/usr/bin/env bash
# Capture a full `hermes --tui` launch into a typescript so flash-and-exit
# errors are preserved instead of vanishing from the screen.
# Usage: run this the same way you normally launch the TUI; result in
# ~/.hermes/logs/tui-user-capture.log
set -u
LOG=~/.hermes/logs/tui-user-capture.log
rm -f "$LOG"
echo "Recording TUI launch... output saved to $LOG (will also print below on exit)."
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