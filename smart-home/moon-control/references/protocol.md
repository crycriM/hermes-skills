# MiND1 / MiND2 Protocol Reference

Reversed from MiND Android app v9.x (com.simaudio.mind, June 2025).
Decompiled with jadx v1.5.0 + portable JRE 17.

## Architecture Overview

The MiND device exposes a single TCP port (discovered via SSDP, typically 49152+)
that multiplexes two protocols:

1. **NetAPI** — XML events over HTTP-framed TCP (transport control, browse, etc.)
2. **StreamerByteData** — Raw binary frames (low-level device commands)

Both use the same TCP socket. Messages are framed and dispatched by type.

---

## Layer 1: NetAPI (XML over TCP)

### Wire Format

HTTP POST over persistent TCP connection:

```
POST /NetApi HTTP/1.1
Host: <ip>:<port>
Content-Type: text/xml
Content-Length: <n>

<event>
  <name>Play</name>
  <items>
    <map>
      <key>value</key>
    </map>
  </items>
</event>
```

Response is HTTP with XML body.

### NetApiMethod Enum (48 methods)

```
GetAPIVersion  = "GetAPIVersion"
RequestAPIVersion = "RequestAPIVersion"
Ping           = "Ping"
Disconnect     = "Disconnect"
GetViewState   = "GetViewState"
RequestChangeViewState = "RequestChangeViewState"
GoHome         = "GoHome"
GetActiveList  = "GetActiveList"
GetRows        = "GetRows"
PlayRow        = "PlayRow"
BrowseRow      = "BrowseRow"
BrowseParent   = "BrowseParent"
GetNowPlaying  = "GetNowPlaying"
GetNowPlayingTime = "GetNowPlayingTime"
Play           = "Play"
IsPlaying      = "IsPlaying"
Stop           = "Stop"
Pause          = "Pause"
IsPaused       = "IsPaused"
Next           = "Next"
Previous       = "Previous"
ScanInc        = "ScanInc"
ScanDec        = "ScanDec"
IsScanning     = "IsScanning"
StopScan       = "StopScan"
SetRepeat      = "SetRepeat"
SetRandom      = "SetRandom"
GetRepeat      = "GetRepeat"
GetRandom      = "GetRandom"
GetValidTransportControls = "GetValidTransportControls"
SetVolume      = "SetVolume"
GetVolume      = "GetVolume"
SetMute        = "SetMute"
GetMute        = "GetMute"
GetActiveMessage = "GetActiveMessage"
AcknowledgeMessage = "AcknowledgeMessage"
GetBridgeCoAppVersions = "GetBridgeCoAppVersions"
GetNetworkConnectionStatus = "GetNetworkConnectionStatus"
GetMACAddress  = "GetMACAddress"
TunnelFromHost = "TunnelFromHost"
TunnelToHost   = "TunnelToHost"
GetMacAddress  = "GetMACAddress"  // duplicate
SetSeekToTime  = "SetSeek2Time"   // value mismatch in enum
AddURIToFavorites = "AddURIToFavourites"
RemoveItemFromFavourites = "RemoveItemFromFavourites"
ClearFavourites = "ClearFavourites"
GetFavouritesStatus = "GetFavouritesStatus"
GetFavouritesItems = "GetFavouritesItems"
```

Source: `com.simaudio.mind.data.streamer.netAPIXml.NetApiMethod`

---

## Layer 2: StreamerByteData (Raw Binary)

### Frame Format

```
[Start Byte (1)] [Indicator Byte (1)] [Message Number (1)] [Length (1)] [Payload... (N)] [Parity (1)]
```

- **Start Byte**: Always `0x01` for commands
- **Indicator Byte**: `CommandByte` enum value
- **Message Number**: Incrementing counter (0-255), managed per-connection
- **Length**: Total frame length including start, indicator, msg#, length, payload, parity = N + 5
- **Payload**: Variable-length byte array
- **Parity**: XOR of all preceding bytes (start through last payload byte)

### CommandByte Enum

```
GetProtocolVersion  = 0 (0x00)
GetPowerState       = 16 (0x10)
NewPowerState       = 17 (0x11)
GetVersion          = 20 (0x14)
StartFWUpdate       = 21 (0x15)
StartFWUpdateAH     = 23 (0x17)
AdjVolumeUp         = 32 (0x20)
AdjVolumeDown       = 33 (0x21)
AdjVolumeStop       = 34 (0x22)
SendIRCode          = 37 (0x25)
AHPassthru          = 38 (0x26)
GetDeviceName       = 48 (0x30)
SetDeviceName       = 49 (0x31)
PlayURL             = 127 (0x7F)   // SignedBytes.MAX_POWER_OF_TWO
CBSwitch            = 69 (0x45)
GetNetworkProfile   = 80 (0x50)
SetNetworkProfile   = 81 (0x51)
```

Source: `com.simaudio.mind.streamer.mind1.stream.communications.CommandByte`

### PassthroughCommandByte Enum (for AHPassthru payload)

These are sent as payload[1] when indicator byte is AHPassthru (0x26):

```
GetProductInfo       = 1  (0x01)
SetProductInfo       = 2  (0x02)
GetInputsInfo        = 3  (0x03)
GetSpecificInputInfo = 4  (0x04)
SetSpecificInputInfo = 5  (0x05)
SelectInput          = 6  (0x06)
GetVolume            = 7  (0x07)
GetSampleRate        = 8  (0x08)
CheckForUpdates      = 10 (0x0A)
StartUpdate          = 11 (0x0B)
GetSubSystemInfo     = 12 (0x0C)
GetSubSystemNewVersion = 13 (0x0D)
StartUpdateAH        = 14 (0x0E)
GetStandBy           = 15 (0x0F)
```

Source: `com.simaudio.mind.data.streamer.netAPIXml.models.PassthroughCommandByte`

### Transport Control Bytes (for AHPassthru payload)

These are NOT in the PassthroughCommandByte enum. They are sent as raw
bytes in the payload when indicator is AHPassthru (0x38... wait, 0x38 = 56
but the enum says AHPassthru = 38 = 0x26).

> **⚠ Correction needed**: AHPassthru in the CommandByte enum is 38 (0x26).
> The payload format for passthrough is `[0x38, <transport byte>]` where
> the first payload byte 0x38 is likely a sub-indicator, not the same as
> the CommandByte.

Transport bytes observed:
- Play:     `0xDA` (218)
- Pause:    `0x80` (128)
- Stop:     `0xEB` (235)
- Next:     `0x4E` (78)
- Previous: `0x4D` (77) — hypothesised, pattern suggests 0x4D

> **Note**: The transport bytes were identified by the user from prior
> research. The decompiled `MiND1.play()` method was not decompilable
> (UnsupportedOperationException), so the exact framing for transport
> control via raw bytes remains unconfirmed. The NetAPI layer is the
> recommended approach for transport control.

---

## Layer 3: Airable REST API (Cloud Content)

### Overview

Airable is the cloud service that provides streaming-service content
browsing for the MiND platform. It is NOT the transport control channel.

### Endpoints

| Environment | Base URL |
|-------------|----------|
| MiND1        | `https://3071228948.airable.io` |
| MiND2 (prod) | `https://1080906287.airable.io` |
| Advancement  | `https://1858554549.airable.io` |
| Betterment   | `https://0000000000.airable.io/debug/` |

Source: `com.simaudio.mind.airable.AirableConfiguration`

### Secrets

| Environment | Secret |
|-------------|--------|
| Production  | `tC3AhgFCLZYMJOaEo9HBqrLwqG3kuUBa` |
| Advancement | `PJFKwfIWH7LIoaYGqlEOe5x2QzLCzcVN` |
| Betterment  | `SDJu3QuHIwi8JSz0T1r5zVaKoU8jbmFE` |

### API

- `GET /streaming` — list available streaming services
- `GET /streaming/<id>` — browse service directory
- `POST /authentication` — authenticate (body: `{username, password, service}`)
- `GET /search?q=...&service=...` — search

Authentication returns a JWT token used in `Authorization: Bearer <token>`.

### IAirableHelper Interface

```kotlin
interface IAirableHelper {
    suspend fun connect(): ResponseSuccess
    suspend fun getStreaming(id: String): AirableDirectory?
    suspend fun getContent(url: String, timeout: Int, retry: Int): Pair<Map<String, *>, String>?
    fun getBaseUrl(): String?
}
```

Source: `com.simaudio.mind.helpers.IAirableHelper`

---

## SSDP Discovery

The device announces itself as a UPnP MediaRenderer:

- M-SEARCH target: `urn:schemas-upnp-org:device:MediaRenderer:1`
- Multicast: 239.255.255.250:1900
- Response contains LOCATION header with description.xml URL
- Description XML contains `friendlyName`, `modelName`, and service endpoints

---

## Decompilation Setup

For future APK analysis:

```bash
# Install jadx (no sudo needed)
wget https://github.com/skylot/jadx/releases/download/v1.5.0/jadx-1.5.0.zip
unzip jadx-1.5.0.zip -d /tmp/jadx

# Install portable JRE
wget https://github.com/adoptium/temurin17-binaries/releases/download/jdk-17.0.16%2B8/OpenJDK17U-jre_x64_linux_hotspot_17.0.16_8.tar.gz
tar -xzf jre.tar.gz -C /tmp/

# Decompile
export JAVA_HOME=/tmp/jdk-17.0.16+8-jre
/tmp/jadx/bin/jadx -d /tmp/decompiled app.apk
```

The interesting packages are:
- `com.simaudio.mind.streamer.mind1` — MiND1 protocol
- `com.simaudio.mind.streamer.mind2` — MiND2 protocol
- `com.simaudio.mind.data.streamer.netAPIXml` — NetAPI XML models
- `com.simaudio.mind.airable` — Airable cloud integration
- `com.simaudio.mind.helpers.AirableHelper` — Airable REST client implementation
