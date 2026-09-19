# Docker-based Packet Capture (No Sudo Required)

When `sudo tcpdump` fails (no terminal, no NOPASSWD sudoers entry), Docker with host networking and raw socket capabilities provides a reliable workaround — as long as the user is in the `docker` group.

## Prerequisites

- User must be in `docker` group: `groups | grep docker`
- Docker daemon must be running
- Target network interface must be known: `ip link show`

## One-shot capture (foreground, count-limited)

```bash
docker run --rm --net=host --cap-add=NET_RAW --cap-add=NET_ADMIN \
  -v /tmp:/tmp alpine:latest sh -c \
  'apk add -q tcpdump 2>/dev/null; tcpdump -i <IFACE> -c <COUNT> -nn <FILTER>'
```

Example — capture 100 packets to/from a specific host:
```bash
docker run --rm --net=host --cap-add=NET_RAW --cap-add=NET_ADMIN \
  -v /tmp:/tmp alpine:latest sh -c \
  'apk add -q tcpdump 2>/dev/null; tcpdump -i eno1 -c 100 -nn host [REDACTED]'
```

## Long-running capture (background, file output)

```bash
docker run --rm --net=host --cap-add=NET_RAW --cap-add=NET_ADMIN \
  -v /tmp:/tmp alpine:latest sh -c \
  'apk add -q tcpdump 2>/dev/null; tcpdump -i eno1 -w /tmp/capture.pcap -s 0 <FILTER>'
```

The `-v /tmp:/tmp` bind mount shares the pcap file with the host. Kill with `docker stop <container>` or Ctrl-C.

## Analysis (read pcap without capture permissions)

```bash
docker run --rm --net=host -v /tmp:/tmp alpine:latest sh -c \
  'apk add -q tcpdump 2>/dev/null; tcpdump -r /tmp/capture.pcap -nn -A'
```

Reading a pcap file does NOT require `--cap-add=NET_RAW` — only capture does.

## Key Flags

| Flag | Purpose |
|------|---------|
| `--net=host` | Use host network stack (see host interfaces) |
| `--cap-add=NET_RAW` | Allow raw socket creation (packet capture) |
| `--cap-add=NET_ADMIN` | Allow promiscuous mode (optional, often needed) |
| `-v /tmp:/tmp` | Share output files between container and host |
| `-s 0` | Full packet capture (no truncation) |
| `-w file` | Write to pcap file instead of stdout |
| `-nn` | Don't resolve hostnames or port names |

## Pitfalls

1. **0 packets captured but filter seems right.** The interface name inside the container must match the host. With `--net=host`, it does — but verify with `ip link show` inside the container.

2. **24-byte pcap file (header only).** No packets matched the filter during the capture window. Try without a filter first: `tcpdump -i eno1 -c 10 -nn` to verify capture works.

3. **"Operation not permitted" even with --cap-add.** Some Docker installations (rootless Docker, some CI environments) restrict capabilities further. Check `docker info | grep -i security` for seccomp/AppArmor profiles.

4. **Container exits immediately.** Alpine needs `apk add -q tcpdump` first — the image doesn't include it. Use `sh -c 'apk add ...; tcpdump ...'` as a single command.
