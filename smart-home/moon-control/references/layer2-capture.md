# Layer 2 — Full Investigation Results

## What we tried

| Approach | Result |
|----------|--------|
| LAN packet capture (phone ↔ device) | **Zero packets** — app uses cloud relay, not direct LAN |
| `/api/v1` probing on port 80 | "wrong method" for all HTTP methods — cloud relay endpoint, locked |
| UPnP `SetAVTransportURI` with `x-mind://` URIs | Accepted but doesn't trigger streaming — needs cloud auth |
| UPnP `SetAVTransportURI` with `airable://` URIs | Same — stored but playback doesn't start |
| APK decompilation (androguard + strings) | **Success** — discovered full NetAPI paths and Airable cloud endpoints |
| NetAPI direct HTTP calls | **Success** — `player:player/data` returns full now-playing with Deezer track info |
| Transport control via NetAPI | **Blocked** — passthrough byte format not decoded |

## Architecture (confirmed)

```
Phone (MiND app)
    |
    |--- TLS ---> airable.io cloud (browse/search catalog)
    |
    |--- TLS ---> Simaudio cloud (relay commands)
                        |
                        |--- persistent connection ---> MOON 390
                                                          |
                                                          |--- TLS ---> Deezer CDN (audio stream)
```

The phone has ZERO direct LAN communication with the device for streaming services.
All control goes through the cloud. The device's `/api/v1` endpoint on port 80 is the
cloud relay's inbound endpoint (authenticated connections only).

## NetAPI (local HTTP REST on port 80)

Discovered via string extraction from classes.dex in APK v3.1.0.

### Format
```
GET /api/getData?path=<path>&roles=<role>
GET /api/setData?path=<path>&roles=<role>&value=<value>  (yes, GET not POST)
GET /api/getRows?path=<path>
```

### Typed value wrappers
- `{"bool_": true/false}` — boolean
- `{"double_": 34.5}` — float
- `{"i32_": 0}` — 32-bit integer
- `{"string_": "name"}` — string
- `{"type": "playerPlayMode", "playerPlayMode": "normal"}` — enum

### Full path inventory

**Read paths (getData):**

| Path | Returns |
|------|---------|
| `player:player/data` | Full playback state: track title, artist, album, duration, stream URI, Deezer ID, controls available, play context |
| `player:player/data/playTime` | Current playback position |
| `player:mindVolume` | Volume 0-100 as double_ |
| `settings:/mediaPlayer/mute` | Mute state |
| `settings:/mediaPlayer/playMode` | Repeat mode (normal/repeat_all/repeat_one/repeat_track) |
| `settings:/deviceName` | "Audio 1" |
| `settings:/network/profile` | DHCP, wired status |
| `settings:/airplay/addedToHome` | AirPlay status |
| `settings:/googlecast/castVersion` | Google Cast version |
| `multiroomobserver:enabled` | Multiroom enabled? |
| `mindtworf:/HostAPI/PowerState` | Power state |
| `timemanager:/availableCountries` | Timezone list |
| `settings:www/ftsTimeZone` | Timezone setting |

**Write paths (setData):**

| Path | Roles | Purpose |
|------|-------|---------|
| `player:player/control` | activate | Transport control — BLOCKED (passthrough bytes) |
| `player:mindVolume` | value | Set volume |
| `settings:/mediaPlayer/mute` | value | Set mute |
| `settings:/mediaPlayer/playMode` | value | Set repeat mode |
| `settings:/deviceName` | value | Set device name |
| `mindtworf:/HostAPI/AHPassthru` | activate | Hardware passthrough — BLOCKED |
| `mindtworf:/HostAPI/AdjVolume` | activate | Adjust volume |
| `mindtworf:/HostAPI/PowerState` | activate | Power on/off |
| `mindtworf:/HostAPI/SendIRCode` | activate | IR blaster |
| `network:scan` | activate | WiFi scan (value empty) |
| `grouping:request` | value | Multiroom grouping |
| `firmwareupdate:checkForUpdate` | activate | Firmware check |
| `settings:www/ftsTimeZone` | value | Set timezone |

### Transport control — what's blocked

The `player:player/control` and `mindtworf:/HostAPI/AHPassthru` endpoints need binary
passthrough command bytes. From the APK:

- `PassthroughCommandByte` Kotlin enum with WhenMappings
- `AhPassthroughParser` / `AhPassthroughEnums`
- Known byte values: `0xDA`, `0x80`, `0xEB`, `0x4E`

Sending `{"type":"i32_","i32_":N}` triggers queue-clearing behavior, not transport control.
Need to use jadx (Java decompiler) to extract the full enum→byte mapping.

## Airable cloud API

The device is authenticated with Airable (device-specific token in firmware).
Cloud API endpoints (requires auth):

```
https://1080906287.airable.io/           — root (requires token+secret)
https://1080906287.airable.io/deezer/    — Deezer catalog
https://1080906287.airable.io/id/deezer/track/<id>  — content resolution
https://1080906287.airable.io/deezer/play/<fmt>/<bitrate>/<id>:<context>  — streaming
```

Other device subdomains found: `1858554549.airable.io`, `3071228948.airable.io`,
`0000000000.airable.io/debug/`

## PrePlayData format

Binary blob (base64) containing 3 streaming URLs at different quality levels:
- Header: `uint32 count=3`
- For each: `uint32 len` + UTF-16LE string

Example URLs for track 15586296:
- `https://1080906287.airable.io/deezer/play/flac/1411/15586296:flow`
- `https://1080906287.airable.io/deezer/play/mp3/320/15586296:flow`
- `https://1080906287.airable.io/deezer/play/mp3/128/15586296:flow`

## Viable paths to close the gap

1. **jadx decompile**: Install Java, run jadx on APK, extract `PassthroughCommandByte` enum mappings
2. **Device firmware extraction**: The MOON 390 firmware at `https://www.simaudio.com/mind/MiND_update.bin` may contain Airable credentials
3. **Deezer public API + AirPlay**: Search Deezer via public API, then AirPlay from a Mac/Python to the MOON (AirPlay 2 is supported)
4. **Roon**: If you have a Roon server, `node-roon-api` gives full Deezer/Tidal/Qobuz control
5. **mitmproxy on phone**: Requires Android proxy config or VPN-based interception of app↔cloud TLS
