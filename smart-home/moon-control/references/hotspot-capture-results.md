# Hotspot Capture Results — 2026-06-06

## Capture Setup

- Host machine as WiFi AP: `moon-capture` (open), wlp195s0, 10.42.0.1/24
- NAT via eno1 for internet access
- MOON 390 WiFi: 50:1e:2d:2e:14:5e, hostname `audivosimaudiomind2-501e2d2e145c`, IP 10.42.0.194
- Phone: HUAWEI Mate 20 Pro, IP 10.42.0.152
- **Key trick:** MOON prefers wired — must unplug Ethernet to force WiFi

## Major Finding: Phone Talks Directly to MOON

The previous assumption (phone → cloud relay → MOON) is **wrong** for control.
The phone sends HTTP requests directly to the MOON on port 80. The cloud is only for:
- Deezer catalog browsing (phone → airable.io TLS)
- Audio streaming (MOON → Deezer CDN TLS)

### Confirmed Architecture

```
Phone (MiND app)
    |-- HTTP port 80 --> MOON 390 (NetAPI: control, playlist, power)
    |-- TLS -----------> airable.io (Deezer catalog browsing)
    
MOON 390
    |-- TLS -----------> airable.io (preplay/statechange)
    |-- TLS -----------> Deezer CDN (audio stream)
```

## NetAPI Protocol — Confirmed Live

### Session Initiation

1. Phone creates event queue: `GET /api/event/pollQueue?queueId=<uuid>&timeout=15`
   - Long-polling, re-issues every ~1 second
   - MOON pushes state changes via this channel

2. Phone queries device identity:
   - `GET /api/getData?path=settings:/system/systemId&roles=value` → `"audivosimaudiomind2-501e2d2e145c"`
   - `GET /api/getData?path=settings:/system/modelName&roles=value` → `"MOON 390"`
   - `GET /api/getData?path=settings:/version&roles=value` → `"2.5.0.0x563a4e0"`

### Power & Input Control

```http
# Power on
GET /api/setData?path=mindtworf:/HostAPI/PowerState&roles=activate
  &value={"ahPowerState":"on","type":"ahPowerState"}

# Switch input via IR (0x5b = Deezer/MiND input)
GET /api/setData?path=mindtworf:/HostAPI/SendIRCode&roles=activate
  &value={"ahIRCode":{"command":"0x5b","address":"0x1e","mode":"0x02"},"type":"ahIRCode"}
```

Response: `{"xclass":"NsdkActionReply","result":{"value":{"type":"bool_","bool_":true}}}`

### Playlist: Adding a Track

**POST** (not GET!) to `/api/setData` with JSON body:

```json
{
  "path": "playlists:pl/addexternalitems",
  "roles": ["activate"],
  "value": {
    "items": [{
      "nsdkRoles": "{\"id\":0,\"path\":\"airable://deezer/track/1010508322\",\"title\":\"Room with a View (Plaid Remix)\",\"icon\":\"http://cdn-images.dzcdn.net/images/cover/d5cae30a7d34b86371297297050db8d2/500x500-000000-80-0-0.jpg\",\"type\":\"audio\",\"containerPlayable\":false,\"disabled\":false,\"mediaData\":{\"metaData\":{\"artist\":\"Rone\",\"album\":\"Room with a View Remixes\",\"contentPrePlayPath\":\"airable:preplay?serviceType=deezer&dataType=track&objectId=1010508322\",\"contentStateChangePath\":\"airable:statechange\",\"serviceID\":\"airable\",\"maximumRetryCount\":3,\"ContentPrePlayTimeOffset\":0,\"StartTime\":0,\"AllowSeekTime\":false},\"resources\":[{\"uri\":\"airable://deezer/track/1010508322\",\"codec\":\"\",\"mimeType\":\"audio/unknown\",\"duration\":249,\"maxIdleTime\":0,\"bitRate\":0,\"sampleFrequency\":0}]},\"doNotTrack\":true}"
    }],
    "plid": "1",
    "mode": "0"
  }
}
```

**Key fields in the nsdkRoles JSON string (double-escaped):**
- `path`: `airable://deezer/track/<deezer_id>` — track URI
- `title`: track title
- `icon`: album art URL (Deezer CDN)
- `mediaData.metaData.artist`: artist name
- `mediaData.metaData.album`: album name
- `mediaData.metaData.contentPrePlayPath`: `airable:preplay?...` — preplay URL
- `mediaData.metaData.contentStateChangePath`: `airable:statechange`
- `mediaData.metaData.serviceID`: `"airable"`
- `mediaData.resources[0].uri`: same airable track URI
- `mediaData.resources[0].duration`: track duration in seconds
- `doNotTrack`: `true` (don't add to play history?)

**Response:** `{"xclass":"NsdkActionReply","result":{"value":{"type":"bool_","bool_":true}}}`

**Event queue notification after add:**
```json
{"rowsVersion":0,"path":"playlists:pl/getitems/1","rowsType":"update",
 "rowsEvents":[{"type":"add","index":1}],"rowsOldVersion":0}
```

### Player State Queries

```http
# Now playing
GET /api/getData?path=player:player/data&roles=value

# Playback position
GET /api/getData?path=player:player/data/playTime&roles=value

# Repeat mode
GET /api/getData?path=settings:/mediaPlayer/playMode&roles=value
```

### Transport Control

```http
# Pause (CONFIRMED WORKING via hotspot capture)
GET /api/setData?path=player:player/control&roles=activate
  &value={"control":"pause"}

# Play — returns HTTP 500 when already playing. Queueing auto-plays,
# so explicit play is only needed after pause/stop. Likely works.
```

### Playlist Queueing

Multiple tracks can be queued in a single POST by including multiple items:

```json
{
  "path": "playlists:pl/addexternalitems",
  "roles": ["activate"],
  "value": {
    "items": [
      {"nsdkRoles": "<track 1 JSON string>"},
      {"nsdkRoles": "<track 2 JSON string>"}
    ],
    "plid": "1",
    "mode": "0"
  }
}
```

Tested with 100-track playlist — queued successfully in one request.
Device auto-plays the first track; subsequent tracks play in order.

## Playlist Queries

```http
# Get playlist container info
GET /api/getRows?path=playlists:pl/getitems/1&roles=containerType&from=0&to=0

# Get track details
GET /api/getRows?path=playlists:pl/getitems/1&roles=title,icon,mediaData,id,context&from=0&to=1
```

## Deezer Audio Streaming (MOON → CDN)

- DNS: `cdnt-stream.dzcdn.net` → `deezer.akamaized.net` → Akamai CDN IPs
- MOON connects to `96.17.206.202:443` (TLS) — 1832 packets, the bulk of the capture
- This is the FLAC/MP3 audio stream delivered directly to the MOON

## Implications

1. **NetAPI transport control WORKS** — `{"control":"pause"}` is plain JSON, not passthrough bytes.
   The previous APK-based analysis was wrong. We can likely send `play`, `stop`, `next`, `previous`.

2. **Phone → MOON is HTTP plaintext** — we can capture and replay all control commands.
   No encryption, no auth tokens needed for local control.

3. **Track queueing requires only a Deezer track ID** — the nsdkRoles JSON can be
   constructed programmatically. We just need the track ID, title, artist, album, duration,
   and album art URL — all available from Deezer's public API.

4. **Power on and input switching work** — `{"ahPowerState":"on"}` and IR code `0x5b` (Deezer input).

## Next Steps

1. Test `{"control":"play"}`, `{"control":"stop"}`, `{"control":"next"}`, `{"control":"previous"}`
2. Test adding a track via POST with programmatically constructed nsdkRoles
3. Test volume control: `player:mindVolume` with `{"type":"double_","double_":50}`
4. Check if other control values work (seek, shuffle, repeat)
