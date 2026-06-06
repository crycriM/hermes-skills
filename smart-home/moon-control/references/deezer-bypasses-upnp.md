# Architecture Discovery: Deezer Streaming Bypasses UPnP

Date: 2026-06-05

## Finding

The MOON 390 (MiND 2) has TWO separate playback engines:

1. **Rygel UPnP MediaRenderer** — handles HTTP streams, DLNA casting, and
   basic AVTransport commands. Exposed via SSDP on a dynamic port (47561,
   33042, 43809 observed).

2. **MiND2 proprietary engine** — handles Deezer/Tidal streaming. The MiND
   app communicates with this engine via a proprietary TCP protocol (MiND2),
   NOT via UPnP. This engine is NOT exposed via SSDP.

## Evidence

When the MiND app is playing Deezer:
- AVTransport reports `NO_MEDIA_PRESENT` with empty URI
- `GetMediaInfo` shows `<NrTracks>0</NrTracks>`, `<PlayMedium>NONE</PlayMedium>`
- `GetTransportInfo` shows `<CurrentTransportState>NO_MEDIA_PRESENT</>`
- Yet the user hears Deezer music through the device

Transport commands (Play/Pause/Next) sent via AVTransport during MiND app
Deezer playback return HTTP 500. Volume commands via RenderingControl DO work
(volume is shared across both engines).

## Implication

To control Deezer playback programmatically, we must implement the MiND2
protocol — the same protocol the MiND app uses. UPnP AVTransport is
insufficient. The MiND2 protocol uses raw TCP (likely on port 50000, which
is open on the device but didn't respond to our test frames).

## Previously observed (before deadlock experiments)

On first discovery (2026-06-05 ~08:30 UTC), the device showed a Deezer
track via AVTransport:
```
CurrentURI: airable:https://1080906287.airable.io/deezer/play/mp3/128/831196
NrTracks: 1
State: STOPPED
```

This means the MiND app HAD set a URI via AVTransport at some point. The
device was likely in a state where the MiND app had used AVTransport to
queue a track (perhaps during initial setup or a different app version).

Current hypothesis: The MiND app uses AVTransport for initial Deezer track
queuing, then switches to MiND2 protocol for playback control. Or it only
uses AVTransport when the device's streaming engine is in a specific mode.

## Port investigation

SSDP discovery ports observed:
- 47561 (first discovery)
- 33042 (after first reboot)
- 43809 (after second reboot)

Other open ports on device:
- 80 (HTTP — returns error page, no NetAPI)
- 50000 (TCP — accepts connection, no response to binary MiND1 frames)

The MiND2 protocol port remains unknown. The MiND app connects via Ktor
(io.ktor.network.sockets.Socket) using `InetSocketAddress` — the port is
likely a constant in the obfuscated code that didn't survive decompilation.

## QPlay service

The device exposes a Tencent QPlay service at `/Control/LibRygelRenderer/QPlay`.
All attempted actions (QPlayAuth, GetDeviceInfo, GetQPlayState) returned 500.
QPlay may be the protocol the MiND app uses internally, but it requires
authentication/an initial handshake we don't know.
