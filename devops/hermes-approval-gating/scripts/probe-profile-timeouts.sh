#!/usr/bin/env bash
# Report the user-interaction waits a Hermes PROFILE actually resolves at runtime.
#
#   bash scripts/probe-profile-timeouts.sh <profile>
#
# Prints the profile's approvals block plus the resolved approval / clarify windows through the SAME
# readers the gateway uses (tools.approval_context._get_approval_timeout,
# tools.clarify_gateway.get_clarify_timeout). Mode normalization and the approval clamp are therefore
# visible here, whereas `hermes config get` only echoes the YAML file.
#
# Override the source tree with HERMES_SRC if Hermes is not installed at ~/.hermes/hermes-agent.
set -euo pipefail

PROFILE="${1:?usage: probe-profile-timeouts.sh <profile>}"
SRC="${HERMES_SRC:-$HOME/.hermes/hermes-agent}"
PROFILE_HOME="$HOME/.hermes/profiles/$PROFILE"

[ -d "$PROFILE_HOME" ] || { echo "no profile home: $PROFILE_HOME" >&2; exit 1; }
[ -d "$SRC" ] || { echo "no Hermes source tree: $SRC (set HERMES_SRC)" >&2; exit 1; }

PY=""
for cand in "$SRC/venv/bin/python" "$SRC/.venv/bin/python"; do
  if [ -x "$cand" ]; then PY="$cand"; break; fi
done
[ -n "$PY" ] || { echo "no venv python under $SRC" >&2; exit 1; }

cd "$SRC"
HERMES_HOME="$PROFILE_HOME" "$PY" - <<'PY'
from hermes_cli.config import load_config_readonly
from tools.approval_context import _get_approval_timeout, format_approval_window
from tools.clarify_gateway import get_clarify_timeout


def describe(seconds):
    """<=0 is meaningful only for clarify (unlimited); print it instead of a bogus window."""
    return "unlimited" if seconds <= 0 else f"{seconds}s = {format_approval_window(seconds)}"


cfg = load_config_readonly()
approvals = cfg.get("approvals") or {}
print("approvals block :", approvals)
print("approval window :", describe(_get_approval_timeout()))
print("clarify window  :", describe(get_clarify_timeout()))
print("mode gates      :", {k: approvals.get(k)
                           for k in ("cron_mode", "single_query_mode", "unattended_mode")})
PY
