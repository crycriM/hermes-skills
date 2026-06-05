"""
Moon Control Skill — Remote control for MOON 390 (MiND 2) network audio player.

Uses standard UPnP AVTransport + RenderingControl SOAP services (Layer 1).
The device is a Rygel-based MediaRenderer discovered via SSDP.

For streaming service content (Deezer/Tidal), the device uses the airable cloud
API at https://1080906287.airable.io. SetAVTransportURI with an airable: URI
and the device fetches the stream directly. This requires the device to have
an active airable session (established via the MiND app or programmatically).

Usage:
  from moon_control import MoonDevice, discover
  device = MoonDevice("192.168.0.172")
  device.play()
  device.set_volume(60)
  info = device.now_playing()
  device.close()
"""

import socket
import time
import re
from typing import Dict, List, Optional, Tuple, NamedTuple
from urllib.request import urlopen, Request
from urllib.error import URLError
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

# ═══════════════════════════════════════════════════════
# Constants
# ═══════════════════════════════════════════════════════

UPNP_AV_TRANSPORT = "urn:schemas-upnp-org:service:AVTransport:2"
UPNP_RENDERING_CONTROL = "urn:schemas-upnp-org:service:RenderingControl:2"
SSDP_ST = "urn:schemas-upnp-org:device:MediaRenderer:1"
SSDP_MULTICAST = ("239.255.255.250", 1900)

AIRABLE_BASE = "https://1080906287.airable.io"
AIRABLE_SECRET = "tC3AhgFCLZYMJOaEo9HBqrLwqG3kuUBa"


# ═══════════════════════════════════════════════════════
# Data classes
# ═══════════════════════════════════════════════════════

@dataclass
class TrackInfo:
    transport_state: str = ""
    title: str = ""
    artist: str = ""
    album: str = ""
    duration: str = ""
    position: str = ""
    uri: str = ""
    nr_tracks: int = 0
    metadata: str = ""

@dataclass
class DeviceInfo:
    ip: str
    port: int
    friendly_name: str = "Unknown"
    model_name: str = "Unknown"
    manufacturer: str = "Unknown"
    serial_number: str = ""
    udn: str = ""
    description_url: str = ""
    av_transport_url: str = ""
    rendering_control_url: str = ""
    services: Dict[str, str] = field(default_factory=dict)


# ═══════════════════════════════════════════════════════
# SSDP Discovery
# ═══════════════════════════════════════════════════════

def discover(timeout: float = 3.0) -> List[DeviceInfo]:
    """Discover MiND devices via SSDP and return device info."""
    M_SEARCH = (
        b'M-SEARCH * HTTP/1.1\r\n'
        b'HOST: 239.255.255.250:1900\r\n'
        b'MAN: "ssdp:discover"\r\n'
        b'ST: ' + SSDP_ST.encode() + b'\r\n'
        b'MX: 2\r\n'
        b'\r\n'
    )

    seen = set()
    devices = []

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.settimeout(timeout)
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
        sock.sendto(M_SEARCH, SSDP_MULTICAST)

        start = time.time()
        while time.time() - start < timeout:
            try:
                data, addr = sock.recvfrom(4096)
                ip = addr[0]
                if ip in seen:
                    continue
                seen.add(ip)

                resp = data.decode('utf-8', errors='ignore')
                location = None
                for line in resp.split('\r\n'):
                    if line.upper().startswith('LOCATION:'):
                        location = line.split(':', 1)[1].strip()
                        break

                if location:
                    dev = _fetch_description(location, ip)
                    if dev:
                        devices.append(dev)

            except socket.timeout:
                break
            except Exception:
                continue

        sock.close()
    except Exception as e:
        print(f"SSDP error: {e}")

    return devices


def _fetch_description(location: str, ip: str) -> Optional[DeviceInfo]:
    """Fetch and parse UPnP device description XML."""
    try:
        with urlopen(location, timeout=3) as resp:
            root = ET.fromstring(resp.read())
    except Exception:
        return None

    ns = {
        '': 'urn:schemas-upnp-org:device-1-0',
        'dlna': 'urn:schemas-dlna-org:device-1-0',
    }

    device_el = root.find('.//device', ns)
    if device_el is None:
        return None

    def find_text(tag):
        el = device_el.find(tag, ns)
        return el.text if el is not None and el.text else ""

    dev = DeviceInfo(
        ip=ip,
        port=_extract_port(location),
        friendly_name=find_text('friendlyName'),
        model_name=find_text('modelName'),
        manufacturer=find_text('manufacturer'),
        serial_number=find_text('serialNumber'),
        udn=find_text('UDN'),
        description_url=location,
    )

    # Find service control URLs
    base = location.rsplit('/', 1)[0]
    service_list = device_el.find('serviceList', ns)
    if service_list is not None:
        for svc in service_list.findall('service', ns):
            stype = find_text_in(svc, 'serviceType', ns)
            curl = find_text_in(svc, 'controlURL', ns)
            if stype and curl:
                full_url = curl if curl.startswith('http') else base + curl
                dev.services[stype] = full_url

    # Convenience shortcuts
    for key, stype in [('av_transport_url', UPNP_AV_TRANSPORT),
                       ('rendering_control_url', UPNP_RENDERING_CONTROL)]:
        if stype in dev.services:
            setattr(dev, key, dev.services[stype])
        # Also try version 1
        stype_v1 = stype.replace(':2', ':1')
        if stype_v1 in dev.services:
            setattr(dev, key, dev.services[stype_v1])

    return dev


def _extract_port(url: str) -> int:
    """Extract port from URL."""
    url = url.replace('http://', '')
    host = url.split('/')[0]
    if ':' in host:
        return int(host.split(':')[1])
    return 80


def find_text_in(el, tag, ns):
    child = el.find(tag, ns)
    return child.text if child is not None and child.text else ""


# ═══════════════════════════════════════════════════════
# UPnP SOAP client
# ═══════════════════════════════════════════════════════

class MoonDevice:
    """Control a MOON 390 via UPnP AVTransport + RenderingControl."""

    def __init__(self, ip: str, port: int = 47561):
        self.ip = ip
        self.port = port
        self.base = f"http://{ip}:{port}"

        # Discover control URLs from device description
        dev = self._get_device_info()
        self.avt_url = dev.av_transport_url or f"{self.base}/Control/LibRygelRenderer/RygelAVTransport"
        self.rcs_url = dev.rendering_control_url or f"{self.base}/Control/LibRygelRenderer/RygelRenderingControl"
        self.friendly_name = dev.friendly_name
        self.model_name = dev.model_name
        self._session = None

    def _get_device_info(self) -> DeviceInfo:
        """Fetch device description and return DeviceInfo."""
        # Try common locations
        candidates = [
            f"{self.base}/4a4012fc-86dd-4ee2-bd9b-064a08e99c4b.xml",
            f"{self.base}/description.xml",
        ]
        for url in candidates:
            try:
                dev = _fetch_description(url, self.ip)
                if dev and dev.services:
                    return dev
            except Exception:
                continue
        return DeviceInfo(ip=self.ip, port=self.port)

    # ── Low-level SOAP ──────────────────────────────────

    def _soap(self, service_url: str, service_type: str,
              action: str, body: str) -> str:
        """Send SOAP request and return response XML string."""
        ns = service_type.replace(':2', ':1') if ':2' in service_type else service_type
        envelope = (
            '<?xml version="1.0"?>'
            '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" '
            's:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">'
            '<s:Body>' + body + '</s:Body>'
            '</s:Envelope>'
        )
        headers = {
            'Content-Type': 'text/xml; charset="utf-8"',
            'SOAPACTION': f'"{ns}#{action}"',
        }
        req = Request(service_url, envelope.encode(), headers)
        try:
            with urlopen(req, timeout=5) as r:
                return r.read().decode()
        except Exception as e:
            raise RuntimeError(f"SOAP {action} failed: {e}")

    def _avt(self, action: str, body: str) -> str:
        return self._soap(self.avt_url, UPNP_AV_TRANSPORT, action, body)

    def _rcs(self, action: str, body: str) -> str:
        return self._soap(self.rcs_url, UPNP_RENDERING_CONTROL, action, body)

    # ── Transport Control ───────────────────────────────

    def play(self):
        """Start or resume playback."""
        body = (
            f'<u:Play xmlns:u="{UPNP_AV_TRANSPORT}">'
            '<InstanceID>0</InstanceID><Speed>1</Speed>'
            '</u:Play>'
        )
        self._avt("Play", body)

    def pause(self):
        """Pause playback."""
        body = (
            f'<u:Pause xmlns:u="{UPNP_AV_TRANSPORT}">'
            '<InstanceID>0</InstanceID>'
            '</u:Pause>'
        )
        self._avt("Pause", body)

    def stop(self):
        """Stop playback."""
        body = (
            f'<u:Stop xmlns:u="{UPNP_AV_TRANSPORT}">'
            '<InstanceID>0</InstanceID>'
            '</u:Stop>'
        )
        self._avt("Stop", body)

    def next(self):
        """Skip to next track."""
        body = (
            f'<u:Next xmlns:u="{UPNP_AV_TRANSPORT}">'
            '<InstanceID>0</InstanceID>'
            '</u:Next>'
        )
        self._avt("Next", body)

    def previous(self):
        """Go to previous track."""
        body = (
            f'<u:Previous xmlns:u="{UPNP_AV_TRANSPORT}">'
            '<InstanceID>0</InstanceID>'
            '</u:Previous>'
        )
        self._avt("Previous", body)

    def seek(self, target: str):
        """Seek to position. Format: HH:MM:SS or track number."""
        body = (
            f'<u:Seek xmlns:u="{UPNP_AV_TRANSPORT}">'
            '<InstanceID>0</InstanceID>'
            '<Unit>REL_TIME</Unit>'
            f'<Target>{target}</Target>'
            '</u:Seek>'
        )
        self._avt("Seek", body)

    # ── Queue / URI ─────────────────────────────────────

    def set_uri(self, uri: str, metadata: str = ""):
        """Set the current playback URI (e.g., a airable: Deezer URI)."""
        body = (
            f'<u:SetAVTransportURI xmlns:u="{UPNP_AV_TRANSPORT}">'
            '<InstanceID>0</InstanceID>'
            f'<CurrentURI>{uri}</CurrentURI>'
            f'<CurrentURIMetaData>{metadata}</CurrentURIMetaData>'
            '</u:SetAVTransportURI>'
        )
        self._avt("SetAVTransportURI", body)

    def play_uri(self, uri: str, metadata: str = ""):
        """Set URI and start playback."""
        self.set_uri(uri, metadata)
        self.play()

    def play_deezer_track(self, track_id: int):
        """Play a Deezer track by ID via airable."""
        uri = f"airable:{AIRABLE_BASE}/deezer/play/mp3/128/{track_id}"
        self.play_uri(uri)

    def play_deezer_playlist(self, playlist_id: int):
        """Play a Deezer playlist by ID via airable."""
        uri = f"airable:{AIRABLE_BASE}/deezer/playlist/{playlist_id}"
        self.play_uri(uri)

    # ── Volume / Mute ───────────────────────────────────

    def set_volume(self, volume: int):
        """Set volume (0-100)."""
        body = (
            f'<u:SetVolume xmlns:u="{UPNP_RENDERING_CONTROL}">'
            '<InstanceID>0</InstanceID>'
            '<Channel>Master</Channel>'
            f'<DesiredVolume>{volume}</DesiredVolume>'
            '</u:SetVolume>'
        )
        self._rcs("SetVolume", body)

    def get_volume(self) -> int:
        """Get current volume."""
        body = (
            f'<u:GetVolume xmlns:u="{UPNP_RENDERING_CONTROL}">'
            '<InstanceID>0</InstanceID>'
            '<Channel>Master</Channel>'
            '</u:GetVolume>'
        )
        resp = self._rcs("GetVolume", body)
        m = re.search(r'<CurrentVolume>(\d+)</CurrentVolume>', resp)
        return int(m.group(1)) if m else 0

    def set_mute(self, muted: bool):
        """Mute or unmute."""
        body = (
            f'<u:SetMute xmlns:u="{UPNP_RENDERING_CONTROL}">'
            '<InstanceID>0</InstanceID>'
            '<Channel>Master</Channel>'
            f'<DesiredMute>{"1" if muted else "0"}</DesiredMute>'
            '</u:SetMute>'
        )
        self._rcs("SetMute", body)

    def get_mute(self) -> bool:
        """Get mute state."""
        body = (
            f'<u:GetMute xmlns:u="{UPNP_RENDERING_CONTROL}">'
            '<InstanceID>0</InstanceID>'
            '<Channel>Master</Channel>'
            '</u:GetMute>'
        )
        resp = self._rcs("GetMute", body)
        m = re.search(r'<CurrentMute>(\d)</CurrentMute>', resp)
        return bool(int(m.group(1))) if m else False

    # ── Now Playing ─────────────────────────────────────

    def get_transport_info(self) -> Dict[str, str]:
        """Get transport state."""
        body = (
            f'<u:GetTransportInfo xmlns:u="{UPNP_AV_TRANSPORT}">'
            '<InstanceID>0</InstanceID>'
            '</u:GetTransportInfo>'
        )
        resp = self._avt("GetTransportInfo", body)
        return {
            'CurrentTransportState':
                _re_first(r'<CurrentTransportState>(.*?)</', resp) or "",
            'CurrentTransportStatus':
                _re_first(r'<CurrentTransportStatus>(.*?)</', resp) or "",
            'CurrentSpeed':
                _re_first(r'<CurrentSpeed>(.*?)</', resp) or "",
        }

    def get_media_info(self) -> Dict[str, str]:
        """Get current media info."""
        body = (
            f'<u:GetMediaInfo xmlns:u="{UPNP_AV_TRANSPORT}">'
            '<InstanceID>0</InstanceID>'
            '</u:GetMediaInfo>'
        )
        resp = self._avt("GetMediaInfo", body)
        return {
            'NrTracks': _re_first(r'<NrTracks>(.*?)</', resp) or "0",
            'MediaDuration': _re_first(r'<MediaDuration>(.*?)</', resp) or "",
            'CurrentURI': _re_first(r'<CurrentURI>(.*?)</', resp) or "",
            'CurrentURIMetaData': _re_first(r'<CurrentURIMetaData>(.*?)</', resp) or "",
            'NextURI': _re_first(r'<NextURI>(.*?)</', resp) or "",
        }

    def get_position_info(self) -> Dict[str, str]:
        """Get playback position."""
        body = (
            f'<u:GetPositionInfo xmlns:u="{UPNP_AV_TRANSPORT}">'
            '<InstanceID>0</InstanceID>'
            '</u:GetPositionInfo>'
        )
        resp = self._avt("GetPositionInfo", body)
        return {
            'Track': _re_first(r'<Track>(.*?)</', resp) or "0",
            'TrackDuration': _re_first(r'<TrackDuration>(.*?)</', resp) or "",
            'RelTime': _re_first(r'<RelTime>(.*?)</', resp) or "",
            'AbsTime': _re_first(r'<AbsTime>(.*?)</', resp) or "",
        }

    def get_transport_settings(self) -> Dict[str, str]:
        """Get repeat/shuffle mode."""
        body = (
            f'<u:GetTransportSettings xmlns:u="{UPNP_AV_TRANSPORT}">'
            '<InstanceID>0</InstanceID>'
            '</u:GetTransportSettings>'
        )
        resp = self._avt("GetTransportSettings", body)
        return {
            'PlayMode': _re_first(r'<PlayMode>(.*?)</', resp) or "",
            'RecQualityMode': _re_first(r'<RecQualityMode>(.*?)</', resp) or "",
        }

    def set_play_mode(self, mode: str):
        """Set repeat/shuffle mode. Mode: NORMAL, REPEAT_ALL, REPEAT_ONE, SHUFFLE."""
        body = (
            f'<u:SetPlayMode xmlns:u="{UPNP_AV_TRANSPORT}">'
            '<InstanceID>0</InstanceID>'
            f'<NewPlayMode>{mode}</NewPlayMode>'
            '</u:SetPlayMode>'
        )
        self._avt("SetPlayMode", body)

    def now_playing(self) -> TrackInfo:
        """Get comprehensive now-playing info."""
        transport = self.get_transport_info()
        media = self.get_media_info()
        position = self.get_position_info()

        info = TrackInfo(
            transport_state=transport.get('CurrentTransportState', ''),
            uri=media.get('CurrentURI', ''),
            nr_tracks=int(media.get('NrTracks', '0')),
            duration=position.get('TrackDuration', ''),
            position=position.get('RelTime', ''),
            metadata=media.get('CurrentURIMetaData', ''),
        )

        # Parse DIDL-Lite metadata if available
        meta_xml = info.metadata
        if meta_xml:
            try:
                root = ET.fromstring(meta_xml)
                ns_dc = 'http://purl.org/dc/elements/1.1/'
                ns_upnp = 'urn:schemas-upnp-org:metadata-1-0/upnp/'
                title_el = root.find(f'.//{{{ns_dc}}}title')
                artist_el = root.find(f'.//{{{ns_upnp}}}artist')
                album_el = root.find(f'.//{{{ns_upnp}}}album')
                info.title = title_el.text if title_el is not None and title_el.text else ""
                info.artist = artist_el.text if artist_el is not None and artist_el.text else ""
                info.album = album_el.text if album_el is not None and album_el.text else ""
            except ET.ParseError:
                pass

        return info

    # ── Lifecycle ───────────────────────────────────────

    def close(self):
        """Clean up."""
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def _re_first(pattern, text):
    m = re.search(pattern, text)
    return m.group(1) if m else None


# ═══════════════════════════════════════════════════════
# Airable REST client (for content browse/search)
# ═══════════════════════════════════════════════════════

import json as _json


class AirableClient:
    """Client for the airable cloud API (Deezer/Tidal content browse).

    The device needs an active airable session to stream content.
    This client can browse and search, but playback requires
    MoonDevice.play_deezer_track() or play_deezer_playlist().
    """

    def __init__(self, base_url: str = AIRABLE_BASE,
                 secret: str = AIRABLE_SECRET):
        self.base_url = base_url.rstrip('/')
        self.secret = secret
        self._token: Optional[str] = None

    def authenticate(self, username: str, password: str,
                     service: str = "deezer") -> bool:
        """Authenticate with airable."""
        url = f"{self.base_url}/authentication"
        payload = _json.dumps({
            "username": username,
            "password": password,
            "service": service,
        }).encode()
        headers = {
            'Content-Type': 'application/json',
            'X-Airable-Secret': self.secret,
        }
        try:
            req = Request(url, payload, headers)
            with urlopen(req, timeout=10) as resp:
                data = _json.loads(resp.read())
                self._token = data.get('token')
                return self._token is not None
        except Exception as e:
            print(f"Airable auth failed: {e}")
            return False

    def search(self, query: str, service: str = "deezer") -> List[Dict]:
        """Search for content."""
        if not self._token:
            return []
        url = f"{self.base_url}/search?q={query}&service={service}"
        headers = {'Authorization': f'Bearer {self._token}'}
        try:
            req = Request(url, headers=headers)
            with urlopen(req, timeout=10) as resp:
                data = _json.loads(resp.read())
                return data.get('items', [])
        except Exception as e:
            print(f"Search failed: {e}")
            return []


# ═══════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: moon_control.py discover|status|play|pause|stop|next|prev|vol [n]|mute [on|off]")
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "discover":
        devices = discover()
        for i, d in enumerate(devices):
            print(f"{i+1}. {d.friendly_name} ({d.model_name}) — {d.ip}:{d.port}")
        if not devices:
            print("No devices found")

    else:
        devices = discover()
        if not devices:
            print("No devices found")
            sys.exit(1)
        dev = devices[0]
        device = MoonDevice(dev.ip, dev.port)
        print(f"Connected: {dev.friendly_name} ({dev.model_name})")

        if cmd == "status":
            np = device.now_playing()
            vol = device.get_volume()
            mute = device.get_mute()
            print(f"  State:   {np.transport_state}")
            print(f"  Volume:  {vol}{' (MUTED)' if mute else ''}")
            if np.title:
                print(f"  Title:   {np.title}")
                print(f"  Artist:  {np.artist}")
                print(f"  Time:    {np.position} / {np.duration}")
        elif cmd == "play":
            device.play()
            print("▶ Playing")
        elif cmd == "pause":
            device.pause()
            print("⏸ Paused")
        elif cmd == "stop":
            device.stop()
            print("⏹ Stopped")
        elif cmd == "next":
            device.next()
            print("⏭ Next")
        elif cmd == "prev":
            device.previous()
            print("⏮ Previous")
        elif cmd == "vol":
            if len(sys.argv) > 2:
                device.set_volume(int(sys.argv[2]))
            print(f"Volume: {device.get_volume()}")
        elif cmd == "mute":
            state = sys.argv[2] if len(sys.argv) > 2 else "toggle"
            if state in ("on", "1"):
                device.set_mute(True)
            elif state in ("off", "0"):
                device.set_mute(False)
            print(f"Mute: {device.get_mute()}")

        device.close()