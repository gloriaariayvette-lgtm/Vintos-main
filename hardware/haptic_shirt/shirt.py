#!/usr/bin/env python3
"""Local shirt controls and a live-probed context adapter. No background playback."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import select
import termios
import time

from playback_control import Playback, LOOP_SECONDS, duration, request_stop, playback_idle
from feather import find_feather
from shirt_signals import MEANINGS, plan

ROOT = Path(__file__).resolve().parent
PRESETS = json.loads((ROOT / "somatic_patterns.json").read_text())["presets"]


class Shirt:
    def __enter__(self):
        self.fd = os.open(find_feather(), os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
        try:
            fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            attrs = termios.tcgetattr(self.fd)
            attrs[0] = attrs[1] = attrs[3] = 0
            attrs[2] = termios.CS8 | termios.CREAD | termios.CLOCAL
            attrs[4] = attrs[5] = termios.B115200
            attrs[6][termios.VMIN] = attrs[6][termios.VTIME] = 0
            termios.tcsetattr(self.fd, termios.TCSANOW, attrs)
            termios.tcflush(self.fd, termios.TCIFLUSH)
            return self
        except BaseException:
            os.close(self.fd)
            raise

    def __exit__(self, *_):
        os.close(self.fd)

    def command(self, text, wait=0.07):
        if any(c in text for c in "\r\n"):
            raise ValueError("one command per call")
        payload = (text + "\n").encode()
        if os.write(self.fd, payload) != len(payload):
            raise RuntimeError("incomplete serial write")
        return self.read(wait)

    def read(self, seconds):
        end = time.monotonic() + seconds
        data = bytearray()
        while time.monotonic() < end:
            ready, _, _ = select.select([self.fd], [], [], max(0, end-time.monotonic()))
            if ready:
                chunk = os.read(self.fd, 4096)
                if not chunk:
                    raise RuntimeError("shirt disconnected")
                data.extend(chunk)
        text = data.decode("utf-8", "replace")
        if "ERROR" in text:
            raise RuntimeError(text.strip())
        return text

    def context(self):
        """Generate only from this probe; never advertise from a saved presence file."""
        status = self.command("status", 0.35)
        if "PCA9685=found chest=found back=found" not in status:
            return ""
        mapping = self.command("map", 0.25)
        zones = []
        for line in mapping.splitlines():
            if line.startswith("CH") and " -> " in line:
                name = line.split(" -> ", 1)[1].strip()
                if name != "unassigned":
                    zones.append(name)
        return ("[HAPTIC SHIRT — controller answering now over USB]\n"
                + "Individual motor zones: " + ", ".join(zones) + ".\n"
                + "Chest and back each control two discs together. "
                + "Arm paths run upper arm → elbow → wrist, or reverse. "
                + "At most four discs at once. Stop cancels all outputs.\n"
                + "This probe confirms controller power and connectivity; "
                + "it does not sense whether the shirt is being worn or the battery switch is on.")

    def pattern(self, pair, name, seconds, peak, *, loop=False):
        if pair not in ("chest", "back", "both") or name not in PRESETS:
            raise ValueError("unknown pair or pattern")
        seconds = duration(seconds, loop)
        if not 0 <= peak <= 20:
            raise ValueError("peak must be 0..20")
        levels, interval = PRESETS[name]
        pairs = ("chest", "back") if pair == "both" else (pair,)
        step = interval / 1000
        with Playback() as playback:
            self.command("stop")
            start = time.monotonic()
            end = start + seconds
            try:
                while time.monotonic() < end and not playback.cancelled():
                    index = int((time.monotonic()-start)/step + 1e-7)
                    amplitude = amplitude_for(levels[index % len(levels)], peak)
                    for target in pairs:
                        remaining = int((end-time.monotonic())*1000)
                        if remaining <= 0 or playback.cancelled(): break
                        lease = min(2000, interval+250, remaining)
                        reply = self.command(f"level {target} {amplitude} {lease}", .025)
                        if f"LEVEL {target} " not in reply:
                            raise RuntimeError("missing level acknowledgement")
                    until = min(end, start+(index+1)*step)
                    while time.monotonic() < until and not playback.cancelled():
                        time.sleep(min(.05, until-time.monotonic()))
            finally:
                self.command("stop")

    def signal(self, name, side, pair, peak, *, loop=False):
        mapping = self.command("map", .25)
        channels = {}
        for line in mapping.splitlines():
            if line.startswith("CH") and " -> " in line:
                ch, zone = line.split(" -> ", 1)
                if zone.strip() != "unassigned": channels[zone.strip()] = int(ch[2:])
        events, cycle_seconds = plan(name, channels, side, pair, peak)
        with Playback() as playback:
            self.command("stop")
            start = time.monotonic()
            end = start + (LOOP_SECONDS if loop else cycle_seconds)
            cycle_start = start
            try:
                while cycle_start < end and not playback.cancelled():
                    for at, cmd in events:
                        due = cycle_start + at
                        if due >= end or playback.cancelled(): break
                        while time.monotonic() < due and not playback.cancelled():
                            time.sleep(min(.05, due-time.monotonic()))
                        if playback.cancelled(): break
                        if time.monotonic()-due > .2:
                            raise RuntimeError("signal timing missed; stopping rather than catching up")
                        remaining = int((end-time.monotonic())*1000)
                        if remaining <= 0: break
                        parts = cmd.split()
                        parts[3] = str(min(int(parts[3]), remaining))
                        self.command(" ".join(parts))
                    until = min(end, cycle_start+cycle_seconds)
                    while time.monotonic() < until and not playback.cancelled():
                        time.sleep(min(.05, until-time.monotonic()))
                    if not loop or time.monotonic() >= end or playback.cancelled(): break
                    self.command("stop")
                    cycle_start = time.monotonic()
            finally:
                self.command("stop")


def amplitude_for(level, peak):
    # ERM uses positive signed RTP range. This rescales shape, not motor force.
    return round(level * peak * 127 / 400)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    for name in ("context", "status", "stop", "map", "patterns"):
        sub.add_parser(name)
    motor = sub.add_parser("motor")
    motor.add_argument("zone")
    arm = sub.add_parser("arm")
    arm.add_argument("side", choices=("right", "left", "both"))
    arm.add_argument("direction", choices=("out", "in"))
    arm.add_argument("--step", type=int, default=None, choices=range(100, 501), metavar="100..500")
    arm.add_argument("--pace", choices=("slow", "normal", "fast"), default="normal")
    pace = sub.add_parser("pace")
    pace.add_argument("setting", choices=("slow", "normal", "fast"))
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
    if args.action == "patterns":
        print("\n".join(sorted(PRESETS)))
        return
    if args.action == "context":
        try:
            with Shirt() as shirt:
                print(shirt.context(), end="")
        except (OSError, RuntimeError, SystemExit):
            pass  # An unavailable controller contributes no context.
        return
    if args.action == "stop":
        request_stop()
        until = time.monotonic()+4
        while not playback_idle():
            if time.monotonic() >= until: raise RuntimeError("Playback is still stopping")
            time.sleep(.05)
    with Shirt() as shirt:
        if args.action == "signal":
            shirt.signal(args.name, args.side, args.pair, args.peak, loop=args.loop)
        elif args.action == "pattern":
            shirt.pattern(args.pair, args.name, args.seconds, args.peak, loop=args.loop)
        elif args.action == "motor":
            # Numeric addresses remain available for motors not yet named.
            ch = int(args.zone) if args.zone.isdecimal() else None
            if ch is not None and not 0 <= ch <= 15:
                parser.error("channel must be 0..15")
            cmd = f"pulse {ch} 4095 1000" if ch is not None else f"zone {args.zone}"
            print(shirt.command(cmd, 1.2), end="")
        elif args.action == "pace":
            print(shirt.command(f"pace {args.setting}", 0.2), end="")
        elif args.action == "arm":
            print(shirt.command(f"arm {args.side} {args.direction} {args.step if args.step is not None else args.pace}", 9.3 if args.pace == "slow" and args.step is None else 2), end="")
        else:
            print(shirt.command(args.action, 0.35), end="")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
