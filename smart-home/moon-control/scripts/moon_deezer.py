#!/usr/bin/env python3
"""Search Deezer and play tracks/playlists on MOON 390 via NetAPI.

Usage:
    # Search
    python3 moon_deezer.py search "daft punk"
    python3 moon_deezer.py playlists "quietus"

    # Build curated playlist by theme
    python3 moon_deezer.py --moon 192.168.0.172 build "chill electro"
    python3 moon_deezer.py build --list   # List available themes

    # Play (MOON must be reachable via HTTP port 80)
    python3 moon_deezer.py --moon 10.42.0.194 play 1010508322
    python3 moon_deezer.py --moon 10.42.0.194 playlist 14598167261

    # Transport control
    python3 moon_deezer.py --moon 10.42.0.194 pause|next|prev|state

    # Discovery
    python3 moon_deezer.py discover

Protocol: The MOON exposes a NetAPI on port 80 (HTTP). Phone sends GET/POST
requests directly to the device — no cloud relay for control. The device
auto-plays after a track is queued. See references/hotspot-capture-results.md.
"""

import sys
import json
import urllib.request
import urllib.parse
import logging
from typing import Optional

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger("moon_deezer")

DEEZER_API = "https://api.deezer.com"


# ═══════════════════════════════════════════════════════
# Deezer search
# ═══════════════════════════════════════════════════════

def search_deezer(query: str, limit: int = 10) -> list[dict]:
    """Search Deezer for tracks."""
    params = urllib.parse.urlencode({"q": query, "limit": limit})
    url = f"{DEEZER_API}/search/track?{params}"
    with urllib.request.urlopen(url) as resp:
        return json.loads(resp.read()).get("data", [])


def get_track(track_id: int) -> dict:
    """Get full track info from Deezer."""
    url = f"{DEEZER_API}/track/{track_id}"
    with urllib.request.urlopen(url) as resp:
        return json.loads(resp.read())


def fetch_playlist_tracks(playlist_id: int) -> list[dict]:
    """Fetch all tracks from a Deezer playlist (paginates)."""
    tracks = []
    url = f"{DEEZER_API}/playlist/{playlist_id}/tracks?limit=100"
    while url:
        with urllib.request.urlopen(url) as resp:
            data = json.loads(resp.read())
            tracks.extend(data.get("data", []))
            url = data.get("next")
    return tracks


def search_playlists(query: str, limit: int = 10) -> list[dict]:
    """Search Deezer for playlists."""
    params = urllib.parse.urlencode({"q": query, "limit": limit})
    url = f"{DEEZER_API}/search/playlist?{params}"
    with urllib.request.urlopen(url) as resp:
        return json.loads(resp.read()).get("data", [])


# ═══════════════════════════════════════════════════════
# Curated artist database for themed playlist building
# ═══════════════════════════════════════════════════════

ARTIST_DB: dict[str, list[str]] = {
    "chill electro": [
        "Ben Böhmer", "Christian Löffler", "Bonobo", "Tycho",
        "Rival Consoles", "Four Tet", "Jon Hopkins", "Max Cooper",
        "Lane 8", "Nils Frahm", "Ólafur Arnalds", "Caribou",
        "Bicep", "Overmono", "Floating Points",
    ],
    "deep house": [
        "Lane 8", "Ben Böhmer", "Yotto", "Marsh", "CRi",
        "Le Youth", "Jerro", "Elderbrook", "Durante", "Nora En Pure",
    ],
    "ambient": [
        "Nils Frahm", "Ólafur Arnalds", "Max Richter", "Jóhann Jóhannsson",
        "Hania Rani", "A Winged Victory for the Sullen", "Stars of the Lid",
        "William Basinski", "Tim Hecker", "Hiroshi Yoshimura",
    ],
    "minimal techno": [
        "Boris Brejcha", "Stephan Bodzin", "Paul Kalkbrenner",
        "Recondite", "Dominik Eulberg", "Kölsch", "Maceo Plex",
    ],
    "electronica": [
        "Bonobo", "Four Tet", "Caribou", "Floating Points",
        "Jon Hopkins", "Rival Consoles", "Max Cooper", "Tycho",
        "Bicep", "Overmono", "Christian Löffler",
    ],
}

ARTIST_CACHE: dict[str, int] = {}  # name → Deezer ID


def _get_artist_id(name: str) -> Optional[int]:
    """Resolve artist name to Deezer ID (cached)."""
    if name in ARTIST_CACHE:
        return ARTIST_CACHE[name]
    params = urllib.parse.urlencode({"q": name, "limit": 1})
    url = f"{DEEZER_API}/search/artist?{params}"
    with urllib.request.urlopen(url) as resp:
        data = json.loads(resp.read()).get("data", [])
        if data:
            ARTIST_CACHE[name] = data[0]["id"]
            return data[0]["id"]
    return None


def _get_artist_top_tracks(artist_id: int, limit: int = 8) -> list[dict]:
    """Get top tracks for a Deezer artist."""
    url = f"{DEEZER_API}/artist/{artist_id}/top?limit={limit}"
    with urllib.request.urlopen(url) as resp:
        return json.loads(resp.read()).get("data", [])


def build_playlist(theme: str) -> list[dict]:
    """Build a playlist from curated artists for a given theme.
    
    Returns deduplicated list of track dicts from Deezer API.
    """
    if theme not in ARTIST_DB:
        log.error(f"Unknown theme '{theme}'. Available: {', '.join(ARTIST_DB)}")
        return []
    
    artists = ARTIST_DB[theme]
    seen = set()
    tracks = []
    
    for name in artists:
        aid = _get_artist_id(name)
        if not aid:
            log.warning(f"Artist not found: {name}")
            continue
        top = _get_artist_top_tracks(aid, limit=8)
        count = 0
        for t in top:
            tid = t["id"]
            if tid not in seen:
                seen.add(tid)
                tracks.append(t)
                count += 1
        log.info(f"  {name}: {count} tracks")
    
    log.info(f"Built '{theme}' playlist: {len(tracks)} tracks from {len(artists)} artists")
    return tracks


def list_themes() -> list[str]:
    """Return available playlist themes."""
    return list(ARTIST_DB.keys())


# ═══════════════════════════════════════════════════════
# MOON NetAPI client
# ═══════════════════════════════════════════════════════

class MoonNetAPI:
    """HTTP client for MOON 390 NetAPI (port 80)."""

    def __init__(self, ip: str, timeout: int = 10):
        self.base = f"http://{ip}"
        self.timeout = timeout

    def _get(self, path: str, params: Optional[dict] = None) -> dict:
        qs = urllib.parse.urlencode(params or {})
        url = f"{self.base}{path}?{qs}" if qs else f"{self.base}{path}"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            raw = resp.read().decode()
            return json.loads(raw)

    def _post(self, path: str, data: dict) -> dict:
        body = json.dumps(data).encode()
        req = urllib.request.Request(
            f"{self.base}{path}",
            data=body,
            headers={"Content-Type": "application/json; charset=utf-8"},
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            raw = resp.read().decode()
            return json.loads(raw)

    def get_player_state(self) -> dict:
        """Get now-playing state."""
        return self._get("/api/getData", {
            "path": "player:player/data",
            "roles": "value",
        })

    def set_control(self, action: str) -> dict:
        """Transport control: play, pause, stop, next, previous."""
        value = json.dumps({"control": action})
        return self._get("/api/setData", {
            "path": "player:player/control",
            "roles": "activate",
            "value": value,
        })

    def _build_nsdk_roles(self, track_info: dict) -> str:
        """Build the nsdkRoles JSON string for a single track."""
        track_id = track_info["id"]
        title = track_info.get("title_short", track_info["title"])
        artist = track_info["artist"]["name"] if isinstance(track_info["artist"], dict) else track_info["artist"]
        album = track_info["album"]["title"] if isinstance(track_info["album"], dict) else track_info["album"]
        duration = track_info["duration"]

        if isinstance(track_info.get("album"), dict) and track_info["album"].get("cover_big"):
            icon = track_info["album"]["cover_big"]
        else:
            icon = f"http://cdn-images.dzcdn.net/images/cover/{track_id}/500x500-000000-80-0-0.jpg"

        nsdk_roles = {
            "id": 0,
            "path": f"airable://deezer/track/{track_id}",
            "title": title,
            "icon": icon,
            "type": "audio",
            "containerPlayable": False,
            "disabled": False,
            "mediaData": {
                "metaData": {
                    "artist": artist,
                    "album": album,
                    "contentPrePlayPath": f"airable:preplay?serviceType=deezer&dataType=track&objectId={track_id}",
                    "contentStateChangePath": "airable:statechange",
                    "serviceID": "airable",
                    "maximumRetryCount": 3,
                    "ContentPrePlayTimeOffset": 0,
                    "StartTime": 0,
                    "AllowSeekTime": False,
                },
                "resources": [{
                    "uri": f"airable://deezer/track/{track_id}",
                    "codec": "",
                    "mimeType": "audio/unknown",
                    "duration": duration,
                    "maxIdleTime": 0,
                    "bitRate": 0,
                    "sampleFrequency": 0,
                }],
            },
            "doNotTrack": True,
        }
        return json.dumps(nsdk_roles)

    def queue_tracks(self, tracks: list[dict]) -> dict:
        """Queue multiple Deezer tracks at once.

        Args:
            tracks: list of track dicts from Deezer API.

        Returns the API response.
        """
        items = [{"nsdkRoles": self._build_nsdk_roles(t)} for t in tracks]
        body = {
            "path": "playlists:pl/addexternalitems",
            "roles": ["activate"],
            "value": {
                "items": items,
                "plid": "1",
                "mode": "0",
            },
        }
        return self._post("/api/setData", body)


# ═══════════════════════════════════════════════════════
# Discovery
# ═══════════════════════════════════════════════════════

def discover_moon() -> Optional[str]:
    """Find MOON 390 IP via SSDP. Returns IP or None."""
    import socket
    SSDP_ADDR = ("239.255.255.250", 1900)
    SSDP_MSG = (
        "M-SEARCH * HTTP/1.1\r\n"
        "HOST: 239.255.255.250:1900\r\n"
        'MAN: "ssdp:discover"\r\n'
        "MX: 2\r\n"
        "ST: urn:schemas-upnp-org:device:MediaRenderer:1\r\n"
        "\r\n"
    )

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.settimeout(3)
    sock.sendto(SSDP_MSG.encode(), SSDP_ADDR)

    try:
        while True:
            data, addr = sock.recvfrom(4096)
            resp = data.decode(errors="replace")
            if "Simaudio" in resp or "Rygel" in resp or "MOON" in resp:
                sock.close()
                return addr[0]
    except socket.timeout:
        sock.close()
    return None


# ═══════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════

def main():
    import argparse

    parser = argparse.ArgumentParser(description="Search Deezer and play on MOON 390")
    parser.add_argument("--moon", default=None, help="MOON IP address (auto-discover if omitted)")
    parser.add_argument("action", nargs="?", default="discover",
                        help="Action: discover, search <q>, playlists <q>, build <theme>, play <id>, playlist <id>, pause, next, prev, state")
    parser.add_argument("arg", nargs="?", help="Query, track ID, or theme")
    parser.add_argument("--list", action="store_true", help="List available themes (with build)")
    args = parser.parse_args()

    if args.action == "discover":
        ip = discover_moon()
        if ip:
            print(f"MOON 390 found at {ip}")
        else:
            print("MOON not found via SSDP. Specify --moon <ip>")
        return

    if args.action == "search":
        if not args.arg:
            print("Usage: moon_deezer.py search <query>", file=sys.stderr)
            sys.exit(1)
        results = search_deezer(args.arg)
        if not results:
            print(f"No results for '{args.arg}'")
            return
        print(f"\nDeezer tracks: '{args.arg}' — {len(results)} results\n")
        for i, t in enumerate(results[:10], 1):
            dur = f"{t['duration'] // 60}:{t['duration'] % 60:02d}"
            print(f"  {i:>2}. {t['id']:>10}  {t['artist']['name']} — {t['title']}  [{t['album']['title']}]  {dur}")
        return

    if args.action == "playlists":
        if not args.arg:
            print("Usage: moon_deezer.py playlists <query>", file=sys.stderr)
            sys.exit(1)
        results = search_playlists(args.arg)
        if not results:
            print(f"No playlists for '{args.arg}'")
            return
        print(f"\nDeezer playlists: '{args.arg}' — {len(results)} results\n")
        for i, p in enumerate(results[:15], 1):
            print(f"  {i:>2}. {p['id']:>12}  {p['title']}  ({p.get('nb_tracks', '?')} tracks) by {p['user']['name']}")
        return

    if args.action == "build":
        if args.list:
            themes = list_themes()
            print("Available themes:")
            for t in themes:
                count = len(ARTIST_DB[t])
                artists = ", ".join(ARTIST_DB[t][:3])
                print(f"  {t:20}  {count} artists  ({artists}...)")
            return
        if not args.arg:
            print("Usage: moon_deezer.py build <theme>", file=sys.stderr)
            print("       moon_deezer.py build --list", file=sys.stderr)
            sys.exit(1)
        tracks = build_playlist(args.arg)
        if not tracks:
            sys.exit(1)
        if not args.moon:
            # Preview only — no MOON specified
            print(f"\n{'—'*60}")
            for i, t in enumerate(tracks[:20], 1):
                dur = f"{t['duration'] // 60}:{t['duration'] % 60:02d}"
                print(f"  {i:>2}. {t['artist']['name'][:25]:25} — {t['title'][:40]:40}  {dur}")
            if len(tracks) > 20:
                print(f"  ... and {len(tracks) - 20} more")
            print(f"{'—'*60}\n{len(tracks)} tracks ready. Use --moon <ip> build <theme> to queue.")
            return
        # MOON specified — fall through to queue below

    # All other actions need a MOON IP
    if not args.moon:
        moon_ip = discover_moon()
        if not moon_ip:
            print("Error: MOON not found. Specify --moon <ip>", file=sys.stderr)
            sys.exit(1)
    else:
        moon_ip = args.moon

    api = MoonNetAPI(moon_ip)

    if args.action == "play" and args.arg:
        track = get_track(int(args.arg))
        print(f"Queuing: {track['artist']['name']} — {track['title']}")
        result = api.queue_tracks([track])
        print(f"Response: {json.dumps(result, indent=2)}")

    elif args.action == "playlist" and args.arg:
        playlist_id = int(args.arg)
        print(f"Fetching playlist {playlist_id}...")
        tracks = fetch_playlist_tracks(playlist_id)
        if not tracks:
            print("No tracks found in playlist")
            sys.exit(1)
        print(f"Queuing {len(tracks)} tracks...")
        result = api.queue_tracks(tracks)
        print(f"Response: {json.dumps(result, indent=2)}")

    elif args.action == "build" and args.arg:
        tracks = build_playlist(args.arg)
        if not tracks:
            sys.exit(1)
        print(f"Queuing {len(tracks)} tracks to MOON at {moon_ip}...")
        result = api.queue_tracks(tracks)
        print(f"Response: {json.dumps(result, indent=2)}")

    elif args.action in ("pause", "stop", "next", "prev"):
        action_map = {"prev": "previous"}
        result = api.set_control(action_map.get(args.action, args.action))
        print(f"{args.action}: {json.dumps(result, indent=2)}")

    elif args.action == "state":
        state = api.get_player_state()
        print(json.dumps(state, indent=2))

    else:
        parser.print_help()


if __name__ == "__main__":
    main()