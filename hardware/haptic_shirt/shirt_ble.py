#!/usr/bin/env python3
"""Bluetooth transport for the shirt. Requires .blevenv's bleak installation."""
import argparse
import asyncio
import json
import time
import sys

from bleak import BleakClient, BleakScanner
from bleak.exc import BleakError
from shirt import PRESETS, amplitude_for
from shirt_signals import MEANINGS, plan
from shirt_prompt import render
from playback_control import Playback, LOOP_SECONDS, duration, request_stop, playback_idle

SERVICE = "87080001-54bc-4e44-b9e6-003e6b048f80"
RX = "87080002-54bc-4e44-b9e6-003e6b048f80"
STATUS = "87080003-54bc-4e44-b9e6-003e6b048f80"
NAME = "Eve-Shirt-615876"


class WirelessShirt:
    def __init__(self, pairing=False):
        self.client = None
        self.pairing = pairing

    async def __aenter__(self):
        device = await BleakScanner.find_device_by_filter(
            lambda d, a: a.local_name == NAME and SERVICE in a.service_uuids,
            timeout=8, service_uuids=[SERVICE])
        if device is None:
            raise RuntimeError("shirt is not advertising")
        self.client = BleakClient(device, timeout=30)
        try:
            await self.client.connect()
            await self.status(pairing=self.pairing)
            await self.command("status")
        except BaseException:
            await self.client.disconnect()
            raise
        return self

    async def __aexit__(self, *_):
        await self.client.disconnect()

    async def status(self, pairing=False):
        if pairing and sys.platform == "darwin":
            # Bleak 3.1.0 discards read_gatt_char(timeout=...) on macOS.
            # Its pinned CoreBluetooth delegate exposes the actual timeout.
            characteristic = self.client.services.get_characteristic(STATUS)
            data = await self.client._backend._delegate.read_characteristic(
                characteristic.obj, use_cached=False, timeout=300)
        else:
            data = await asyncio.wait_for(self.client.read_gatt_char(STATUS), 3)
        return json.loads(bytes(data))

    async def command(self, text):
        if not text or len(text.encode()) >= 100 or "\n" in text or "\r" in text:
            raise ValueError("command must be a single line under 100 bytes")
        before = await self.status()
        await self.client.write_gatt_char(RX, text.encode(), response=True)
        end = time.monotonic()+3
        while time.monotonic() < end:
            result = await self.status()
            if result["seq"] != before["seq"]:
                if not result["ok"]:
                    raise RuntimeError("shirt refused command; outputs stopped")
                return result
            await asyncio.sleep(0.02)
        raise RuntimeError("shirt did not acknowledge command")

    async def context(self):
        state = await self.command("status")
        if not state["ready"]:
            return ""
        return render(state, fresh=True)

    async def pattern(self, pair, name, seconds, peak, *, loop=False):
        if pair not in ("chest", "back", "both") or name not in PRESETS:
            raise ValueError("unknown pair or pattern")
        seconds = duration(seconds, loop)
        if not 0 <= peak <= 20:
            raise ValueError("peak must be 0..20")
        pairs = ("chest", "back") if pair == "both" else (pair,)
        levels, interval = PRESETS[name]
        step = interval/1000
        with Playback() as playback:
            await self.command("stop")
            start = time.monotonic()
            end = start + seconds
            try:
                while time.monotonic() < end and not playback.cancelled():
                    index = int((time.monotonic()-start)/step + 1e-7)
                    amplitude = amplitude_for(levels[index % len(levels)], peak)
                    for target in pairs:
                        remaining = int((end-time.monotonic())*1000)
                        if remaining <= 0 or playback.cancelled(): break
                        await self.command(f"level {target} {amplitude} {min(2000,interval+250,remaining)}")
                    until = min(end, start+(index+1)*step)
                    while time.monotonic() < until and not playback.cancelled():
                        await asyncio.sleep(min(.05, until-time.monotonic()))
            finally:
                if self.client.is_connected: await self.command("stop")

    async def signal(self, name, side, pair, peak, *, loop=False):
        state = await self.command("status")
        channels = dict(zip(state["zones"], state["channels"]))
        events, cycle_seconds = plan(name, channels, side, pair, peak)
        with Playback() as playback:
            await self.command("stop")
            start = time.monotonic()
            end = start + (LOOP_SECONDS if loop else cycle_seconds)
            cycle_start = start
            try:
                while cycle_start < end and not playback.cancelled():
                    for at, cmd in events:
                        due = cycle_start + at
                        if due >= end or playback.cancelled(): break
                        while time.monotonic() < due and not playback.cancelled():
                            await asyncio.sleep(min(.05, due-time.monotonic()))
                        if playback.cancelled(): break
                        if time.monotonic()-due > .2:
                            raise RuntimeError("signal timing missed; stopping rather than catching up")
                        remaining = int((end-time.monotonic())*1000)
                        if remaining <= 0: break
                        parts = cmd.split()
                        parts[3] = str(min(int(parts[3]), remaining))
                        await self.command(" ".join(parts))
                    until = min(end, cycle_start+cycle_seconds)
                    while time.monotonic() < until and not playback.cancelled():
                        await asyncio.sleep(min(.05, until-time.monotonic()))
                    if not loop or time.monotonic() >= end or playback.cancelled(): break
                    await self.command("stop")
                    cycle_start = time.monotonic()
            finally:
                if self.client.is_connected: await self.command("stop")


async def run(args):
    if args.action == "scan":
        device = await BleakScanner.find_device_by_filter(
            lambda d, a: a.local_name == NAME and SERVICE in a.service_uuids,
            timeout=8, service_uuids=[SERVICE])
        print("shirt found" if device else "shirt not found")
        return
    if args.action == "stop":
        request_stop()
        until = time.monotonic()+4
        while not playback_idle():
            if time.monotonic() >= until: raise RuntimeError("Playback is still stopping")
            await asyncio.sleep(.05)
    async with WirelessShirt(pairing=args.action == "pair") as shirt:
        if args.action == "pair":
            print(json.dumps(await shirt.command("status")))
        elif args.action == "context":
            print(await shirt.context())
        elif args.action == "signal":
            await shirt.signal(args.name, args.side, args.pair, args.peak, loop=args.loop)
        elif args.action == "pattern":
            await shirt.pattern(args.pair, args.name, args.seconds, args.peak, loop=args.loop)
        else:
            if args.action == "motor":
                if args.zone.isdecimal():
                    ch = int(args.zone)
                    if ch > 15:
                        raise ValueError("channel must be 0..15")
                    cmd = f"pulse {ch} 4095 1000"
                else:
                    cmd = f"zone {args.zone}"
            elif args.action == "arm":
                cmd = f"arm {args.side} {args.direction} {args.step if args.step is not None else args.pace}"
            else:
                cmd = args.action
            print(json.dumps(await shirt.command(cmd)))
            if args.action in ("motor", "arm"):
                await asyncio.sleep(9.3 if args.action == "arm" and args.pace == "slow" and args.step is None else 2)
                print(json.dumps(await shirt.status()))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    for name in ("scan", "status", "stop", "context", "pair"):
        sub.add_parser(name)
    motor = sub.add_parser("motor")
    motor.add_argument("zone")
    arm = sub.add_parser("arm")
    arm.add_argument("side", choices=("right", "left", "both"))
    arm.add_argument("direction", choices=("out", "in"))
    arm.add_argument("--step", type=int, default=None, choices=range(100,501), metavar="100..500")
    arm.add_argument("--pace", choices=("slow", "normal", "fast"), default="normal")
    pat = sub.add_parser("pattern")
    pat.add_argument("pair", choices=("chest", "back", "both"))
    pat.add_argument("name", choices=sorted(PRESETS))
    timing = pat.add_mutually_exclusive_group()
    timing.add_argument("--seconds", type=float)
    timing.add_argument("--loop", action="store_true", help="repeat for 3 minutes, then stop")
    pat.add_argument("--peak", type=int, default=10)
    signal = sub.add_parser("signal")
    signal.add_argument("name", choices=MEANINGS)
    signal.add_argument("--side", choices=("right", "left", "both"), default="right")
    signal.add_argument("--pair", choices=("chest", "back"), default="chest")
    signal.add_argument("--peak", type=int, default=10)
    signal.add_argument("--loop", action="store_true", help="repeat for 3 minutes, then stop")
    args = parser.parse_args()
    try:
        asyncio.run(run(args))
    except (OSError, RuntimeError, asyncio.TimeoutError, BleakError):
        if args.action != "context":
            raise
        # No stale capability text when the controller cannot be reached.


if __name__ == "__main__":
    main()
