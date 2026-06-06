# Code Fixes — Pending and Applied

## PENDING: Safety guard in play_uri()

**File:** `moon_control.py`, `MoonDevice.play_uri()` method
**Status:** Documented in this file — apply on next session

The current `play_uri()` calls `set_uri()` then `play()` unconditionally.
Two issues:
1. If the device is already TRANSITIONING, a new `SetAVTransportURI` deadlocks
   the firmware (hard reboot required)
2. Some firmwares auto-play on URI set; calling `play()` immediately returns 500

**Fix — replace the three methods:**

```python
def play_uri(self, uri: str, metadata: str = ""):
    """Set URI and start playback. Guards against TRANSITIONING deadlock."""
    state = self.get_transport_info().get('CurrentTransportState', '')
    if state == 'TRANSITIONING':
        raise RuntimeError(
            "Device is TRANSITIONING — sending a new URI would deadlock the "
            "firmware. Wait for it to settle or power-cycle the device."
        )
    self.set_uri(uri, metadata)
    time.sleep(0.5)
    state = self.get_transport_info().get('CurrentTransportState', '')
    if state in ('STOPPED', 'NO_MEDIA_PRESENT'):
        self.play()

def play_deezer_track(self, track_id: int):
    uri = f"airable:{AIRABLE_BASE}/deezer/play/mp3/128/{track_id}"
    self.play_uri(uri)

def play_deezer_playlist(self, playlist_id: int):
    uri = f"airable:{AIRABLE_BASE}/deezer/playlist/{playlist_id}"
    self.play_uri(uri)
```

Note: `import time` is already at the top of the file.

## APPLIED: f-string/bytes fix in discover()

**File:** `moon_control.py`, `discover()` function, line 84
**Status:** Applied 2025-06-05

Original: `f'ST: {SSDP_ST}\r\n'` mixed f-string with bytes literals → SyntaxError
Fix: `b'ST: ' + SSDP_ST.encode() + b'\r\n'`
