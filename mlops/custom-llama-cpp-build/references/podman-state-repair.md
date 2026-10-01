# Podman/Distrobox state repair after OOM-killed container

## Symptom

After a distrobox container is OOM-killed or left in a stale state, every podman command fails with:

```
invalid internal status, try resetting the pause process with "podman system migrate": could not find any running process
```

`podman system migrate` is the error's own suggestion but it PANICS with a nil-pointer in `UnmountContainerImage` when a stale `ContainerState` row still claims a `mountPoint` that no longer exists. So the suggested command is unusable here.

## Diagnose (read-only)

The podman state is a sqlite DB at `~/.local/share/containers/storage/db.sql`. The `ContainerState` table holds JSON with `state`, `mounted`, `oomKilled`, `pid`, `conmonPid`, `mountPoint`. A row that is `state=3` (running) + `mounted=true` + dead PIDs + `oomKilled=true` is the culprit.

```bash
sqlite3 ~/.local/share/containers/storage/db.sql \
  "SELECT ID, json_extract(JSON,'$.state'), json_extract(JSON,'$.mounted'), json_extract(JSON,'$.oomKilled'), json_extract(JSON,'$.pid') FROM ContainerState;"
ps -p <pid> 2>&1   # dead = stale row
```

Note: `distrobox list` and `podman ps` return EMPTY when podman state is broken — that does NOT prove no containers exist. Query the DB to see the real container inventory.

## Fix (patch the DB, back up first)

```bash
cp ~/.local/share/containers/storage/db.sql ~/.local/share/containers/storage/db.sql.bak-$(date +%s)
```

```python
import sqlite3, json
db = sqlite3.connect("<expanded>/db.sql")
for cid in ["<container-id>", ...]:  # only rows whose PID is confirmed dead
    row = db.execute("SELECT JSON FROM ContainerState WHERE ID=?", (cid,)).fetchone()
    st = json.loads(row[0])
    st["state"] = 6   # stopped/exited
    st["mounted"] = False
    st.pop("pid", None); st.pop("conmonPid", None); st.pop("mountPoint", None)
    db.execute("UPDATE ContainerState SET JSON=?, State=6 WHERE ID=?", (json.dumps(st), cid))
db.commit()
```

Only patch rows whose PIDs are verified dead — a live container must never be touched this way.

## Prevention

Containers started from Hermes background terminals or cron run in systemd scopes with hard `MemoryMax 4GiB` — big model loads OOM-kill the scope and leave this exact stale state. Start large llama-servers via systemd user services or real foreground terminals, not agent-owned background procs.

After the DB is repaired, creating a replacement toolbox uses the `TOOLBOXES` dict in `~/sources/amd-strix-halo-toolboxes/refresh-toolboxes.sh` (exact image ref + device flags). See `references/strix-halo-toolbox-tags.md` for which tag to choose.
