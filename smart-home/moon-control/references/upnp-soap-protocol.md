# UPnP SOAP Protocol — MOON 390 (MiND 2 / Rygel)

The device is a standard Rygel-based MediaRenderer. All control happens via
UPnP SOAP calls to AVTransport and RenderingControl services. **Do not attempt
raw TCP binary protocol** — the device does not respond to it.

## Device Info

- **Manufacturer**: Simaudio
- **Model**: MOON 390 (MiND 2)
- **UPnP stack**: Rygel (GUPnP 1.0.2)
- **Device type**: `urn:schemas-upnp-org:device:MediaRenderer:2`
- **Friendly name**: "Audio 1" (default Rygel name — renameable in app)

## Control URLs

Discovered from device description XML at the SSDP location URL:

| Service | Control URL |
|---------|------------|
| AVTransport:2 | `/Control/LibRygelRenderer/RygelAVTransport` |
| RenderingControl:2 | `/Control/LibRygelRenderer/RygelRenderingControl` |
| ConnectionManager:2 | `/Control/LibRygelRenderer/RygelSinkConnectionManager` |
| QPlay:1 | `/Control/LibRygelRenderer/QPlay` |

Base: `http://<device-ip>:47561`

## SOAP Request Format

```python
envelope = (
    '<?xml version="1.0"?>'
    '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" '
    's:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">'
    '<s:Body>' + body + '</s:Body>'
    '</s:Envelope>'
)

headers = {
    'Content-Type': 'text/xml; charset="utf-8"',
    'SOAPACTION': '"urn:schemas-upnp-org:service:AVTransport:2#Play"',
}
```

Critical: the `SOAPACTION` header must use the **version-1 namespace** (`:1`)
even when calling version-2 services. The service type in the body XML uses `:2`.

## AVTransport Actions

All use `<InstanceID>0</InstanceID>`.

| Action | Body | Notes |
|--------|------|-------|
| Play | `<Speed>1</Speed>` | |
| Pause | — | |
| Stop | — | |
| Next | — | |
| Previous | — | |
| Seek | `<Unit>REL_TIME</Unit><Target>00:01:30</Target>` | |
| SetAVTransportURI | `<CurrentURI>...</CurrentURI><CurrentURIMetaData></CurrentURIMetaData>` | Use `airable:` URIs for streaming |
| GetTransportInfo | — | Returns CurrentTransportState |
| GetMediaInfo | — | Returns CurrentURI, NrTracks |
| GetPositionInfo | — | Returns RelTime, TrackDuration |
| GetTransportSettings | — | Returns PlayMode |
| SetPlayMode | `<NewPlayMode>NORMAL</NewPlayMode>` | NORMAL, REPEAT_ALL, REPEAT_ONE, SHUFFLE |

## RenderingControl Actions

All use `<InstanceID>0</InstanceID><Channel>Master</Channel>`.

| Action | Extra Body | Notes |
|--------|-----------|-------|
| SetVolume | `<DesiredVolume>60</DesiredVolume>` | 0-100 |
| GetVolume | — | Returns CurrentVolume |
| SetMute | `<DesiredMute>1</DesiredMute>` | 1=mute, 0=unmute |
| GetMute | — | Returns CurrentMute (0 or 1) |

## Response Parsing

Responses are XML with the pattern:
```xml
<u:ActionNameResponse xmlns:u="http://...">
  <FieldName>value</FieldName>
</u:ActionNameResponse>
```

Parse with regex: `re.search(r'<FieldName>(.*?)</FieldName>', resp)`

## Airable URIs

Streaming service content is identified by airable: URIs:

| Content Type | URI Format |
|-------------|------------|
| Deezer track | `airable:https://1080906287.airable.io/deezer/play/mp3/128/{track_id}` |
| Deezer playlist | `airable:https://1080906287.airable.io/deezer/playlist/{playlist_id}` |
| Deezer album | `airable:https://1080906287.airable.io/deezer/album/{album_id}` |

Set via `SetAVTransportURI` then `Play`.

## Pitfalls

1. **Airable auth required**: The device needs an active airable session to stream.
   Without it, SetAVTransportURI succeeds but Play stays TRANSITIONING forever.
   Solution: open the MiND app briefly to refresh the session, or POST to
   `https://1080906287.airable.io/authentication` with Deezer credentials.
   Auth endpoint: POST JSON `{username, password, service}` with header
   `X-Airable-Secret: tC3AhgFCLZYMJOaEo9HBqrLwqG3kuUBa`.

2. **Port 47561, not 49152**: The MiND 2 uses port 47561 (from SSDP), not the
   49152 commonly assumed for MiND 1.

3. **SSDP UUID-based URL**: The description XML is at a UUID path like
   `/4a4012fc-86dd-4ee2-bd9b-064a08e99c4b.xml`, not `/description.xml`.

4. **HTTP 500 on Play when already playing**: The device returns 500 if you
   call Play while already TRANSITIONING. Stop first.

5. **No raw binary protocol**: The MiND1 binary protocol (StartByte.Command = 0xA5)
   does NOT work on this device. It's Rygel, not the MiND1 firmware stack.
