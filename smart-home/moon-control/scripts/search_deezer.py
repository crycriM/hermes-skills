#!/usr/bin/env python3
"""Search Deezer via public API and show track IDs for MOON playback.

Usage:
    python3 scripts/search_deezer.py "michael jackson"
    python3 scripts/search_deezer.py "dark side of the moon" --type album

The Deezer public API is free and doesn't require authentication.
Use the returned track/album/artist IDs with the Airable cloud API
to trigger playback on the MOON 390 (requires Layer 2 auth — see skill).
"""
import sys
import json
import urllib.request
import urllib.parse
from typing import Optional

DEEZER_API = "https://api.deezer.com"


def search(query: str, search_type: str = "track", limit: int = 10) -> list[dict]:
    """Search Deezer catalog.

    Args:
        query: Search term (artist, track, album name)
        search_type: 'track', 'artist', 'album', or 'playlist'
        limit: Max results (default 10, max 100)

    Returns:
        List of dicts with id, title, artist, album fields.
    """
    params = urllib.parse.urlencode({"q": query, "limit": limit})
    url = f"{DEEZER_API}/search/{search_type}?{params}"
    try:
        with urllib.request.urlopen(url) as resp:
            data = json.loads(resp.read())
            return data.get("data", [])
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return []


def format_track(t: dict) -> str:
    """Format a track result for display."""
    return (
        f"  {t['id']:>10}  {t['artist']['name']} — {t['title']}  "
        f"[{t['album']['title']}]"
    )


def format_album(a: dict) -> str:
    return f"  {a['id']:>10}  {a['artist']['name']} — {a['title']}"


def format_artist(a: dict) -> str:
    return f"  {a['id']:>10}  {a['name']}  ({a.get('nb_fan', '?')} fans)"


def format_playlist(p: dict) -> str:
    return f"  {p['id']:>10}  {p['title']}  ({p.get('nb_tracks', '?')} tracks) by {p['user']['name']}"


FORMATTERS = {
    "track": format_track,
    "album": format_album,
    "artist": format_artist,
    "playlist": format_playlist,
}


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    query = sys.argv[1]
    search_type = "track"

    # Parse --type flag
    args = sys.argv[2:]
    for i, arg in enumerate(args):
        if arg == "--type" and i + 1 < len(args):
            search_type = args[i + 1]
            break

    results = search(query, search_type)
    if not results:
        print(f"No results for '{query}' (type={search_type})")
        sys.exit(1)

    fmt = FORMATTERS.get(search_type, format_track)
    print(f"\nDeezer search: '{query}' ({search_type}) — {len(results)} results\n")
    for r in results[:15]:
        print(fmt(r))
    print()


if __name__ == "__main__":
    main()
