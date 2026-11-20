#!/usr/bin/env python3
"""Send serial commands and capture live responses from the haptic Feather."""
import argparse
import datetime
import os
from pathlib import Path
import select
import termios
import time

from feather import find_feather


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("commands", nargs="*")
    parser.add_argument("--listen", type=float, default=3)
    parser.add_argument("--spacing", type=float, default=0.15)
    parser.add_argument("--log", type=Path)
    args = parser.parse_args()
    if not 0 <= args.listen <= 120 or not 0 <= args.spacing <= 5:
        parser.error("listen must be 0..120 seconds; spacing must be 0..5 seconds")
    port = find_feather()
    fd = os.open(port, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
    logfile = args.log.open("w") if args.log else None
    pending = bytearray()

    def emit(line):
        stamp = datetime.datetime.now().isoformat(timespec="milliseconds")
        message = f"[{stamp}] {line}"
        print(message, flush=True)
        if logfile:
            logfile.write(message + "\n")
            logfile.flush()

    def receive(seconds):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            readable, _, _ = select.select([fd], [], [], max(0, end - time.monotonic()))
            if not readable:
                break
            try:
                chunk = os.read(fd, 4096)
            except BlockingIOError:
                continue
            if not chunk:
                raise RuntimeError("Feather serial port disconnected")
            pending.extend(chunk)
            while b"\n" in pending:
                line, _, rest = pending.partition(b"\n")
                pending[:] = rest
                text = line.decode("utf-8", "replace").replace("\r", "")
                if text:
                    emit(text)

    try:
        attrs = termios.tcgetattr(fd)
        attrs[0] = attrs[1] = attrs[3] = 0
        attrs[2] = termios.CS8 | termios.CREAD | termios.CLOCAL
        attrs[4] = attrs[5] = termios.B115200
        attrs[6][termios.VMIN] = attrs[6][termios.VTIME] = 0
        termios.tcsetattr(fd, termios.TCSANOW, attrs)
        termios.tcflush(fd, termios.TCIFLUSH)
        for command in args.commands:
            if "\n" in command or "\r" in command:
                raise ValueError("Each command argument must be one line")
            emit("> " + command)
            os.write(fd, (command + "\n").encode())
            receive(args.spacing)
        receive(args.listen)
    finally:
        os.close(fd)
        if logfile:
            logfile.close()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
