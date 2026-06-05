---
name: moon-control
description: Remote control of a MOON 390 (MiND 2) network audio player. Two-layer architecture reversed from the MiND Android app. Supports NetAPI (TCP XML) for transport control and Airable REST API for Deezer/Tidal content browsing.
tags: [moon, mind, audio, deezer, upnp, ssdp, reverse-engineering, airable, streaming]
---

# Moon Control Skill

Remote control of a MOON 390 (MiND 2) network audio player. Two-layer architecture reversed from the MiND Android app:

## Architecture

### Layer 1: NetAPI (TCP XML)
The device exposes a TCP port (discovered via SSDP, typically 49152) that accepts XML events over HTTP-framed messages. This is the primary control channel.

**Supported commands:** Play, Pause, Stop, Next, Previous, SetVolume, GetVolume, SetMute, GetMute, Seek, GetNowPlaying, GetPlayTime, GetRows, PlayRow, BrowseRow, GoHome, Favorites, Ping, and more (48 total methods from NetApiMethod enum).

### Layer 2: Airable REST API (HTTPS)
Airable is a cloud service that provides content browse/search for streaming services (Deezer, Tidal, etc.). The MiND app uses it to browse catalogs, then tells the device to play via NetAPI.

**Endpoints:**
- MiND1: `https://3071228948.airable.io`
- MiND2: `https://1080906287.airable.io`
- Auth: `/authentication` (POST: username, password, service)
- Browse: `/streaming/<id>`
- Search: `/search?q=...&service=...`

**Key insight:** The airable API provides the content metadata (tracks, albums, playlists). Once a track is selected, the MiND app sends a NetAPI `PlayRow` or `Play` command to the device, which then fetches the DRM-protected stream directly from Deezer/Tidal servers.

## Usage

```python
from moon_control import MoonController, discover_and_connect

# Auto-discover and connect
ctrl = discover_and_connect()
if ctrl:
    ctrl.play()
    ctrl.set_volume(75)
    ctrl.next_track()
    ctrl.disconnect()
```

```python
# Direct IP connection
from moon_control import MoonController
ctrl = MoonController("192.168.1.50")
ctrl.connect()
print(ctrl.get_now_playing())
ctrl.pause()
ctrl.disconnect()
```

```python
# Airable (Deezer) content browsing
from moon_control import AirableClient
ac = AirableClient()
ac.authenticate("user@email.com", "password", service="deezer")
results = ac.search("daft punk")
# Get directory ID from results, then use MoonController.play_row()
```

## CLI

```bash
python moon_control.py discover    # Find devices
python moon_control.py play        # Play
python moon_control.py pause       # Pause
python moon_control.py next        # Next track
python moon_control.py vol 75      # Set volume
python moon_control.py np          # Now playing
```

## Files

- `moon_control.py` — Full implementation (controller + discovery + airable client)
- `references/protocol.md` — Complete protocol reference: enum values, binary format, airable endpoints, secrets, and decompilation setup
- `references/docker-tcpdump.md` — TCP capture setup for reverse engineering
- `references/layer2-capture.md` — Capture methodology for proprietary protocol
- `scripts/moonctl.py` — CLI wrapper
- `scripts/search_deezer.py` — Deezer search through airable

## Dependencies

Python stdlib only (socket, urllib, xml). No pip installs needed.

## Legal

This skill only sends control commands to the user's own device on the local network. It does not intercept, decode, or circumvent DRM-protected audio streams. Reverse engineering was performed for interoperability purposes (EU Directive 2009/24/EC art. 6).
