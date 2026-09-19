---
category: devops
name: home-network-lan-wifi
description: Use when scanning/joining wifi or fixing home LAN routing.
---

# Home Network LAN & Wifi Troubleshooting

Use when the user asks to scan/join wifi, troubleshoot connectivity ("no internet", "IP config unavailable"), or configure the home OpenWrt LuCI router / ISP box routing, subnets, or DHCP.

## Environment (this user's LAN — verify live before acting; don't trust stale state)
- ISP box (also hands out the 192.168.0.0/24 subnet): gateway **[REDACTED]**, MAC **[REDACTED]**, broadcasts SSID **[REDACTED]**. This is the box the machine normally routes through.
- OpenWrt LuCI router (the user's separate router): ssh `root@fe80::5aef:68ff:fe0e:1816%eno1`, LuCI admin at `https://[fd80:6964:93f9::1]` (both over eno1, link-local/ULA scope `%eno1`). LAN = br-lan (lan1–4) `192.168.1.1/24 static + IPv4 DHCP on` (.100–.249); WAN = `dhcp`. SSID cricri3 (WPA3/SAE) on both radios (radio0 5g→phy0-ap0, radio1 2g→phy1-ap0). **`192.168.0.1` is a DIFFERENT AP** (MAC c0:3f:0e:a5:48:40, SSID "cricri") — NOT this router, despite being on the same L2. Confirm device identity via BSSID MAC + ARP, never by IP guesswork.
- Multiple SSIDs in range: cricri / cricri2 (WPA2), cricri3 (WPA3, dual-radio: 2.4GHz + 5/6GHz). Not all belong to the same device — check BSSID OUIs before assuming which radio/router an SSID comes from.
- Machine: eno1 (ethernet, the primary/default route, netplan-managed profile `netplan-eno1`) + wlp195s0 (wifi).

## nmcli wifi scan & connect — core workflow
1. A plain `nmcli device wifi list` often returns **stale NetworkManager-cached results** (may show only one AP). Force a fresh scan, but NOTE:
   **`nmcli device wifi rescan`, `nmcli device wifi connect <SSID>`, and `nmcli connection add` all require polkit authorization the agent's process does NOT have** ("not authorized" / "Insufficient privileges"). The user must run these in their own interactive shell (nobody adds/changes NM configs from the agent session). This is a stable platform limitation, not a transient error — do not retry in a loop; hand the user the exact command block.
2. First real scan (user's shell):
   ```
   nmcli device wifi rescan && nmcli device wifi list
   ```
   `rescan` alone is a separate step; connecting before a rescan yields "No network with SSID 'X' found" even when the AP is physically there.
3. Connect by password:
   ```
   nmcli device wifi connect <SSID> password '<psk>'
   ```
   This triggers its own association scan and is the cleanest one-shot path.

## WPA2 vs WPA3 — key-mgmt matters
- **WPA2** APs → `wifi-sec.key-mgmt wpa-psk`.
- **WPA3** APs (SAE) → MUST be `wifi-sec.key-mgmt sae`, or the client can't authenticate.
- When building a profile explicitly (or if `device wifi connect` fails because the AP isn't in NM's cache):
  ```
  nmcli connection add type wifi con-name <name> ssid <ssid> \
      wifi-sec.key-mgmt sae wifi-sec.psk '<psk>' \
      ipv4.route-metric 1000 ipv6.route-metric 1000
  nmcli connection up <name>
  ```
  Use `wpa-psk` instead of `sae` for WPA2 APs.
- **Duplicate-profile hazard**: repeated `connection add` creates multiple profiles with the same `connection.id` but different UUIDs (one wpa-psk, one sae). `nmcli connection show` lists both; ambiguous which gets picked. Delete the wrong variant before up-ing.

## Preempting ethernet — the user's recurring concern
- Want wifi to join WITHOUT hijacking the default route from eno1 (netplan ethernet profile `netplan-eno1`, metric 100). NM's default route-metric is 100 for ethernet and 600 for wifi, so wired already wins the tie — but make it explicit and durable by pinning the wifi profile's `ipv4.route-metric`/`ipv6.route-metric` to a high value (e.g. 1000). eno1's own profile is untouched; it stays primary.
- Wifi↔wifi autoconnect switching (NM dropping a hung cricri3 for trusted cricri2) is NORMAL and has nothing to do with eno1 — don't misattribute it.
- Common symptom "activating but stuck at getting IP configuration": association succeeded (AP shows 100% signal, it's the IN-USE AP) but DHCP is not answering. Watch `journalctl -u NetworkManager -n 40 | grep -iE 'dhcp|activat|state change'`. NM may then silently fall back to another trusted profile — check `nmcli device status` for which SSID actually won.

## OpenWrt LuCI router — DHCP / double-NAT
Can the router run its own DHCP (own LAN subnet) alongside the ISP box DHCP? **Yes — that's standard double NAT.** Hard rule: the router's LAN subnet MUST NOT overlap the ISP box subnet (192.168.0.0/24). Give the router e.g. 192.168.1.1/24.

Why wifi clients fail even with correct password ("no internet" on Windows, "IP configuration not available" on Linux). **CONFIRMED root cause on cricri3 (2026-08-26): the wifi APs were not bridged into lan** — the wifi-iface blocks lacked `option network 'lan'`, so phy0-ap0/phy1-ap0 were UP but OUTSIDE br-lan. Clients associated (SAE OK, 100% signal) but their DHCP broadcasts never reached dnsmasq (bound to br-lan) → no IPv4 lease. This is the MOST likely cause when association works and DHCP times out with an otherwise-correct router config. Diagnose on the router:
```
ls /sys/class/net/br-lan/brif              # expect the phy-* APs listed
readlink /sys/class/net/phy0-ap0/master    # must resolve to br-lan, not NONE
uci show wireless                          # wifi-iface blocks should each have network='lan'
```
Fix (each wifi-iface for the SSID must get network='lan'):
```
uci set wireless.wifinet1.network=lan
uci set wireless.wifinet2.network=lan
uci commit wireless && wifi reload
# verify: `ls /sys/class/net/br-lan/brif` now shows the phy-* APs, and each master == br-lan
```
Other causes, in order:
1. **Wifi radio/wifi-iface not in network "lan"** — see above (silent, common).
2. **LAN subnet overlap** — router LAN on the same 192.168.0.0/24 as the ISP box AND its WAN DHCP-requests from that same subnet = overlap + no NAT. Fix: LAN to a disjoint subnet (e.g. 192.168.1.1/24).
3. **LAN DHCP server off / IPv6-only** — LuCI › Network › Interfaces › LAN › DHCP Server: "Ignore interface" must be UNticked, an IPv4 DHCP range set.
4. **NAT/masquerade** — Network › Firewall › Zones: lan zone in=lan out=wan with MASQUERADE.
5. **WAN not in DHCP-client mode** — Network › Interfaces › WAN: protocol DHCP client, must receive 192.168.0.x + gateway from the ISP box.

Layperson gotcha: a wifi-iface with NO `network` option does NOT auto-join "lan" — in OpenWrt it stays unbridged. Always set it explicitly.

Topology telling: the machine's eno1 usually sits on the ISP box's flat 192.168.0.0/24 BUT can still reach the LuCI router over its fd80 ULA / link-local (`fe80::…%eno1`) — the LuCI box is NOT a dumb-AP bridged into the ISP subnet; it runs its own 192.168.1.1/24 LAN. Anchor on `ip -br addr` + `ip neigh` (which MAC owns the default gateway), never on a hunch about the LuCI admin IP.

## Driving the OpenWrt router over ssh (no sshpass, no sudo)
Password ssh from the agent works once the user provides creds; OpenWrt's BusyBox has no `sshpass`. Use the SSH_ASKPASS trick so the password isn't left hanging on an unattended fd:
```
printf '#!/bin/sh\necho "<pw>"\n' > /tmp/askpass.sh && chmod +x /tmp/askpass.sh
export SSH_ASKPASS=/tmp/askpass.sh SSH_ASKPASS_REQUIRE=force
ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
    -o PreferredAuthentications=password -o PubkeyAuthentication=no \
    -o NumberOfPasswordPrompts=1 \
    root@fe80::5aef:68ff:fe0e:1816%eno1 '<command>'
```
Gotchas:
- `SSH_ASKPASS`/`SSH_ASKPASS_REQUIRE` do NOT persist across Hermes terminal calls — re-export in the SAME command each time.
- Link-local target needs the scope suffix `%eno1`.
- `setsid -w` (non-interactive askpass trick) is REJECTED by the terminal wrapper — run ssh with `background=true`, then `process(action=wait)`.
- A quoting slip in the remote command aborts BEGIN whole line at parse time (BusyBox `ash`) — test with a trivial `echo CONNECTED` first.
- OpenWrt-native read path (not all present): `uci show <pkg>`, `ifstatus lan`, `iwinfo`, `wifi status`, `ls /sys/class/net/br-lan/brif`, BusyBox `ifconfig` (NOT `ip -br` — unsupported).

## Pitfalls / lessons
- "Not authorized"/"Insufficient privileges" from nmcli is the polkit boundary, not a config error — hand the user the command block instead of retrying.
- Use explicit `connection add` for WPA3 (SAE); `device wifi connect` needs the AP in NM's cache first, which in turn needs a user-driven `rescan`.
- Read `ip -br addr` + `ip route` + `ip neigh` before asserting topology; the default route and ARP table reveal which box actually holds the gateway.
- Never assume a single device hosts all SSIDs — verify BSSID OUIs.

Support files: `references/openwrt-doublenat-session.md` — walkthrough and observed state from the cricri3 investigation.