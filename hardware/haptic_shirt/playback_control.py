"""Local playback ownership and a stop request shared by USB/Bluetooth clients."""
import fcntl
import json
import os
from pathlib import Path
import time
import uuid

LOOP_SECONDS = 180
RUNTIME = Path(__file__).resolve().parent / ".runtime"


def _write_state(state):
    RUNTIME.mkdir(mode=0o700, exist_ok=True)
    target = RUNTIME / "playback.json"
    temp = RUNTIME / ("state-" + uuid.uuid4().hex)
    fd = os.open(temp, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        os.write(fd, json.dumps(state).encode())
    finally:
        os.close(fd)
    os.replace(temp, target)


class Playback:
    def __enter__(self):
        RUNTIME.mkdir(mode=0o700, exist_ok=True)
        self.fd = os.open(RUNTIME / "playback.lock", os.O_CREAT | os.O_RDWR, 0o600)
        try:
            fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            os.close(self.fd)
            raise RuntimeError("A pattern is already playing; stop it before starting another")
        self.token = uuid.uuid4().hex
        _write_state({"owner": self.token})
        return self

    def cancelled(self):
        try:
            return json.loads((RUNTIME / "playback.json").read_text()).get("owner") != self.token
        except (OSError, ValueError):
            return True

    def __exit__(self, *_):
        fcntl.flock(self.fd, fcntl.LOCK_UN)
        os.close(self.fd)


def request_stop():
    _write_state({"stopped": True})


def playback_idle():
    RUNTIME.mkdir(mode=0o700, exist_ok=True)
    fd = os.open(RUNTIME / "playback.lock", os.O_CREAT | os.O_RDWR, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return False
        return True
    finally:
        os.close(fd)


def duration(seconds, loop):
    if loop:
        if seconds is not None:
            raise ValueError("Loop runs for three minutes; omit --seconds")
        return LOOP_SECONDS
    seconds = 5 if seconds is None else seconds
    if not 0 < seconds <= 30:
        raise ValueError("Non-loop duration must be greater than zero and at most 30 seconds")
    return seconds
