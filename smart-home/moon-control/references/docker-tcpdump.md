# No-sudo Packet Capture via Docker

When `sudo tcpdump` requires a terminal (no passwordless sudo), use Docker
with host networking and NET_RAW capability.

## Prerequisites

User must be in the `docker` group:
```bash
groups | grep docker
```

## Capture commands

**One-shot (capture N packets, exit):**
```bash
docker run --rm --net=host --cap-add=NET_RAW --cap-add=NET_ADMIN \
  -v /tmp:/tmp alpine:latest sh -c \
  'apk add -q tcpdump 2>/dev/null; tcpdump -i eno1 -c 500 -w /tmp/capture.pcap host 192.168.0.172'
```

**Background (long-running):**
```bash
docker run --rm --net=host --cap-add=NET_RAW --cap-add=NET_ADMIN \
  -v /tmp:/tmp alpine:latest sh -c \
  'apk add -q tcpdump 2>/dev/null; tcpdump -i eno1 -w /tmp/capture.pcap -s 0 host 192.168.0.172'
```

**Read captured pcap:**
```bash
docker run --rm --net=host -v /tmp:/tmp alpine:latest sh -c \
  'apk add -q tcpdump 2>/dev/null; tcpdump -r /tmp/capture.pcap -nn'
```

## Pitfalls

1. **Interface name** — varies by system. Common: `eno1`, `eth0`, `wlp195s0`. Check with `ip link show`.
2. **`--net=host` required** — without it, the container has its own network namespace and can't see host traffic.
3. **`-v /tmp:/tmp`** — needed to persist pcap files outside the container (they disappear with `--rm`).
4. **First run is slow** — alpine downloads and installs tcpdump each time. For repeated use, build a custom image with tcpdump pre-installed.
5. **Docker bridge interfaces** — they show up in `ip link` as `br-*` and `docker0`. Ignore them; capture on the physical interface.

## Why this works

The Docker daemon runs as root and can grant `CAP_NET_RAW` to containers.
The user only needs `docker` group membership (no sudo for docker commands).
Unlike `sudo tcpdump`, Docker doesn't need a terminal for authentication.
