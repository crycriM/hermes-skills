---
name: tailscale-ingress
description: "Tailnet ingress and client connect failures (serve/funnel)."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [tailscale, networking, ingress, tls, magicdns, serve, funnel]
    related_skills: [devops, hermes-messaging-platforms, docker-open-webui-deploy]
---

# Tailnet ingress: publishing a service, and diagnosing clients that cannot reach it

## When to Use

- A local service must be reachable from other devices over the tailnet (`tailscale serve`,
  `tailscale funnel`), or is already published and its exposure needs review.
- A user reports "I can't connect" from an app while the service itself looks healthy.
- A `.ts.net` / MagicDNS name fails to resolve or connect on one device but works elsewhere.

Most of this class is about telling "the service is broken" apart from "the client never got
there" — the two look identical from the user's side and have nothing in common.

## Recipe

1. Bind the service to loopback only, then publish it through the tailnet:
   `tailscale serve --bg --https=443 http://127.0.0.1:<port>` (tailnet-only) or
   `tailscale funnel --bg --https=443 http://127.0.0.1:<port>` (public).
2. Read back what is published: `tailscale serve status` (`--json` for the handler map).
3. Confirm the preconditions: the node needs the `https` capability (`tailscale debug netmap` →
   `CapMap`) and HTTPS enabled for the tailnet. A missing tailnet-side setting shows up later as a
   certificate that never issues, not as a serve error.
4. Check the certificate the ingress presents:
   `openssl s_client -connect <name>:443 -servername <name> </dev/null | openssl x509 -noout -subject -dates -ext subjectAltName`.
   It is a Let's Encrypt cert for the **MagicDNS name** and for nothing else.
5. Hand clients the MagicDNS name **with the scheme**: `https://<host>.<tailnet>.ts.net`.

## Hard rules (each is a mechanism, not a guess)

- **`tailscale serve` routes by SNI, so a client can never reach it by IP.** An IP-based client
  produces `http: TLS handshake error from <client ip>: no SNI ServerName` in the tailscaled
  journal and a certificate or connection error in the app. That log line *is* the diagnosis: the
  client dialed the IP instead of the name.
- **A local curl through the tailnet URL proves nothing about remote clients.** MagicDNS names are
  answered by tailscaled from its own netmap, and traffic to the node's own tailnet IP never leaves
  the host. Verify from a second device, or from the tailscaled log of the client's own attempt.
- **The `ts.net` zone is public.** The coordination server hands clients a split-DNS route for the
  whole `ts.net.` zone pointing at Tailscale's public nameservers, and those answer `NXDOMAIN`
  *authoritatively* for node names with no public record (everything except Funnel-published
  nodes). Check with `dig +short @1.1.1.1 ts.net NS` (the zone is delegated) and
  `dig @<the split-route resolver> <node>.ts.net`.
- **A client returning `NXDOMAIN` / `DNS_PROBE_FINISHED_NXDOMAIN` for a `.ts.net` name is not using
  Tailscale for DNS.** That is device-side state, not a server fault — and the host resolving the
  same name fine is expected, for the reason in the rule above.
- **`tailscale ping <peer>` proves the tunnel, never the service.** It talks to the peer's
  tailscaled and succeeds while DNS, ACL-filtered traffic, or the published service are broken.
  Read it as "tunnel up", nothing more — it will happily pong while every real connection fails.
- **Clients differ on TLS.** Modern Matrix clients (Element X) and most native apps require https
  with a certificate matching the hostname, so an IP URL can never work for them. Clients that
  tolerate plain http (Element classic, FluffyChat, Cinny, a browser) can talk to a service bound
  on the tailnet IP over http.

## Diagnostic ladder for "can't connect from the app"

Name the failure before chasing it: ask for the exact client-side error, and offer the candidates as
picks rather than a free-text question — `ERR_CONNECTION_TIMED_OUT`, `DNS_PROBE_FINISHED_NXDOMAIN` /
`ERR_NAME_NOT_RESOLVED`, and a certificate warning point at transport, name resolution, and TLS
respectively. "Can't connect" or "timeout" alone cannot distinguish them, and each has a different
fix.

1. Service alive on loopback: `curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:<port>/<known-path>`.
2. Ingress published and cert valid: `tailscale serve status`, then the `openssl s_client` check.
3. **Did the client's traffic arrive at all?** Start a watcher **before** the user retries, then
   read it:
   `journalctl -u tailscaled -f --no-pager -o short-iso | grep --line-buffered -E '<client tailnet ip>|handshake'`.
   No lines = the name never resolved on that device (a DNS problem, step 6);
   `no SNI ServerName` = it dialed the IP; a clean handshake = transport is fine, read the
   service's own logs next. The attempt leaves no packet behind, so a watcher started afterwards
   sees nothing and proves nothing.
4. Peer state and path: `tailscale status --json` (`Online`, `Relay`, `CurAddr`), `tailscale ping <peer>`.
5. The name→IP the client is *supposed* to get: `tailscale dns status` (read its `Split DNS Routes`
   before blaming the device), `tailscale dns query <name>`, `getent hosts <name>`.
6. Device-side state the user must fix: VPN actually connected; "Use Tailscale DNS settings" ON in
   the app **then reconnect the VPN** (the DNS config only applies on reconnect); Android "Private
   DNS" Off/Automatic (a strict hostname overrides the VPN resolver and breaks exactly this while
   the tunnel keeps working); vendor power managers (EMUI/Huawei/Xiaomi) killing the VPN in the
   background.

## When a device will not resolve MagicDNS — options and their costs

Present these as choices; none is a default, and each changes something the user cares about.

- **Admin console → DNS → "Override local DNS".** Add a global nameserver (e.g. 1.1.1.1) *first*:
  with no global nameservers, override leaves public names with no upstream and breaks ordinary
  browsing on every device. Then reconnect the VPN on the device. Cost: DNS for the whole tailnet
  goes through Tailscale, so a local resolver or filtering setup stops being used.
- **Funnel.** Publishes the name into the public `ts.net` zone with the already-valid certificate,
  so the client's own DNS resolves it and MagicDNS, Tailscale, and vendor power management drop out
  of the picture entirely. Cost: the service becomes reachable from the internet — harden it first
  (disable self-registration, confirm only credential-gated endpoints answer) and state the
  exposure plainly before enabling.
- **http-tolerant client + service bound on the tailnet IP.** No DNS lookup, no certificate, no new
  exposure; costs a different app on that device.

## Pitfalls

- **Sweep the port before binding it.** A service on `0.0.0.0:<port>` blocks a later
  `127.0.0.1:<port>` bind (plain `SO_REUSEADDR` does not bridge wildcard vs. specific): the other
  tool dies with "address already in use" and any client aimed at that port silently reaches the
  wrong service. Grep live scripts and units for the candidate port before committing; this host's
  port map and folder-serving recipe live in the user-owned `devops` skill.
- **Attribute sockets before concluding anything.** The host-side halves of a Docker port publish
  belong to root/`docker-proxy` and are invisible to `ss -p`, and a service that dials a hostname
  on demand may hold no socket between polls. Prove a live connection by intersecting the target
  process's `/proc/<pid>/fd` socket inodes with `/proc/net/tcp` (and expect the client's socket on
  the published port, e.g. `:443`, not on the port the service binds).
- **Do not close this out as "server is fine" while the client still cannot connect.** Verified
  server-side health plus a working local curl is only half the answer; the deliverable is the
  client reaching it, or a named next action on the device.
