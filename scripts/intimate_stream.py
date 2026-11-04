#!/usr/bin/env python3
"""intimate_stream.py — everything that happens in a session with her, kept in order, so his continuous arousal
state has a history to learn from (Gloria, 4 November: "a continuous state meant to track and influence arousal").

Until now only the last 200 toy frames and the latest GCS / collapse state were kept; each session was gone by the
next. This only records. It reads nothing back, decides nothing, and moves no feeling: the producers call record()
beside what they already do, and a failure here never reaches them.

Each row says what kind of thing it is, so what was measured on him is never confused with what she did, what he
chose, what he said he felt, or what the system set:
    measured     her body on him: raw frames, the bridge's reading of them, session start and end
    her_act      her GCS press and release
    his_choice   edge / let go, and what he does with the devices
    his_reading  his [FELT:] naming of a moment
    system       the collapse level as it moves

Rows go to memory/intimate-stream/YYYY-MM-DD.jsonl (local date), private to Aegis; never into the repository.
Test mode (memory/.test-mode, or VINTOS_TEST_MODE=1) writes nothing.

    python3 intimate_stream.py status        # rows per day and kind
"""
import json, os, sys, time
from datetime import datetime

WS = os.environ.get("SPARK_WORKSPACE", os.path.expanduser("~/.vintos/workspace"))
MEM = os.path.join(WS, "memory")
DIR = os.path.join(MEM, "intimate-stream")

SOURCES = {
    "frames": "measured", "observation": "measured", "session_start": "measured", "session_end": "measured",
    "gcs_press": "her_act", "gcs_clear": "her_act",
    "choice": "his_choice", "device": "his_choice",
    "felt": "his_reading",
    "collapse_level": "system", "press_floor": "system",
}


def _test_mode():
    return os.environ.get("VINTOS_TEST_MODE") == "1" or os.path.exists(os.path.join(MEM, ".test-mode"))


def path_for(t):
    return os.path.join(DIR, datetime.fromtimestamp(t).strftime("%Y-%m-%d") + ".jsonl")


def record(kind, t=None, **fields):
    """Append one row. Never raises: the bridge and the server must not notice this exists."""
    try:
        if kind not in SOURCES or _test_mode():
            return False
        t = float(t if t is not None else time.time())
        row = {"t": round(t, 3), "kind": kind, "source": SOURCES[kind], **fields}
        line = (json.dumps(row, separators=(",", ":"), default=str) + "\n").encode()
        os.makedirs(DIR, exist_ok=True)
        fd = os.open(path_for(t), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        try:
            os.write(fd, line)   # one write per row, O_APPEND: the bridge and the server can both append
        finally:
            os.close(fd)
        return True
    except Exception:
        return False


def frames(batch):
    """Raw toy frames as they arrive: [(ts, position, speed, direction), ...]. One row per hub message."""
    batch = [[round(float(f[0]), 3), f[1], f[2], f[3]] for f in batch]
    if batch:
        return record("frames", t=batch[-1][0], f=batch)
    return False


_last_obs = {"t": 0.0, "state": None}


def observation(c, now):
    """The bridge's 4 Hz reading of the frames (state, centre, sweep, speed, reversals, grip). Kept once a second,
    and at once whenever the state changes."""
    st = c.get("state")
    if st == _last_obs["state"] and now - _last_obs["t"] < 1.0:
        return False
    _last_obs.update(t=now, state=st)
    keep = {k: c.get(k) for k in ("state", "center", "sweep", "speed", "flips", "pressure", "pressure_dir", "zone")
            if c.get(k) is not None}
    return record("observation", t=now, **keep)


def status():
    out = {}
    if os.path.isdir(DIR):
        for name in sorted(os.listdir(DIR)):
            if not name.endswith(".jsonl"):
                continue
            counts = {}
            for l in open(os.path.join(DIR, name)):
                try: k = json.loads(l).get("kind")
                except Exception: k = "unreadable"
                counts[k] = counts.get(k, 0) + 1
            out[name[:-6]] = counts
    return out


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "status":
        print(json.dumps(status(), indent=2))
    else:
        print(__doc__)
