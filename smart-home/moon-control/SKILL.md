---
name: moon-control
description: Remote control of a MOON 390 (MiND 2) network audio player via UPnP SOAP (Rygel AVTransport + RenderingControl) and NetAPI (HTTP port 80) for Deezer search + playback. Supports transport, volume, mute, seek, now-playing, Deezer track/playlist queueing, and HTTP stream playback.
tags: [moon, mind, audio, deezer, upnp, ssdp, rygel, airable, streaming]
---

# Moon Control Skill

Remote control of a MOON 390 (MiND 2) network audio player. The device is a
standard Rygel-based UPnP MediaRenderer — control uses SOAP calls to
AVTransport and RenderingControl services. No proprietary protocol needed.

## Architecture

### Layer 1: UPnP SOAP (working ✓)
The device exposes standard UPnP SOAP services on port 47561 (discovered via SSDP):
- **AVTransport:2** — Play, Pause, Stop, Next, Previous, Seek, SetAVTransportURI
- **RenderingControl:2** — SetVolume, GetVolume, SetMute, GetMute

This is all that's needed for transport/volume control. The device handles
streaming internally once given an `airable:` URI.

### Layer 2: Airable cloud content (BROKEN — do not use via UPnP)
Airable (`https://1080906287.airable.io`) is a cloud service for streaming
service content (Deezer/Tidal). The device resolves `airable:` URIs to fetch
DRM-protected streams. **However, the MiND app bypasses UPnP entirely for
Deezer streaming.** It uses a proprietary MiND2 protocol on a separate TCP
channel (port unknown, not exposed via SSDP). UPnP AVTransport is only used
for generic HTTP streams and DLNA casting.

**⚠️ DANGER — FIRMWARE DEADLOCK:** Do NOT send `airable:` URIs via UPnP
SetAVTransportURI. If the device can't resolve the airable URI (expired
session, bad ID, auth required), it enters TRANSITIONING and **permanently
locks ALL write commands** — including Stop, Play, and SetVolume. Even a soft
reboot doesn't clear it. **Recovery: unplug from wall 10 seconds.**

**⚠️ Airable auth blocked:** The `/authentication` endpoint requires an HMAC
signature we couldn't extract from the obfuscated APK code. Sending just the
`X-Airable-Secret` header returns "Invalid signature." Until the signature
algorithm is reverse-engineered, programmatic airable auth is not possible.

**⚠️ Port changes on reboot:** The SSDP port changes after every power cycle.
Always run `discover()` before connecting — never hardcode the port.

**⚠️ MiND app hijacks AVTransport:** When the MiND app is actively streaming
Deezer, AVTransport reports NO_MEDIA_PRESENT. The Deezer playback happens
entirely outside the UPnP stack. Transport commands (Play/Pause/Next) return
HTTP 500 during MiND app streaming.

### Layer 3: NetAPI + Deezer (working ✓ — via hotspot capture 2026-06-06)
Deezer's public API (`https://api.deezer.com`) can search tracks, albums,
playlists without authentication. The MOON's NetAPI (HTTP port 80) accepts
track queueing via POST to `/api/setData` with the `playlists:pl/addexternalitems`
path. The device auto-plays after queueing — no explicit play needed.

See `scripts/moon_deezer.py` and `references/hotspot-capture-results.md`.

## Usage

### Layer 1: UPnP SOAP (transport, volume)
```python
from moon_control import MoonDevice, discover
devices = discover()
moon = MoonDevice(devices[0].ip, devices[0].port)
moon.play()
moon.set_volume(60)
```

### Layer 2: NetAPI (Deezer search + playback)
```bash
# Search tracks or playlists
python3 scripts/moon_deezer.py search "daft punk"
python3 scripts/moon_deezer.py playlists "quietus"

# Play a single track (auto-plays after queueing)
python3 scripts/moon_deezer.py --moon 10.42.0.194 play 3135556

# Queue an entire playlist
python3 scripts/moon_deezer.py --moon 10.42.0.194 playlist 14598167261

# Transport control
python3 scripts/moon_deezer.py --moon 10.42.0.194 pause
python3 scripts/moon_deezer.py --moon 10.42.0.194 next
python3 scripts/moon_deezer.py --moon 10.42.0.194 prev

# Player state
python3 scripts/moon_deezer.py --moon 10.42.0.194 state

# Discover MOON on network
python3 scripts/moon_deezer.py discover
```

The MOON must be reachable via HTTP port 80 on the local network.
The device auto-plays after a track is queued — no explicit play command needed.

## CLI

```bash
python3 moon_control.py discover              # Find devices
python3 moon_control.py status                # Now playing + volume
python3 moon_control.py play | pause | stop   # Transport
python3 moon_control.py next | prev           # Skip
python3 moon_control.py vol 60                # Set volume
python3 moon_control.py mute on | off         # Mute
```

## Files

- `moon_control.py` — Full implementation (MoonDevice, discover, AirableClient)
- `scripts/moon_deezer.py` — **Deezer search + MOON NetAPI queueing** (single tracks + playlists)
- `scripts/moonctl.py` — CLI wrapper (argparse-based, async)
- `scripts/search_deezer.py` — Search Deezer catalog via public API
- `scripts/arp_capture.sh` — ARP spoof capture of MOON↔gateway traffic via bettercap
- `references/upnp-soap-protocol.md` — **Canonical protocol reference**: SOAP format, all actions
- `references/upnp-errors.md` — UPnP error codes, MOON 390 firmware-specific bugs
- `references/code-fixes.md` — Pending fixes: play_uri auto-transition workaround
- `references/protocol.md` — Complete NetAPI/MiND1 protocol from APK reverse engineering
- `references/docker-tcpdump.md` — TCP capture setup
- `references/layer2-capture.md` — Full investigation: architecture, ARP spoof, NetAPI paths
- `references/hotspot-capture-results.md` — **Key finding**: phone→MOON NetAPI is HTTP plaintext

## Dependencies

Python stdlib only (socket, urllib, xml). No pip installs needed.

## Pitfalls

### ⚠️ DANGER: Firmware deadlock on unresolvable airable URIs

The MOON 390 Rygel firmware has a critical bug: if `SetAVTransportURI` sets an
`airable:` URI that the device can't resolve (expired Deezer session, bad ID),
the AVTransport enters TRANSITIONING and **permanently locks all write commands**
including Stop, Play, SetAVTransportURI, and even SetVolume. Only Get* reads
work. **Recovery: unplug from wall for 10 seconds, replug.**

BEFORE calling `play_uri()` or any airable method, always check:
```python
state = device.get_transport_info()['CurrentTransportState']
if state == 'TRANSITIONING':
    raise RuntimeError("Device stuck — hard reboot required")
```

### ⚠️ Deezer requires active airable session

The device fetches Deezer streams through `https://1080906287.airable.io`.
The session token is established by the MiND app during Deezer login. Without
a valid session, `SetAVTransportURI` succeeds silently but `Play` leaves the
device in TRANSITIONING (see deadlock above). Restore Deezer auth via the
MiND app before attempting Deezer playback.

### Port changes on reboot

The UPnP control port changes every device restart. Always `discover()`.

### Auto-transition on SetAVTransportURI

Some firmware versions auto-start playback on URI set. Calling `play()` 
immediately after `set_uri()` may return HTTP 500. Wait 0.5s and check state.

### MOON 390 WPA2 password entry bug

The front-panel password entry UI appends a spurious character after the last
typed digit, corrupting the passphrase. Association silently fails with no
error message on screen. **Use open networks for WiFi capture.**

## Capture methods

- `references/docker-tcpdump.md` — Docker-based capture
- `references/layer2-capture.md` — Full investigation: ARP spoof, NetAPI, architecture
- `references/wifi-hotspot-capture.md` — Hostapd hotspot capture (no ARP spoof, cleanest approach)
- `scripts/arp_capture.sh` — ARP spoof script (bettercap-based)

## Safety

This skill only sends control commands to the device on the local network. It does not attempt to intercept, decode, or circumvent DRM-protected audio streams. Reverse engineering was performed for interoperability purposes (EU Directive 2009/24/EC art. 6).
