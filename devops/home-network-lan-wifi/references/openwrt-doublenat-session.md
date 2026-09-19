# OpenWrt LuCI double-NAT walkthrough (cricri3 investigation, 2026-08-26)

## Situation
ISP box owns 192.168.0.0/24 (gateway [REDACTED], SSID [REDACTED], MAC [REDACTED]).
User plugged the OpenWrt LuCI router's WAN port into the ISP box, wifi ON, wanting clients
on SSID "cricri3" to get the router's own DHCP on a separate subnet. Symptoms:
- Windows: password accepted but "no internet"
- Linux/NM: "Connection activation failed — IP configuration not available" (DHCP never answered)

## CONFIRMED root cause (this is what was actually wrong)
The OpenWrt wifi-iface blocks (`wifinet1`, `wifinet2` on radio1 2g / radio0 5g) had **no
`option network 'lan'`**. Result: the AP interfaces phy0-ap0 / phy1-ap0 came UP but were
**NOT members of br-lan**:
```
br-lan members (before):  lan1 lan2 lan3 lan4
readlink /sys/class/net/phy0-ap0/master -> NONE (not bridged)
```
Clients associated to cricri3 fine (SAE handshake OK, signal 100) but their DHCP broadcasts
never reached dnsmasq (bound to br-lan), so no IPv4 lease ever arrived. A wifi-iface with no
`network` option stays unbridged — there is NO implicit default to "lan".

Everything else was already correct (so double-NAT config was NOT the problem):
- LAN = br-lan static **192.168.1.1/24** (disjoint from ISP 192.168.0.0/24) — good.
- LAN DHCPv4 enabled, range 192.168.1.100–.249 — good.
- WAN = `dhcp` (would pull 192.168.0.x from ISP box when plugged in) — good.
- Wifi cricri3 SAE on both radios — good.

## The fix (applied, verified)
```
uci set wireless.wifinet1.network=lan
uci set wireless.wifinet2.network=lan
uci commit wireless && wifi reload
```
Verify after:
```
ls /sys/class/net/br-lan/brif         # now: lan1 lan2 lan3 lan4 phy0-ap0 phy1-ap0
readlink /sys/class/net/phy0-ap0/master   # -> .../virtual/net/br-lan
wifi status | grep -cE '"up": true'   # 2 radios
```

## Topology corrections learned this session
- The LuCI router is NOT at 192.168.0.1 — that IP belongs to a separate AP (MAC
  c0:3f:0e:a5:48:40, SSID "cricri"). The LuCI box is reached at `fe80::5aef:68ff:fe0e:1816%eno1`
  (ssh) and `https://[fd80:6964:93f9::1]` (LuCI). It is NOT a dumb-AP on 192.168.0.0/24;
  it runs its own 192.168.1.1/24 LAN. Earlier "IPv6-only / no IPv4 DHPC" memory was WRONG.
- The two cricri3 BSSIDs (00:25:9C:14:3A:83 ch6, 00:25:9C:14:3A:84 ch161) are this router's
  own radios (phy1-ap0 MAC 00:25:9C:14:3A:83, phy0-ap0 MAC 00:25:9C:14:3A:84).

## Host side (the M5 laptop running this session)
- eno1 [REDACTED]/24 gw [REDACTED] (metric 100) — primary; wlp195s0 into [REDACTED]
  [REDACTED]/24 (metric 600). Wifi never took the default route from ethernet.
- Agent's nmcli is polkit-bound: `rescan`/`wifi connect`/`connection add` → "not authorized" /
  "Insufficient privileges". Those are USER-shell commands. Read-only (`connection show`,
  `device wifi list`, `ip`, `journalctl -u NetworkManager`) are fine from the agent.
- To test, user runs: `nmcli device wifi connect cricri3 password '<psk>'` from their shell.

## Read path used on the router (works over ssh)
`uci show wireless` / `uci show network`, `ifstatus lan`, `wifi status`, `iwinfo`,
`ls /sys/class/net/br-lan/brif`, `readlink /sys/class/net/<ap>/master`, BusyBox `ifconfig`.
Note: BusyBox `ip` does NOT support `-br`; remote command quoting slips abort the whole ash
line at parse time (test with a bare `echo` first).