#!/usr/bin/env python3
"""Interactively install Vintos's NVIDIA key on Aegis without echoing it."""
import getpass
import os
from pathlib import Path
import tempfile

TARGET = Path.home()/".config/vintos/nvidia-nim.key"


def main():
    target = TARGET
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(target.parent, 0o700)
    key = getpass.getpass("NVIDIA API key (hidden): ").strip()
    if not 20 <= len(key) <= 4096 or any(c.isspace() for c in key):
        raise ValueError("invalid key shape; nothing saved")
    fd, temporary = tempfile.mkstemp(prefix=".nvidia-nim-", dir=target.parent)
    try:
        with os.fdopen(fd, "w") as stream:
            os.fchmod(stream.fileno(), 0o600)
            stream.write(key + "\n"); stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary, target)
    finally:
        try: os.unlink(temporary)
        except FileNotFoundError: pass
    print("NVIDIA key saved at", target, "(mode 0600). No API job was submitted.")


if __name__ == "__main__": main()
