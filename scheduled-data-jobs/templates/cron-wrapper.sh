#!/bin/bash
# Hardened Hermes no_agent cron wrapper — copy and modify.
# Cron env has a stripped PATH (no ~/.local/bin) and does NOT load project .env.
# set -o pipefail is mandatory when the script ends in a pipe, or the pipe's
# exit code (tail's 0) masks real failures and the job reports status ok.
set -e -o pipefail
export PATH="/home/USER/.local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
cd /ABS/PATH/to/project || exit 1
set -a; source /ABS/PATH/to/project/.env; set +a
UV="/home/USER/.local/bin/uv"

# Step 1 — extend / refresh primary data
echo "=== step 1 start $(date '+%F %T') ==="
"$UV" run python3 scripts/update_primary.py

# Step 2 — enrichment that only UPDATEs existing rows must run AFTER the refresh
echo "=== step 2 start $(date '+%F %T') ==="
"$UV" run python3 scripts/enrich.py

echo "=== done $(date '+%F %T') ==="
