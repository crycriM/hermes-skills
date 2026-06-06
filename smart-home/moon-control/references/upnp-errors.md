# UPnP AVTransport Error Codes

## Standard UPnP errors (400-600)

| Code | Meaning |
|------|---------|
| 401 | Invalid Action |
| 402 | Invalid Args |
| 403 | Invalid Var |
| 404 | Action Failed |
| 501 | Action Failed (no such object) |
| 600 | Argument Value Invalid |
| 601 | Argument Value Out of Range |
| 602 | Optional Action Not Implemented |
| 603 | Out of Memory |
| 604 | Human Intervention Required |
| 605 | String Argument Too Long |

## AVTransport-specific errors (701-799)

| Code | Meaning | Seen on MOON 390? |
|------|---------|-------------------|
| 701 | Transition Not Available | |
| 702 | No Contents | |
| 703 | Read Error | |
| 704 | Format Not Supported For Playback | |
| 705 | Transport Is Locked | |
| 706 | Write Error | |
| 707 | Media Is Protected Or Not Readable | |
| 708 | Format Not Supported For Recording | |
| 709 | Media Is Full | |
| 710 | Seek Mode Not Supported | |
| 711 | Illegal Seek Target | |
| 712 | Play Mode Not Supported | |
| 713 | Record Quality Not Supported | |
| 714 | Illegal MIME-Type | ✓ (stream.srg-ssr.ch returned this) |
| 715 | Content BUSY | |
| 716 | Resource Not Found | ✓ (dead URLs return this) |
| 717 | Play Speed Not Supported | |
| 718 | Invalid InstanceID | |
| 719 | No DNS Server | |
| 720 | Bad DNS Address | |
| 730 | Restricted Content | |
| 731 | Invalid Stream Type | |
| 732 | Unacceptable Stream | |

## MOON 390 Firmware-Specific Behaviors

### Deadlock on unresolvable airable URIs
When SetAVTransportURI is called with an `airable:` URI that the device cannot
resolve (expired session, bad credentials), the device enters TRANSITIONING and
**locks all write commands** returning HTTP 500. Read commands (GetTransportInfo,
GetVolume) still work. Recovery: full power cycle (unplug from wall 10s).

This appears to be a Rygel firmware bug — the AVTransport instance never times
out or fails gracefully. The lock persists across soft reboots (front panel
power button). Only unplugging from wall power clears it.

**Diagnostic signal:** If Get* commands work but all Set* commands return
HTTP 500 with error 716 or blank error, the firmware is deadlocked.

### Auto-transition on SetAVTransportURI
Some firmware versions auto-start playback when a new URI is set. Calling
`Play` immediately after `SetAVTransportURI` returns HTTP 500 because the
transport is already TRANSITIONING. Solution: wait 0.5s after SetAVTransportURI,
check state, only call Play if state is STOPPED or NO_MEDIA_PRESENT.

### Port changes on reboot
The SSDP/HTTP port changes after hard power cycles (unplug). In our testing:
- First session: port 47561
- After hard reboot: port 33042
Always re-discover via SSDP — never hardcode the port.

### QPlay service
The device also exposes `urn:schemas-tencent-com:service:QPlay:1` — a Tencent
QPlay service. All attempted calls (QPlayAuth, GetDeviceInfo, GetQPlayState)
returned HTTP 500 on our firmware. Not needed for basic control. Likely used
by the MiND app for Tencent QQ Music integration only; unused for Deezer/Tidal.

### NO_MEDIA_PRESENT vs STOPPED vs TRANSITIONING
- **NO_MEDIA_PRESENT**: Device is idle, no URI set. Safe to send SetAVTransportURI.
- **STOPPED**: URI is set but playback stopped. Safe to send Play.
- **TRANSITIONING**: Device is loading/resolving a URI. DO NOT send write commands — firmware deadlock risk.
- **PLAYING**: Active playback. Can send Pause/Stop/Next/Previous.

## Airable URIs

Format: `airable:https://1080906287.airable.io/<service>/<type>/<quality>/<id>`

Known working formats:
- Track: `airable:https://1080906287.airable.io/deezer/play/mp3/128/{deezer_track_id}`
- Playlist: `airable:https://1080906287.airable.io/deezer/playlist/{deezer_playlist_id}`

The device needs an active airable session (established via MiND app Deezer login
or direct POST to https://1080906287.airable.io/authentication with
X-Airable-Secret header) to resolve these URIs.
