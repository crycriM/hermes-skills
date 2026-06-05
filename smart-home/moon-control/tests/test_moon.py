"""Tests for moon_control — MOON 390 MiND 2 UPnP control module."""
import pytest
import xml.etree.ElementTree as ET
from unittest.mock import AsyncMock, patch, MagicMock


# ---------------------------------------------------------------------------
# RED phase: test SOAP helpers (pure functions, no device needed)
# ---------------------------------------------------------------------------

# We'll test the module after it exists. For now these tests WILL FAIL
# because moon_control.py doesn't exist yet.


def test_build_soap_envelope_avtransport():
    """Build a valid SOAP envelope for GetTransportInfo."""
    from moon_control import _build_soap_envelope

    body_xml = (
        '<u:GetTransportInfo xmlns:u="urn:schemas-upnp-org:service:AVTransport:2">'
        "<InstanceID>0</InstanceID>"
        "</u:GetTransportInfo>"
    )
    envelope = _build_soap_envelope(
        "urn:schemas-upnp-org:service:AVTransport:2", "GetTransportInfo", body_xml
    )

    root = ET.fromstring(envelope)
    # Verify SOAP structure
    body = root.find("{http://schemas.xmlsoap.org/soap/envelope/}Body")
    assert body is not None
    action_elem = body.find(
        "{urn:schemas-upnp-org:service:AVTransport:2}GetTransportInfo"
    )
    assert action_elem is not None
    instance = action_elem.find("InstanceID")
    assert instance is not None
    assert instance.text == "0"


def test_build_soap_envelope_rendering_control():
    """Build a valid SOAP envelope for SetVolume."""
    from moon_control import _build_soap_envelope

    body_xml = (
        '<u:SetVolume xmlns:u="urn:schemas-upnp-org:service:RenderingControl:2">'
        "<InstanceID>0</InstanceID>"
        "<Channel>Master</Channel>"
        "<DesiredVolume>42</DesiredVolume>"
        "</u:SetVolume>"
    )
    envelope = _build_soap_envelope(
        "urn:schemas-upnp-org:service:RenderingControl:2", "SetVolume", body_xml
    )

    root = ET.fromstring(envelope)
    body = root.find("{http://schemas.xmlsoap.org/soap/envelope/}Body")
    action_elem = body.find(
        "{urn:schemas-upnp-org:service:RenderingControl:2}SetVolume"
    )
    assert action_elem is not None
    assert action_elem.find("DesiredVolume").text == "42"


def test_parse_transport_info_response():
    """Parse a real GetTransportInfo SOAP response."""
    from moon_control import _parse_soap_response

    response_xml = (
        '<?xml version="1.0"?>'
        '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" '
        's:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">'
        "<s:Body>"
        '<u:GetTransportInfoResponse xmlns:u="urn:schemas-upnp-org:service:AVTransport:2">'
        "<CurrentTransportState>PLAYING</CurrentTransportState>"
        "<CurrentTransportStatus>OK</CurrentTransportStatus>"
        "<CurrentSpeed>1</CurrentSpeed>"
        "</u:GetTransportInfoResponse>"
        "</s:Body>"
        "</s:Envelope>"
    )
    result = _parse_soap_response(response_xml)

    assert result["CurrentTransportState"] == "PLAYING"
    assert result["CurrentTransportStatus"] == "OK"
    assert result["CurrentSpeed"] == "1"


def test_parse_volume_response():
    """Parse a GetVolume SOAP response."""
    from moon_control import _parse_soap_response

    response_xml = (
        '<?xml version="1.0"?>'
        '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" '
        's:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">'
        "<s:Body>"
        '<u:GetVolumeResponse xmlns:u="urn:schemas-upnp-org:service:RenderingControl:2">'
        "<CurrentVolume>75</CurrentVolume>"
        "</u:GetVolumeResponse>"
        "</s:Body>"
        "</s:Envelope>"
    )
    result = _parse_soap_response(response_xml)
    assert result["CurrentVolume"] == "75"


def test_parse_empty_soap_fault():
    """SOAP fault returns empty dict."""
    from moon_control import _parse_soap_response

    fault_xml = (
        '<?xml version="1.0"?>'
        '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/">'
        "<s:Body>"
        "<s:Fault>"
        "<faultcode>s:Client</faultcode>"
        "<faultstring>UPnPError</faultstring>"
        "</s:Fault>"
        "</s:Body>"
        "</s:Envelope>"
    )
    result = _parse_soap_response(fault_xml)
    assert result == {}


def test_make_soap_action_header():
    """Build the SOAPACTION header string."""
    from moon_control import _make_soap_action

    header = _make_soap_action(
        "urn:schemas-upnp-org:service:AVTransport:2", "Play"
    )
    assert header == '"urn:schemas-upnp-org:service:AVTransport:2#Play"'


# ---------------------------------------------------------------------------
# Device class tests (mock HTTP)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_moon_device_get_transport_info():
    """MoonDevice.get_transport_info sends correct SOAP and parses response."""
    from moon_control import MoonDevice

    device = MoonDevice("192.168.0.172", port=47561)

    mock_response = AsyncMock()
    mock_response.text = (
        '<?xml version="1.0"?>'
        '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" '
        's:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">'
        "<s:Body>"
        '<u:GetTransportInfoResponse xmlns:u="urn:schemas-upnp-org:service:AVTransport:2">'
        "<CurrentTransportState>PLAYING</CurrentTransportState>"
        "<CurrentTransportStatus>OK</CurrentTransportStatus>"
        "<CurrentSpeed>1</CurrentSpeed>"
        "</u:GetTransportInfoResponse>"
        "</s:Body>"
        "</s:Envelope>"
    )
    mock_response.raise_for_status = MagicMock()

    with patch.object(device._client, "post", return_value=mock_response) as mock_post:
        result = await device.get_transport_info()
        mock_post.assert_called_once()
        assert result["CurrentTransportState"] == "PLAYING"


@pytest.mark.asyncio
async def test_moon_device_set_volume():
    """MoonDevice.set_volume sends correct SOAP."""
    from moon_control import MoonDevice

    device = MoonDevice("192.168.0.172", port=47561)

    mock_response = AsyncMock()
    mock_response.text = (
        '<?xml version="1.0"?>'
        '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" '
        's:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">'
        "<s:Body>"
        '<u:SetVolumeResponse xmlns:u="urn:schemas-upnp-org:service:RenderingControl:2">'
        "</u:SetVolumeResponse>"
        "</s:Body>"
        "</s:Envelope>"
    )
    mock_response.raise_for_status = MagicMock()

    with patch.object(device._client, "post", return_value=mock_response) as mock_post:
        await device.set_volume(60)
        call_args = mock_post.call_args
        # Verify SOAP body contains DesiredVolume
        assert "60" in call_args[1]["content"]


@pytest.mark.asyncio
async def test_moon_device_mute():
    """MoonDevice.set_mute sends correct SOAP."""
    from moon_control import MoonDevice

    device = MoonDevice("192.168.0.172", port=47561)

    mock_response = AsyncMock()
    mock_response.text = (
        '<?xml version="1.0"?>'
        '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" '
        's:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">'
        "<s:Body>"
        '<u:SetMuteResponse xmlns:u="urn:schemas-upnp-org:service:RenderingControl:2">'
        "</u:SetMuteResponse>"
        "</s:Body>"
        "</s:Envelope>"
    )
    mock_response.raise_for_status = MagicMock()

    with patch.object(device._client, "post", return_value=mock_response) as mock_post:
        await device.set_mute(True)
        content = mock_post.call_args[1]["content"]
        assert "1" in content or "true" in content.lower()
