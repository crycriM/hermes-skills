# Airable Authentication Blocker

Date: 2026-06-05

## The problem

The MOON 390 streams Deezer/Tidal content through `airable.io`, a cloud
service at `https://1080906287.airable.io` (MiND2) or
`https://3071228948.airable.io` (MiND1). The device needs a valid session
token to resolve `airable:` URIs.

We attempted programmatic authentication via the `/authentication` endpoint:

```
POST https://1080906287.airable.io/authentication
Headers:
  Content-Type: application/json
  X-Airable-Secret: tC3AhgFCLZYMJOaEo9HBqrLwqG3kuUBa
Body: {"username": "...", "password": "...", "service": "deezer"}
Response: {"id":["airable","error","authentication"],"message":"Invalid signature."}
```

The API requires an HMAC signature we couldn't extract from the obfuscated
APK code. The `AirableHelper.connect()` method (from classes5.dex) takes
parameters: `start, parameters, salt, deviceId, name, version, locale, ip,
signature, url` — but the signature computation is in a non-decompiled method.

## What we tried

1. `X-Airable-Secret` header alone → "Invalid signature"
2. HMAC-SHA256 of body with secret as key → not tried (need the exact algo)
3. Observed the APK's `connect` coroutine variables but method not decompiled

## What works instead

The MiND app handles airable auth internally. Opening the app and playing any
Deezer track refreshes the device's session. After that, the device can
stream Deezer while the session is valid (unknown expiry).

## Related: firmware deadlock

Sending `airable:` URIs via UPnP `SetAVTransportURI` when the device lacks a
valid airable session causes the Rygel UPnP stack to enter a permanent
TRANSITIONING state. All write commands (Stop, Play, SetAVTransportURI,
SetVolume) return HTTP 500 with UPnP error 716 "Resource not found" or
similar. Only Get* reads work.

The device does NOT recover from this state. Soft reboot (power button) does
not clear it. Full power cycle (unplug from wall, 10s wait, replug) is
required. This happened 3 times during 2026-06-05 testing session.

## Next steps

1. Extract the signature algorithm from the APK (likely in a `Platform` or
   `Security` utility class, not in `AirableHelper` directly)
2. Or: capture the airable auth flow from the MiND app using mitmproxy/Wireshark
3. Or: abandon airable direct API and implement MiND2 protocol (raw TCP) to
   control Deezer the same way the MiND app does
