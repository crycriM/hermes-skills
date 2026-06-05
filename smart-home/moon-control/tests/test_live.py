#!/usr/bin/env python3
"""Live integration test against the MOON 390 on the local network.

Run with: python3 tests/test_live.py

Tests are skipped if the device is unreachable (safe to run anytime).
"""
import asyncio
import sys
import os

# Add parent dir to path for import
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from moon_control import MoonDevice, discover

DEVICE_IP = "192.168.0.172"


async def can_reach(ip: str) -> bool:
    """Quick connectivity check."""
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(ip, 47561), timeout=2.0
        )
        writer.close()
        await writer.wait_closed()
        return True
    except Exception:
        return False


async def main():
    print("=== MOON 390 Live Integration Test ===\n")

    # Check connectivity
    if not await can_reach(DEVICE_IP):
        print(f"[SKIP] Cannot reach {DEVICE_IP}:47561 — device offline?")
        return

    device = MoonDevice(DEVICE_IP)
    passed = 0
    failed = 0
    skipped = 0

    async def check(name: str, condition: bool, detail: str = ""):
        nonlocal passed, failed
        if condition:
            print(f"  ✓ {name} {detail}")
            passed += 1
        else:
            print(f"  ✗ {name} {detail}")
            failed += 1

    try:
        # --- Transport info ---
        print("\n--- Transport Info ---")
        info = await device.get_transport_info()
        print(f"  State: {info.get('CurrentTransportState')}")
        print(f"  Status: {info.get('CurrentTransportStatus')}")
        await check(
            "get_transport_info returns state",
            "CurrentTransportState" in info,
        )

        # --- Volume ---
        print("\n--- Volume ---")
        vol = await device.get_volume()
        print(f"  Current volume: {vol}")
        await check("get_volume returns int", isinstance(vol, int) and 0 <= vol <= 100)

        # Save original volume to restore later
        orig_vol = vol

        # Set volume to test value (use something different from current)
        test_vol = 50 if orig_vol != 50 else 55
        await device.set_volume(test_vol)
        await asyncio.sleep(0.3)
        new_vol = await device.get_volume()
        await check(
            f"set_volume({test_vol})",
            new_vol == test_vol,
            f"(got {new_vol})",
        )

        # Restore original volume
        await device.set_volume(orig_vol)

        # --- Mute ---
        print("\n--- Mute ---")
        orig_mute = await device.get_mute()
        print(f"  Current mute: {orig_mute}")

        # Toggle mute and restore
        await device.set_mute(True)
        await asyncio.sleep(0.3)
        muted = await device.get_mute()
        await check("set_mute(True)", muted is True, f"(got {muted})")

        await device.set_mute(False)
        await asyncio.sleep(0.3)
        muted = await device.get_mute()
        await check("set_mute(False)", muted is False, f"(got {muted})")

        # Restore original mute state
        await device.set_mute(orig_mute)

        # --- Position / Media Info ---
        print("\n--- Position & Media Info ---")
        pos = await device.get_position_info()
        media = await device.get_media_info()
        print(f"  Track: {pos.get('Track', 'N/A')}")
        print(f"  Duration: {pos.get('TrackDuration', 'N/A')}")
        print(f"  URI: {media.get('CurrentURI', 'N/A')}")
        await check("get_position_info returns data", "Track" in pos)
        await check("get_media_info returns data", "CurrentURI" in media)

        # --- Now Playing ---
        print("\n--- Now Playing ---")
        np = await device.now_playing()
        print(f"  State: {np.transport_state}")
        print(f"  Title: {np.title or '(none)'}")
        print(f"  Artist: {np.artist or '(none)'}")
        print(f"  Duration: {np.duration}")
        print(f"  Position: {np.position}")
        await check("now_playing returns TrackInfo", np.transport_state != "")

        # --- Discovery ---
        print("\n--- SSDP Discovery ---")
        devices = await discover(timeout=3.0)
        print(f"  Found {len(devices)} device(s)")
        for d in devices:
            print(f"    {d.friendly_name} ({d.model_name}) at {d.ip}:{d.port}")
            print(f"    Services: {list(d.services.keys())}")
        await check("discover finds device", len(devices) >= 1)

        # --- Layer 2 stubs ---
        print("\n--- Layer 2 stubs ---")
        try:
            await device.play_mind_object("test_123")
            await check("play_mind_object (should fail)", False)
        except NotImplementedError:
            await check("play_mind_object raises NotImplementedError", True)

        try:
            await device.select_zone("zone1")
            await check("select_zone (should fail)", False)
        except NotImplementedError:
            await check("select_zone raises NotImplementedError", True)

    finally:
        await device.close()

    print(f"\n{'='*40}")
    print(f"Results: {passed} passed, {failed} failed, {skipped} skipped")
    if failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
