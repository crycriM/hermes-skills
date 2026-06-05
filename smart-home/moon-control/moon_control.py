"""
Moon Control Skill - Remote control for MOON 390 (MiND 2) network audio player.

Two-layer architecture:
  Layer 1: NetAPI (XML over TCP) — transport control, volume, now-playing, browse
  Layer 2: Airable REST API — streaming service content browse/search (Deezer, Tidal)

Protocol: Single TCP connection multiplexes both NetAPI XML events and raw
StreamerByteData frames. Discovered port via UPnP SSDP (typically 49152+).

Reversed from MiND Android app v9.x (com.simaudio.mind, June 2025).
"""

import socket
import struct
import time
import hashlib
import hmac
import json
import re
import ssl
from typing import List, Dict, Optional, Tuple, Any
from urllib.request import urlopen, Request
from urllib.error import URLError
from urllib.parse import urlencode
import xml.etree.ElementTree as ET


# ═══════════════════════════════════════════════════════════════════
# Constants from APK reverse engineering
# ═══════════════════════════════════════════════════════════════════

# Port used by MiND devices for control
MIND_CONTROL_PORT = 49152

# Airable cloud API endpoints
AIRABLE_MIND1_BASE = "https://3071228948.airable.io"
AIRABLE_MIND2_BASE = "https://1080906287.airable.io"
AIRABLE_SECRET = "tC3AhgFCLZYMJOaEo9HBqrLwqG3kuUBa"

# NetAPI method names (from NetApiMethod enum, deobfuscated)
class NetMethod:
    PLAY = "Play"
    PAUSE = "Pause"
    STOP = "Stop"
    NEXT = "Next"
    PREVIOUS = "Previous"
    SET_VOLUME = "SetVolume"
    GET_VOLUME = "GetVolume"
    SET_MUTE = "SetMute"
    GET_MUTE = "GetMute"
    GET_NOW_PLAYING = "GetNowPlaying"
    GET_NOW_PLAYING_TIME = "GetNowPlayingTime"
    SET_SEEK_TIME = "SetSeekToTime"
    GET_ROWS = "GetRows"
    PLAY_ROW = "PlayRow"
    BROWSE_ROW = "BrowseRow"
    BROWSE_PARENT = "BrowseParent"
    GO_HOME = "GoHome"
    GET_ACTIVE_LIST = "GetActiveList"
    SET_REPEAT = "SetRepeat"
    SET_RANDOM = "SetRandom"
    GET_VALID_TRANSPORT_CONTROLS = "GetValidTransportControls"
    GET_FAVORITES_ITEMS = "GetFavouritesItems"
    ADD_TO_FAVORITES = "AddURIToFavorites"
    REMOVE_FROM_FAVORITES = "RemoveItemFromFavourites"
    GET_FAVORITES_STATUS = "GetFavouritesStatus"
    TUNNEL_TO_HOST = "TunnelToHost"
    TUNNEL_FROM_HOST = "TunnelFromHost"
    PING = "Ping"
    GET_MAC_ADDRESS = "GetMacAddress"


# ═══════════════════════════════════════════════════════════════════
# UPnP / SSDP Discovery
# ═══════════════════════════════════════════════════════════════════

def discover_mind_devices(timeout: int = 5) -> List[Dict[str, Any]]:
    """Discover MiND devices on the network using SSDP.

    Returns list of dicts with keys:
      ip, port, description_url, friendly_name, model_name
    """
    M_SEARCH = (
        b'M-SEARCH * HTTP/1.1\r\n'
        b'HOST: 239.255.255.250:1900\r\n'
        b'MAN: "ssdp:discover"\r\n'
        b'ST: urn:schemas-upnp-org:device:MediaRenderer:1\r\n'
        b'MX: 2\r\n'
        b'\r\n'
    )

    devices = []
    seen_ips = set()

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.settimeout(timeout)
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
        sock.sendto(M_SEARCH, ('239.255.255.250', 1900))

        start = time.time()
        while time.time() - start < timeout:
            try:
                data, addr = sock.recvfrom(4096)
                ip = addr[0]
                if ip in seen_ips:
                    continue
                seen_ips.add(ip)

                response = data.decode('utf-8', errors='ignore')
                lines = response.split('\r\n')

                location = None
                for line in lines:
                    if line.upper().startswith('LOCATION:'):
                        location = line.split(':', 1)[1].strip()
                        break

                if location:
                    # Parse: http://ip:port/path
                    if location.startswith('http://'):
                        location = location[7:]
                    host_part, _, _ = location.partition('/')
                    if ':' in host_part:
                        device_ip, port_str = host_part.split(':', 1)
                        port = int(port_str)
                    else:
                        device_ip = host_part
                        port = MIND_CONTROL_PORT

                    devices.append({
                        'ip': device_ip,
                        'port': port,
                        'description_url': f'http://{host_part}/description.xml',
                        'friendly_name': 'Unknown',
                        'model_name': 'Unknown',
                    })

            except socket.timeout:
                break
            except Exception:
                continue

        sock.close()

    except Exception as e:
        print(f"SSDP discovery failed: {e}")

    # Enrich with device description
    for dev in devices[:]:
        try:
            with urlopen(dev['description_url'], timeout=3) as resp:
                root = ET.fromstring(resp.read())
                ns = {'': 'urn:schemas-upnp-org:device-1-0'}
                fn = root.find('.//friendlyName', ns)
                mn = root.find('.//modelName', ns)
                if fn is not None and fn.text:
                    dev['friendly_name'] = fn.text
                if mn is not None and mn.text:
                    dev['model_name'] = mn.text
        except Exception:
            pass

    return devices


# ═══════════════════════════════════════════════════════════════════
# NetAPI client — TCP socket, XML event exchange
# ═══════════════════════════════════════════════════════════════════

class NetApiClient:
    """Low-level NetAPI client over TCP."""

    def __init__(self, ip: str, port: int = MIND_CONTROL_PORT):
        self.ip = ip
        self.port = port
        self._sock: Optional[socket.socket] = None
        self._connected = False

    @property
    def connected(self) -> bool:
        return self._connected and self._sock is not None

    def connect(self, timeout: float = 5.0) -> bool:
        """Establish TCP connection."""
        try:
            self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._sock.settimeout(timeout)
            self._sock.connect((self.ip, self.port))
            self._connected = True
            return True
        except Exception as e:
            print(f"Failed to connect to {self.ip}:{self.port}: {e}")
            self._sock = None
            self._connected = False
            return False

    def disconnect(self):
        """Close TCP connection."""
        if self._sock:
            try:
                self._sock.close()
            except Exception:
                pass
            finally:
                self._sock = None
                self._connected = False

    def _recv_all(self, timeout: float = 5.0) -> bytes:
        """Receive data until socket closes or timeout."""
        if self._sock is None:
            return b""
        self._sock.settimeout(timeout)
        data = b""
        try:
            while True:
                chunk = self._sock.recv(4096)
                if not chunk:
                    break
                data += chunk
        except socket.timeout:
            pass
        return data

    def send_event(self, method: str, items: Optional[List[Dict[str, str]]] = None,
                   property_name: str = "", data_value: str = "") -> Optional[str]:
        """Send a NetAPI XML event and optionally receive response.

        Args:
            method: NetMethod value (e.g., "Play", "Pause")
            items: list of key-value dicts for the event
            property_name: property name (for enum methods)
            data_value: data value (for enum methods)

        Returns:
            Response XML string if available, None otherwise.
        """
        if not self.connected:
            print("Not connected")
            return None

        # Build XML event
        # <event><name>Play</name>...</event>
        xml_parts = ['<event>', f'<name>{method}</name>']
        if items:
            xml_parts.append('<items>')
            for item in items:
                xml_parts.append('<map>')
                for k, v in item.items():
                    xml_parts.append(f'<{k}>{v}</{k}>')
                xml_parts.append('</map>')
            xml_parts.append('</items>')
        xml_parts.append('</event>')
        xml_body = ''.join(xml_parts)

        # Wrap in HTTP POST (NetAPI uses HTTP-like framing over TCP)
        http_request = (
            f"POST /NetApi HTTP/1.1\r\n"
            f"Host: {self.ip}:{self.port}\r\n"
            f"Content-Type: text/xml\r\n"
            f"Content-Length: {len(xml_body)}\r\n"
            f"Connection: keep-alive\r\n"
            f"\r\n"
            f"{xml_body}"
        )

        try:
            if self._sock is None:
                print("Socket is None")
                return None
            self._sock.send(http_request.encode('utf-8'))
            response = self._recv_all(timeout=3.0)
            if response:
                # Parse HTTP response to get body
                parts = response.split(b'\r\n\r\n', 1)
                if len(parts) > 1:
                    return parts[1].decode('utf-8', errors='ignore')
            return None
        except Exception as e:
            print(f"Failed to send event: {e}")
            self._connected = False
            return None


# ═══════════════════════════════════════════════════════════════════
# Moon Controller — high-level API
# ═══════════════════════════════════════════════════════════════════

class MoonController:
    """High-level controller for MOON 390 (MiND 2) device."""

    def __init__(self, ip: str, port: int = MIND_CONTROL_PORT):
        self.ip = ip
        self.port = port
        self._client = NetApiClient(ip, port)

    def connect(self) -> bool:
        return self._client.connect()

    def disconnect(self):
        self._client.disconnect()

    # ── Transport Control ────────────────────────────────────────

    def play(self):
        self._client.send_event(NetMethod.PLAY)

    def pause(self):
        self._client.send_event(NetMethod.PAUSE)

    def stop(self):
        self._client.send_event(NetMethod.STOP)

    def next_track(self):
        self._client.send_event(NetMethod.NEXT)

    def previous_track(self):
        self._client.send_event(NetMethod.PREVIOUS)

    def toggle_play_pause(self):
        # Try playing; device will interpret based on current state
        self._client.send_event(NetMethod.PLAY)

    def seek(self, seconds: int):
        """Seek to position in seconds."""
        self._client.send_event(NetMethod.SET_SEEK_TIME,
                                items=[{"time": str(seconds)}])

    # ── Volume / Mute ────────────────────────────────────────────

    def set_volume(self, volume: int):
        """Set volume (0-100)."""
        self._client.send_event(NetMethod.SET_VOLUME,
                                items=[{"volume": str(volume)}])

    def get_volume(self) -> Optional[int]:
        """Get current volume."""
        resp = self._client.send_event(NetMethod.GET_VOLUME)
        if resp:
            match = re.search(r'<volume>(\d+)</volume>', resp)
            if match:
                return int(match.group(1))
        return None

    def set_mute(self, muted: bool):
        """Mute or unmute."""
        self._client.send_event(NetMethod.SET_MUTE,
                                items=[{"mute": "1" if muted else "0"}])

    # ── Now Playing ──────────────────────────────────────────────

    def get_now_playing(self) -> Optional[str]:
        """Get current track info (raw XML)."""
        return self._client.send_event(NetMethod.GET_NOW_PLAYING)

    def get_play_time(self) -> Optional[Tuple[int, int]]:
        """Get (elapsed_seconds, total_seconds)."""
        resp = self._client.send_event(NetMethod.GET_NOW_PLAYING_TIME)
        if resp:
            m1 = re.search(r'<elapsed>(\d+)</elapsed>', resp)
            m2 = re.search(r'<total>(\d+)</total>', resp)
            if m1 and m2:
                return (int(m1.group(1)), int(m2.group(1)))
        return None

    # ── Browsing ─────────────────────────────────────────────────

    def get_rows(self, start: int = 0, end: int = 99) -> Optional[str]:
        """Get content rows (raw XML)."""
        items = [{"start": str(start)}, {"end": str(end)}]
        return self._client.send_event(NetMethod.GET_ROWS, items=items)

    def play_row(self, row_index: int) -> Optional[str]:
        """Play a specific row."""
        return self._client.send_event(NetMethod.PLAY_ROW,
                                       items=[{"index": str(row_index)}])

    def browse_row(self, row_index: int) -> Optional[str]:
        """Browse into a row."""
        return self._client.send_event(NetMethod.BROWSE_ROW,
                                       items=[{"index": str(row_index)}])

    def browse_parent(self) -> Optional[str]:
        """Go up one level."""
        return self._client.send_event(NetMethod.BROWSE_PARENT)

    def go_home(self):
        """Return to home screen."""
        self._client.send_event(NetMethod.GO_HOME)

    # ── Favorites ────────────────────────────────────────────────

    def get_favorites(self) -> Optional[str]:
        """Get favorites list (raw XML)."""
        return self._client.send_event(NetMethod.GET_FAVORITES_ITEMS)

    def add_to_favorites(self, uri: str):
        """Add URI to favorites."""
        self._client.send_event(NetMethod.ADD_TO_FAVORITES,
                                items=[{"uri": uri}])

    def remove_from_favorites(self, uri: str):
        """Remove URI from favorites."""
        self._client.send_event(NetMethod.REMOVE_FROM_FAVORITES,
                                items=[{"uri": uri}])

    # ── Misc ─────────────────────────────────────────────────────

    def ping(self) -> bool:
        """Ping the device to check connectivity."""
        resp = self._client.send_event(NetMethod.PING)
        return resp is not None

    def get_mac_address(self) -> Optional[str]:
        """Get device MAC address."""
        resp = self._client.send_event(NetMethod.GET_MAC_ADDRESS)
        if resp:
            match = re.search(r'<mac>([0-9A-Fa-f:]+)</mac>', resp)
            if match:
                return match.group(1)
        return None


# ═══════════════════════════════════════════════════════════════════
# Airable REST API client — streaming service content
# ═══════════════════════════════════════════════════════════════════

class AirableClient:
    """Client for the airable cloud API (Deezer, Tidal, etc. content).

    The airable API is a REST/JSON API that provides content browsing
    for streaming services integrated into the MiND platform.
    """

    def __init__(self, base_url: str = AIRABLE_MIND2_BASE,
                 secret: str = AIRABLE_SECRET):
        self.base_url = base_url.rstrip('/')
        self.secret = secret
        self._token: Optional[str] = None
        self._session_data: Optional[Dict] = None

    def authenticate(self, username: str, password: str,
                     service: str = "deezer") -> bool:
        """Authenticate with the airable API.

        Args:
            username: service username/email
            password: service password
            service: streaming service name (deezer, tidal, etc.)

        Returns:
            True if authentication succeeded.
        """
        auth_url = f"{self.base_url}/authentication"
        payload = {
            "username": username,
            "password": password,
            "service": service,
        }

        try:
            req = Request(auth_url,
                          data=json.dumps(payload).encode('utf-8'),
                          headers={
                              'Content-Type': 'application/json',
                              'X-Airable-Secret': self.secret,
                          })
            with urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())
                self._token = data.get('token')
                self._session_data = data
                return self._token is not None
        except Exception as e:
            print(f"Airable authentication failed: {e}")
            return False

    def _request(self, path: str, params: Optional[Dict] = None) -> Optional[Dict]:
        """Make an authenticated request to the airable API."""
        if not self._token:
            print("Not authenticated")
            return None

        url = f"{self.base_url}/{path.lstrip('/')}"
        if params:
            url += '?' + urlencode(params)

        headers = {
            'Authorization': f'Bearer {self._token}',
            'X-Airable-Secret': self.secret,
        }

        try:
            req = Request(url, headers=headers)
            with urlopen(req, timeout=10) as resp:
                return json.loads(resp.read())
        except Exception as e:
            print(f"Airable request failed: {e}")
            return None

    def get_streaming_services(self) -> Optional[List[Dict]]:
        """Get list of available streaming services."""
        result = self._request("streaming")
        if result:
            return result.get('items', [])
        return None

    def get_directory(self, directory_id: str) -> Optional[Dict]:
        """Get content of a directory (album, playlist, etc.)."""
        return self._request(f"streaming/{directory_id}")

    def search(self, query: str, service: str = "deezer") -> Optional[List[Dict]]:
        """Search for content on a streaming service."""
        result = self._request("search", {"q": query, "service": service})
        if result:
            return result.get('items', [])
        return None

    def get_content(self, url: str) -> Optional[Dict]:
        """Fetch content from a specific URL."""
        # For external URLs, use direct request
        try:
            req = Request(url, headers={
                'Authorization': f'Bearer {self._token}',
            })
            with urlopen(req, timeout=10) as resp:
                return json.loads(resp.read())
        except Exception as e:
            print(f"Content fetch failed: {e}")
            return None


# ═══════════════════════════════════════════════════════════════════
# Convenience: discover & connect
# ═══════════════════════════════════════════════════════════════════

def discover_and_connect(timeout: int = 5) -> Optional[MoonController]:
    """Discover MiND devices and return controller for the first one found."""
    devices = discover_mind_devices(timeout)
    if not devices:
        print("No MiND devices found on network")
        return None

    device = devices[0]
    print(f"Found: {device['friendly_name']} ({device['model_name']}) "
          f"at {device['ip']}:{device['port']}")

    ctrl = MoonController(device['ip'], device['port'])
    if ctrl.connect():
        return ctrl
    else:
        print(f"Failed to connect to {device['ip']}")
        return None


# ═══════════════════════════════════════════════════════════════════
# CLI demo
# ═══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python moon_control.py <command> [args]")
        print("Commands: discover, play, pause, stop, next, prev, vol <n>, np")
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "discover":
        devices = discover_mind_devices()
        if devices:
            print(f"Found {len(devices)} device(s):")
            for i, d in enumerate(devices):
                print(f"  {i+1}. {d['friendly_name']} ({d['model_name']}) — {d['ip']}:{d['port']}")
        else:
            print("No MiND devices found")

    else:
        # Need IP - discover first
        devices = discover_mind_devices()
        if not devices:
            print("No devices found. Specify IP with --ip <addr>")
            sys.exit(1)

        ip = devices[0]['ip']
        port = devices[0]['port']

        ctrl = MoonController(ip, port)
        if not ctrl.connect():
            print("Connection failed")
            sys.exit(1)

        if cmd == "play":
            ctrl.play()
            print("▶ Play")
        elif cmd == "pause":
            ctrl.pause()
            print("⏸ Pause")
        elif cmd == "stop":
            ctrl.stop()
            print("⏹ Stop")
        elif cmd == "next":
            ctrl.next_track()
            print("⏭ Next")
        elif cmd == "prev":
            ctrl.previous_track()
            print("⏮ Previous")
        elif cmd == "vol":
            if len(sys.argv) > 2:
                ctrl.set_volume(int(sys.argv[2]))
                print(f"🔊 Volume: {sys.argv[2]}")
        elif cmd == "np":
            resp = ctrl.get_now_playing()
            print(resp or "No now-playing info")
        else:
            print(f"Unknown command: {cmd}")

        ctrl.disconnect()