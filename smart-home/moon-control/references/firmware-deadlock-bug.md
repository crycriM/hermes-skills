# MOON 390 Rygel Firmware Deadlock Bug

## Severity: CRITICAL — bricks device until hard power cycle

## Reproduction

1. Device is in STOPPED or NO_MEDIA_PRESENT state
2. Send `SetAVTransportURI` with an `airable:` URI that the device can't resolve:
   ```
   airable:https://1080906287.airable.io/deezer/playlist/14324532281
   ```
3. URLError or HTTP 500 on the SOAP call (sometimes it returns 200 — the URI
   is accepted but resolution fails later)
4. Send `Play`
5. Device enters TRANSITIONING state and stays there forever

## Symptoms

- `GetTransportInfo` → `<CurrentTransportState>TRANSITIONING</CurrentTransportState>`
- `GetTransportInfo` also shows `<CurrentTransportStatus>OK</CurrentTransportStatus>` —
  the device THINKS it's fine, just "transitioning"
- ALL write commands return HTTP 500 with UPnP error codes:
  - `Stop` → 500
  - `SetAVTransportURI` → 500
  - `Play` → 500
  - `Next` → 500
  - `SetVolume` → 500 (note: volume control normally works via RenderingControl,
    but in this state it also fails)
- Only Get* reads work (GetTransportInfo, GetMediaInfo, GetPositionInfo,
  GetVolume)
- QPlay service also returns 500 for all actions
- Port 80 returns "The requested url was not found"
- MiND app also cannot control the device

## Recovery

**Only hard power cycle works.** Unplug from wall, wait 10 seconds, replug.
Soft reboot (front panel power button) does NOT clear the state. The device
comes back with a new SSDP port number.

## Attempted fixes (all failed)

- `Stop` → 500
- `SetAVTransportURI` with empty URI → accepted (URI cleared to "") but state stays TRANSITIONING
- `SetNextAVTransportURI` with empty → accepted but no effect
- ConnectionManager `GetProtocolInfo` and `GetCurrentConnectionIDs` → work but don't help
- Waiting 30+ seconds → never times out

## Occurrences

- 2026-06-05: 3 times during moon-control skill development
  - First: TheQuietus playlist ID 14324532281 (bad airable session)
  - Second: Deezer track ID 2886687292 (expired session)
  - Third: Deezer track ID 831196 (original track, also expired)

## Root cause hypothesis

The Rygel UPnP stack (GUPnP 1.0.2 on Linux 4.1.15) doesn't properly handle
unresolvable URIs. When `SetAVTransportURI` sets a URI that requires
external service resolution (airable), the AVTransport state machine enters
TRANSITIONING while trying to fetch the stream metadata. If the fetch fails
(401/403/network error), the state machine has no error transition back to
STOPPED — it's stuck waiting for a resolution that will never complete.

The Rygel version used by MOON 390 appears to be an older GUPnP 1.0.2 build
that lacks proper timeout/error handling for the TRANSITIONING state.

## Prevention

- NEVER call `play_deezer_track()` or `play_deezer_playlist()` methods
- Before any `play_uri()` call, check transport state:
  ```python
  state = device.get_transport_info()['CurrentTransportState']
  if state == 'TRANSITIONING':
      raise RuntimeError("Device stuck — hard reboot required")
  ```
- Only use `play_uri()` with plain HTTP URLs (radio streams, local files)
- Use the MiND app for all Deezer playback
