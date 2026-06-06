# Hotspot Capture — MOON 390 ↔ Phone Traffic

Preferred over ARP spoofing: no device disruption, no network interference,
clean pcap with only target traffic on a dedicated interface.

## Why this works

Instead of injecting ARP packets between MOON and gateway, turn the capture
machine into a WiFi hotspot. Connect both MOON and phone to it. All traffic
passes through us — tcpdump on the hotspot interface sees everything.

## Requirements

- WiFi interface with AP mode support (`iw phy phy0 info | grep AP`)
- `hostapd` + `dnsmasq` installed
- sudo access (hostapd, dnsmasq, tcpdump all need it)

## Setup (one-shot)

```bash
# 0. Unblock WiFi
sudo rfkill unblock wifi

# 1. Install deps
sudo apt install hostapd dnsmasq -y

# 2. Tell NetworkManager to keep hands off
sudo nmcli device set wlp195s0 managed no

# 3. Create hostapd config
sudo tee /etc/hostapd/hostapd-moon.conf <<'EOF'
interface=wlp195s0
driver=nl80211
ssid=moon-capture
hw_mode=g
channel=6
wmm_enabled=0
macaddr_acl=0
auth_algs=1
ignore_broadcast_ssid=0
wpa=2
wpa_passphrase=test1234
wpa_key_mgmt=WPA-PSK
wpa_pairwise=TKIP
rsn_pairwise=CCMP
EOF

# 4. Assign static IP (use non-conflicting subnet — 10.42.0.0/24)
sudo ip addr add 10.42.0.1/24 dev wlp195s0

# 5. Start hostapd (daemon mode)
sudo hostapd -B /etc/hostapd/hostapd-moon.conf

# 6. Start DHCP server (foreground — run in separate terminal or bg)
sudo dnsmasq -d --interface=wlp195s0 \
  --dhcp-range=10.42.0.100,10.42.0.200,12h \
  --bind-interfaces &
```

## Verify

```bash
# Interface should be in AP mode with correct SSID
iw dev wlp195s0 info
# → type AP, ssid moon-capture, channel 6

# Check connected stations
iw dev wlp195s0 station dump

# Check DHCP leases
cat /var/lib/misc/dnsmasq.leases
```

## Capture

Once both MOON (MAC `10:c3:7b:4c:7c:a2`) and phone are connected:

```bash
sudo tcpdump -i wlp195s0 -w /tmp/moon_capture_$(date +%Y%m%d_%H%M%S).pcap -s 0 -v
```

Interact with the MiND app, then Ctrl+C. Analyze the pcap.

## Teardown

```bash
sudo pkill hostapd
sudo pkill dnsmasq
sudo ip addr del 10.42.0.1/24 dev wlp195s0
sudo nmcli device set wlp195s0 managed yes
```

## Pitfalls

- **nmcli hotspot blocked by polkit**: `nmcli dev wifi hotspot` fails with
  "Not authorized to control networking" on many desktop distros. Use hostapd
  directly — it bypasses NetworkManager authorization entirely.
- **NetworkManager fights for interface**: NM may re-grab wlp195s0 mid-session.
  Always run `nmcli device set wlp195s0 managed no` before starting hostapd.
- **MOON WiFi may need front-panel navigation**: If MOON doesn't auto-join,
  use the front panel to select the `moon-capture` network. The MiND app can't
  change WiFi networks while not on the same network as the device.
- **txpower may be low**: The `iw dev wlp195s0 info` output shows txpower.
  If it's very low (~3 dBm), keep devices within a few meters.
- **No internet on hotspot**: By design — no NAT rules added. This keeps the
  capture clean (no background cloud traffic from phone apps). If the MiND app
  requires internet for streaming, add NAT: `sudo iptables -t nat -A POSTROUTING -o eno1 -j MASQUERADE`.
