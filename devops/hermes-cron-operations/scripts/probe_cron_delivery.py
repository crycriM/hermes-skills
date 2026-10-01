"""Resolve one cron job's delivery target the way the tick does (read-only).

Why this exists: a job whose `deliver` is a bare platform name resolves a HOME
CHANNEL, and when that resolution fails the send is dropped with only a log
warning (`no delivery target resolved for deliver=<platform>`). Reading
`config.yaml` does not answer it — resolution goes through the job-owning
profile's secret scope (`.env`), so the check must run with that scope bound.

Run it through the Hermes shim, which injects the runtime dependency environment
before importing (a bare interpreter cannot import these modules):

    cp <this file> ~/.hermes/hermes-agent/zz_probe_cron_delivery.py
    ~/.hermes/hermes-agent/.hermes/bin/hermes --run-module zz_probe_cron_delivery <job_id>
    rm ~/.hermes/hermes-agent/zz_probe_cron_delivery.py

Call the shim path directly: the `hermes` on PATH parses `--run-module` as a CLI
command name and errors out.

Exit codes: 0 = at least one target resolved, 1 = unknown job, 2 = usage,
3 = no target (the send is being dropped).
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def _load_job(home: Path, job_id: str) -> dict | None:
    raw = json.loads((home / "cron" / "jobs.json").read_text(encoding="utf-8"))
    jobs = raw if isinstance(raw, list) else raw.get("jobs", [])
    return next((j for j in jobs if str(j.get("id")) == job_id), None)


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__.strip().splitlines()[0])
        print("usage: --run-module zz_probe_cron_delivery <job_id>")
        return 2
    job_id = argv[0]
    home = Path(os.environ.get("HERMES_HOME") or (Path.home() / ".hermes")).resolve()
    job = _load_job(home, job_id)
    if job is None:
        print(f"no job {job_id} in {home}/cron/jobs.json")
        return 1

    print(f"home         : {home}")
    print(f"job          : {job.get('name')} ({job_id})")
    print(f"deliver      : {job.get('deliver')!r}")
    print(f"origin       : {job.get('origin')}")
    print(f"workdir      : {job.get('workdir')}")
    print(f"last run     : {job.get('last_run_at')} status={job.get('last_status')}")
    print(f"last deliv.  : {job.get('last_delivery_error')!r}")

    from agent.secret_scope import (
        build_profile_secret_scope,
        reset_secret_scope,
        set_secret_scope,
    )
    from cron.scheduler_delivery import (
        _env_home_target_chat_id,
        _get_config_home_channel,
        _resolve_delivery_targets,
    )

    token = set_secret_scope(build_profile_secret_scope(home), profile_home=str(home))
    try:
        tokens = {t.strip().lower() for t in str(job.get("deliver") or "").split(",")}
        for platform in sorted(tokens - {"", "local", "origin", "all"}):
            if ":" in platform:  # explicit platform:chat_id, no home lookup involved
                continue
            print(f"  {platform}: env={_env_home_target_chat_id(platform)!r} "
                  f"config_home={_get_config_home_channel(platform)}")
        targets = _resolve_delivery_targets(job)
    finally:
        reset_secret_scope(token)

    if targets:
        print(f"targets      : {targets}")
        return 0
    print("targets      : NONE — this fire would deliver nothing (log warning only,"
          " run status stays ok)")
    return 3


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
