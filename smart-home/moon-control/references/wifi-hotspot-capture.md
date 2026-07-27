# WiFi Hotspot Capture — Clean Alternative to ARP Spoof

Instead of ARP spoofing (disruptive, bettercap Docker overhead), turn the
capture machine into a WiFi hotspot, connect both the MOON and phone to it,
and capture directly on the hotspot interface with tcpdump. No MITM tricks,
no latency, no device disconnects.

See `references/hotspot-capture-results.md` for analysis of captured traffic
and the NetAPI protocol discoveries made with this method.

## Prerequisites

- WiFi adapter with AP mode support (`iw phy phy0 info | grep "AP"`)
- `hostapd` and `dnsmasq` installed
- `rfkill unblock wifi` if soft-blocked

## Setup (one-shot)

```bash
# 1. Unblock WiFi
sudo rfkill unblock wifi

# 2. Install deps
sudo apt install hostapd dnsmasq -y

# 3. Tell NetworkManager hands off
sudo nmcli device set wlp195s0 managed no

# 4. hostapd config (open network — MOON has password entry bugs, see pitfall)
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
EOF

# 5. Assign static IP
sudo ip addr add 10.42.0.1/24 dev wlp195s0

# 6. Start AP
sudo hostapd -B /etc/hostapd/hostapd-moon.conf

# 7. Start DHCP
sudo dnsmasq -d --interface=wlp195s0 \
  --dhcp-range=10.42.0.100,10.42.0.200,12h \
  --bind-interfaces &

# 8. Enable NAT so MOON has internet (required for Deezer streaming)
sudo sysctl -w net.ipv4.ip_forward=1
sudo iptables -t nat -A POSTROUTING -o eno1 -j MASQUERADE
sudo iptables -A FORWARD -i wlp195s0 -o eno1 -j ACCEPT
sudo iptables -A FORWARD -i eno1 -o wlp195s0 -m state --state RELATED,ESTABLISHED -j ACCEPT
```

## Capture

```bash
sudo tcpdump -i wlp195s0 -w /tmp/moon_capture_$(date +%Y%m%d_%H%M%S).pcap -s 0
```

## Teardown

```bash
sudo pkill hostapd
sudo pkill dnsmasq
sudo ip addr del 10.42.0.1/24 dev wlp195s0
sudo iw dev wlp195s0 set type managed
sudo nmcli device set wlp195s0 managed yes

# Clean up NAT rules (flush FORWARD + POSTROUTING, or reboot)
sudo iptables -D FORWARD -i wlp195s0 -o eno1 -j ACCEPT 2>/dev/null
sudo iptables -D FORWARD -i eno1 -o wlp195s0 -m state --state RELATED,ESTABLISHED -j ACCEPT 2>/dev/null
sudo iptables -t nat -D POSTROUTING -o eno1 -j MASQUERADE 2>/dev/null
sudo sysctl -w net.ipv4.ip_forward=0
```

## Pitfalls

### hostapd "Match already configured" on restart

If hostapd crashes or is killed, the interface stays in AP mode. Restarting
hostapd without resetting yields a segfault. Fix:

```bash
sudo ip link set wlp195s0 down
sudo iw dev wlp195s0 set type managed
sudo ip link set wlp195s0 up
sudo hostapd -B /etc/hostapd/hostapd-moon.conf
```

### Low txpower limits range

Check with `iw dev wlp195s0 info | grep txpower`. Values around 3 dBm mean
very short range — devices must be within a few meters. If the MOON can see
the SSID but can't associate, txpower is likely the cause. Try raising it:

```bash
sudo iw dev wlp195s0 set txpower fixed 2000  # 20 dBm
```

### MOON 390 WPA2 password entry bug

The MOON front-panel password entry adds a spurious character when typing the
last digit — this corrupts the passphrase and association silently fails with
no error message. **Use open networks for capture** and rely on physical
proximity + short capture windows for security.

### Identifying which device is which

Don't rely on IPs alone — phones use MAC randomization and DHCP may reassign.
Check hostnames in `cat /var/lib/misc/dnsmasq.leases`:

- **MOON**: hostname begins with `audivosimaudiomind2-` (WiFi MAC `50:1e:2d:2e:14:5e`)
- **Phone**: hostname includes model name (e.g. `HUAWEI_Mate_20_Pro`)
- Old/stale leases show `*` as hostname — these are expired, ignore them

### MOON 390 prefers wired over WiFi

If Ethernet is plugged in, the MOON will ignore the WiFi network entirely.
**Unplug the Ethernet cable** to force WiFi before attempting to connect.

MOON WiFi MAC: `50:1e:2d:2e:14:5e` (hostname `audivosimaudiomind2-501e2d2e145c`)
MOON Wired MAC: `10:c3:7b:4c:7c:a2`

### No internet = no Deezer

Without NAT (step 8 above), devices on the hotspot have no internet access.
The MiND app will show "Deezer service not found" because the MOON can't reach
airable.io or the Deezer CDN. Always enable NAT before testing streaming.
