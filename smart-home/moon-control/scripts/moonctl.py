#!/usr/bin/env python3
"""Quick MOON 390 control from the terminal.

Usage:
    moonctl discover              # Find device on network
    moonctl status                # Show now-playing + volume
    moonctl play                  # Play
    moonctl pause                 # Pause
    moonctl stop                  # Stop
    moonctl next                  # Next track
    moonctl prev                  # Previous track
    moonctl vol 60                # Set volume to 60
    moonctl vol                   # Show current volume
    moonctl mute on|off           # Mute/unmute
    moonctl seek 00:01:30         # Seek to 1:30
    moonctl repeat all|one|track|off  # Set repeat mode

Device IP defaults to 192.168.0.172 or MOON_IP env var.
"""
import asyncio
import os
import sys
import argparse

# Look for moon_control.py in the skill root (parent of scripts/)
_skill_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _skill_dir)
from moon_control import MoonDevice, discover

DEFAULT_IP = os.environ.get("MOON_IP", "192.168.0.172")


async def cmd_discover():
    print("Discovering MOON devices...")
    devices = await discover(timeout=3.0)
    if not devices:
        print("No MOON devices found.")
        return
    for d in devices:
        print(f"  {d.friendly_name} — {d.model_name} ({d.manufacturer})")
        print(f"  IP: {d.ip}:{d.port}")
        print(f"  Services: {', '.join(d.services.keys())}")
        print()


async def cmd_status(ip: str):
    async with MoonDevice(ip) as dev:
        vol = await dev.get_volume()
        mute = await dev.get_mute()
        np = await dev.now_playing()

        print(f"MOON 390 at {ip}")
        print(f"  State:   {np.transport_state}")
        print(f"  Volume:  {vol}{' (MUTED)' if mute else ''}")
        if np.title:
            print(f"  Title:   {np.title}")
        if np.artist:
            print(f"  Artist:  {np.artist}")
        if np.album:
            print(f"  Album:   {np.album}")
        if np.duration:
            print(f"  Time:    {np.position} / {np.duration}")
        if np.uri:
            print(f"  URI:     {np.uri}")


async def cmd_transport(ip: str, action: str, **kwargs):
    async with MoonDevice(ip) as dev:
        if action == "play":
            await dev.play()
            print("Playing")
        elif action == "pause":
            await dev.pause()
            print("Paused")
        elif action == "stop":
            await dev.stop()
            print("Stopped")
        elif action == "next":
            await dev.next()
            print("Next track")
        elif action == "prev":
            await dev.previous()
            print("Previous track")
        elif action == "seek":
            target = kwargs.get("target", "0:00:00")
            await dev.seek(target)
            print(f"Seeked to {target}")
        elif action == "repeat":
            mode = kwargs.get("mode", "NORMAL")
            mode_map = {
                "off": "NORMAL",
                "all": "REPEAT_ALL",
                "one": "REPEAT_ONE",
                "track": "REPEAT_TRACK",
            }
            resolved = mode_map.get(mode, mode.upper())
            assert resolved is not None
            await dev.set_play_mode(resolved)
            print(f"Repeat mode: {mode}")


async def cmd_volume(ip: str, vol: str | None):
    async with MoonDevice(ip) as dev:
        if vol is None:
            v = await dev.get_volume()
            m = await dev.get_mute()
            print(f"Volume: {v}{' (muted)' if m else ''}")
        else:
            await dev.set_volume(int(vol))
            print(f"Volume set to {vol}")


async def cmd_mute(ip: str, state: str):
    async with MoonDevice(ip) as dev:
        muted = state.lower() in ("on", "true", "1", "yes")
        await dev.set_mute(muted)
        print(f"Mute: {'ON' if muted else 'OFF'}")


def main():
    parser = argparse.ArgumentParser(
        description="MOON 390 (MiND 2) network audio player control"
    )
    parser.add_argument("--ip", default=DEFAULT_IP, help="Device IP address")

    sub = parser.add_subparsers(dest="command")

    sub.add_parser("discover", help="Discover MOON devices via SSDP")
    sub.add_parser("status", help="Show now-playing and volume")

    # Transport
    sub.add_parser("play", help="Start/resume playback")
    sub.add_parser("pause", help="Pause playback")
    sub.add_parser("stop", help="Stop playback")
    sub.add_parser("next", help="Next track")
    p_prev = sub.add_parser("prev", help="Previous track")

    p_seek = sub.add_parser("seek", help="Seek to position")
    p_seek.add_argument("target", help="Position (e.g., 00:01:30)")

    p_repeat = sub.add_parser("repeat", help="Set repeat mode")
    p_repeat.add_argument(
        "mode", choices=["off", "all", "one", "track"], help="Repeat mode"
    )

    # Volume
    p_vol = sub.add_parser("vol", help="Get or set volume (0-100)")
    p_vol.add_argument("level", nargs="?", help="Volume level (omit to read)")

    # Mute
    p_mute = sub.add_parser("mute", help="Mute/unmute")
    p_mute.add_argument("state", choices=["on", "off"], help="Mute state")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    ip = args.ip

    if args.command == "discover":
        asyncio.run(cmd_discover())
    elif args.command == "status":
        asyncio.run(cmd_status(ip))
    elif args.command in ("play", "pause", "stop", "next", "prev"):
        asyncio.run(cmd_transport(ip, args.command))
    elif args.command == "seek":
        asyncio.run(cmd_transport(ip, "seek", target=args.target))
    elif args.command == "repeat":
        asyncio.run(cmd_transport(ip, "repeat", mode=args.mode))
    elif args.command == "vol":
        asyncio.run(cmd_volume(ip, getattr(args, "level", None)))
    elif args.command == "mute":
        asyncio.run(cmd_mute(ip, args.state))


if __name__ == "__main__":
    main()
