# System Service Discovery

Discover what's listening on which port, how it was started, and which systemd unit or Docker compose owns it.

## 1. List listening ports with processes

```bash
ss -tlnp4
```

Columns: `Local Address:Port`, `Peer`, `Process`. The process column shows `("name",pid=NNNN,fd=N)`.

- `-t` = TCP, `-l` = listening, `-n` = numeric, `-p` = show process, `-4` = IPv4 only
- Add `-u` for UDP: `ss -ulnp4`
- Drop `-4` to see IPv6 too: `ss -tlnp`

For a compact table:

```bash
ss -tlnp4 2>/dev/null | awk 'NR==1{printf "%-22s %-6s %s\n","ADDRESS","PORT","PROCESS"} NR>1{port=substr($4,index($4,":")+1); cmd=""; for(i=5;i<=NF;i++) cmd=cmd $i " "; sub(/users:\(/,"",cmd); sub(/\)/,"",cmd); printf "%-22s %-6s %s\n",$4,port,cmd}'
```

## 2. Get the exact command line from a PID

`/proc/PID/cmdline` uses null bytes (`\0`) as argument delimiters — so `cat` shows a mashed-together string. Use `tr` to replace nulls with spaces:

```bash
cat /proc/PID/cmdline | tr '\0' ' '
```

This reveals the full `argv` including flags, config paths, working dir arguments — not just the process name that `ps` or `ss` truncates to.

## 3. Map to systemd units

System services:

```bash
systemctl list-units --type=service --state=running --no-pager
```

User services:

```bash
systemctl --user list-units --type=service --state=running --no-pager
```

Cross-reference the PID from `ss` output against the `MainPID` of a unit:

```bash
systemctl show -p MainPID <unit-name>
```

Or grep journal for the PID:

```bash
journalctl _PID=NNNN --no-pager -n 5
```

## 4. Map to Docker containers

```bash
# All running containers with ports
docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Ports}}'

# Search by port
docker ps --format '{{.Names}} {{.Ports}}' | grep ':9090'

# Inspect a container's config (command, mounts, env)
docker inspect <container-name> --format '{{json .Config.Cmd}}'
docker inspect <container-name> --format '{{json .Mounts}}'

# Find its compose file origin: look in ~/ for docker-compose.yml files
find ~ -maxdepth 3 -name 'docker-compose*' -not -path '*/node_modules/*'
```

The container name pattern is `<project>_<service>_<N>` (e.g. `rankit_timescaledb_1`). The project dir usually has the `docker-compose.yml`.

## 5. nginx reverse-proxy routing

nginx may front multiple services on one SSL port via sub-path routing. Check:

```bash
# Enabled sites
ls /etc/nginx/sites-enabled/

# Full config with routing rules
cat /etc/nginx/sites-enabled/<site>

# Grep for backend destinations
grep 'proxy_pass\|root' /etc/nginx/sites-enabled/*
```

## 6. Unknown processes (no systemd, no Docker)

If a PID isn't in systemd or Docker, check:

```bash
# Parent PID
ps -p PID -o ppid,comm --no-headers

# Working directory (the dir the process was launched from)
readlink /proc/PID/cwd

# Environment — look for PWD, VIRTUAL_ENV, etc.
cat /proc/PID/environ | tr '\0' '\n' | grep -E '^PWD=|^VIRTUAL_ENV=|^HOME='
```

## 7. Outputting findings

When documenting a port map, separate by function:

- **Inference layer** (llama.cpp router + slots, model manager)
- **Agent layer** (Hermes gateway, web UI)
- **Data layer** (RAG, PostgreSQL, Redis)
- **Media layer** (STT/Whisper)
- **App layer** (task managers, dashboards, static sites)
- **Infra** (nginx, SSH, DNS, Tailscale)

Each entry: port, bind address, process name + full argv, systemd unit (or Docker/compose source), purpose.

## Pitfalls

- `/proc/PID/cmdline` uses null delimiters — always pipe through `tr '\0' ' '`. Just `cat`-ing it looks like one smashed word.
- Python argparse/long flags may be split across null-delimited fields — `tr '\0' ' '` reassembles them correctly.
- `ss -p` requires root or `CAP_NET_ADMIN` to see process names for other users' sockets. As the owning user, you see your own processes fine.
- Docker container names with `_1` suffix can differ from the `docker-compose.yml` service name — check via `docker inspect` rather than assuming.
- nginx may have listen directives in `conf.d/` as well as `sites-enabled/` — check both.
- `systemctl --user` services are per-user and only show when you're that user. Run as the owning user.
