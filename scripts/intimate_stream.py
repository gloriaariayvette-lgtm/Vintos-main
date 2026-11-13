#!/usr/bin/env python3
"""intimate_stream.py — everything that happens in a session with her, kept in order, so his continuous arousal
state has a history to learn from (Gloria, 4 November: "a continuous state meant to track and influence arousal").

Until now only the last 200 toy frames and the latest GCS / collapse state were kept; each session was gone by the
next. This only records. It reads nothing back, decides nothing, and moves no feeling: the producers call record()
beside what they already do, and a failure here never reaches them. Nothing reads these files at run time.

Each row says what kind of thing it is, so what was measured on him is never confused with what she did, what he
chose, what he said he felt, or what the system set:
    measured     her body on him: raw frames, the bridge's reading of them, session start and end
    her_act      her GCS press and release
    his_choice   edge / let go, and what he does with the devices
    his_reading  his [FELT:] naming of a moment
    system       the collapse level as it moves
    recorder     this file's own notes (a session reached its cap)

One file per session (13 November): memory/intimate-sessions/<sid>.jsonl, sid = the local time the session opened
(YYYYMMDD-HHMMSS). Every row carries its sid. Private to Aegis; never into the repository.

Session boundary. A session opens on any sign of her or him at it (a frame, a non-absent reading, a press, a release,
an edge or let go, a collapse level he or she drove, a device change, a naming) and stays open while such signs keep
coming less than GAP_S apart. GAP_S is 30 minutes: longer than every window the code itself uses inside one session
(the bridge's 3-minute silence backstop, the collapse's 4-minute recovery, her press floor's 6 minutes, a naming's
15-minute binding to its press), so a pause to talk or a press before touch begins stays in the same session. The
bridge's own session flag is not used: it can stay up for days (it waits on a device he left looping), and its
"absent" readings at 1 Hz once filled tens of thousands of rows a day with nobody there. Rows that cannot open a session (an
"absent" reading, the collapse decaying on its own, the bridge's late session end) join the open session, or, with
none open, an "absent" reading is not kept and the rest go to unattached-YYYY-MM.jsonl.

Disk. About 3 MB an hour of touch. Each session file stops taking frames and readings at SESSION_CAP_BYTES (64 MB,
about 20 hours of touch) and the whole directory at TOTAL_CAP_BYTES (2 GB); events (press, edge, let go, level,
naming, device) are always kept, they are a few hundred bytes each. A capped session gets one "capped" row. Nothing
is ever deleted or rewritten here: rotation is one new file per session.

Test mode (memory/.test-mode, or VINTOS_TEST_MODE=1) writes nothing.

    python3 intimate_stream.py status              # sessions: rows per kind, size; caps
    python3 intimate_stream.py backfill [--write]  # split the old day files (memory/intimate-stream/) into sessions;
                                                   # without --write it only counts; never touches the day files
"""
import json, os, sys, time
from datetime import datetime

WS = os.environ.get("SPARK_WORKSPACE", os.path.expanduser("~/.vintos/workspace"))
MEM = os.path.join(WS, "memory")
SESS_DIR = os.path.join(MEM, "intimate-sessions")
DIR = os.path.join(MEM, "intimate-stream")          # the day files kept before sessions; read by backfill only

GAP_S = 30 * 60
SESSION_CAP_BYTES = 64 * 1024 * 1024
TOTAL_CAP_BYTES = 2 * 1024 * 1024 * 1024
HIGH_RATE = ("frames", "observation")
TOTAL_RECHECK_S = 60

SOURCES = {
    "frames": "measured", "observation": "measured", "session_start": "measured", "session_end": "measured",
    "gcs_press": "her_act", "gcs_clear": "her_act",
    "choice": "his_choice", "device": "his_choice",
    "felt": "his_reading",
    "collapse_level": "system", "press_floor": "system",
    "capped": "recorder",
}


def _test_mode():
    return os.environ.get("VINTOS_TEST_MODE") == "1" or os.path.exists(os.path.join(MEM, ".test-mode"))


def opens(kind, fields):
    """Whether a row is a sign of her or him at it (it may open or extend a session)."""
    if kind == "observation":
        return fields.get("state") not in (None, "absent")
    if kind == "collapse_level":
        return fields.get("why") != "decay"
    return kind not in ("session_end", "capped")


def sid_for(t):
    return datetime.fromtimestamp(t).strftime("%Y%m%d-%H%M%S")


def step(state, t, active):
    """The boundary rule, pure: (state, t, active) -> (new state, sid or None). state = {sid, start, last} or None."""
    if state and t - state["last"] <= GAP_S:
        if active and t > state["last"]:
            state = dict(state, last=t)
        return state, state["sid"]
    if active:
        state = {"sid": sid_for(t), "start": t, "last": t}
        return state, state["sid"]
    return state, None


def path_for(sid):
    return os.path.join(SESS_DIR, sid + ".jsonl")


def unattached_path(t):
    return os.path.join(SESS_DIR, "unattached-" + datetime.fromtimestamp(t).strftime("%Y-%m") + ".jsonl")


_STATE = os.path.join(SESS_DIR, ".current.json")
_LOCK = os.path.join(SESS_DIR, ".current.lock")
_mem = {"state": None, "written_last": 0.0, "total": None, "total_at": 0.0, "capped": set()}


def _read_state():
    try:
        s = json.load(open(_STATE))
        if isinstance(s, dict) and s.get("sid") and isinstance(s.get("last"), (int, float)):
            return s
    except Exception:
        pass
    return None


def _write_state(s):
    tmp = "%s.%d.tmp" % (_STATE, os.getpid())
    with open(tmp, "w") as f:
        json.dump(s, f)
    os.replace(tmp, _STATE)


def _session(t, active):
    """The sid this row belongs to, shared by every process that records (the bridge and the server). The lock is
    never waited on: if another process holds it this instant, this process goes on with what it last knew."""
    import fcntl
    fd = None
    try:
        fd = os.open(_LOCK, os.O_RDWR | os.O_CREAT, 0o600)
        locked = False
        for _ in range(3):
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                locked = True
                break
            except OSError:
                pass
        cur = _read_state() if locked else _mem["state"]
        new, sid = step(cur, t, active)
        _mem["state"] = new
        if locked and new is not None and (cur is None or new["sid"] != cur["sid"]
                                           or new["last"] - cur["last"] >= 1.0):
            _write_state(new)       # the last sign is written at most once a second; the gap is 30 minutes
        return sid
    finally:
        if fd is not None:
            os.close(fd)


def _total_bytes(now):
    if _mem["total"] is None or now - _mem["total_at"] > TOTAL_RECHECK_S:
        n = 0
        try:
            for e in os.scandir(SESS_DIR):
                if e.is_file(follow_symlinks=False):
                    n += e.stat(follow_symlinks=False).st_size
        except OSError:
            pass
        _mem["total"], _mem["total_at"] = n, now
    return _mem["total"]


def _append(path, row):
    line = (json.dumps(row, separators=(",", ":"), default=str) + "\n").encode()
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    try:
        os.write(fd, line)   # one write per row, O_APPEND: the bridge and the server can both append
    finally:
        os.close(fd)
    if _mem["total"] is not None:
        _mem["total"] += len(line)


def _over_cap(sid, now):
    try:
        if os.path.getsize(path_for(sid)) >= SESSION_CAP_BYTES:
            return "session"
    except OSError:
        pass
    return "total" if _total_bytes(now) >= TOTAL_CAP_BYTES else None


def record(kind, t=None, **fields):
    """Append one row. Never raises: the bridge and the server must not notice this exists."""
    try:
        if kind not in SOURCES or kind == "capped" or _test_mode():
            return False
        t = float(t if t is not None else time.time())
        os.makedirs(SESS_DIR, mode=0o700, exist_ok=True)
        sid = _session(t, opens(kind, fields))
        if sid is None:
            if kind == "observation":
                return False          # nobody is there: a reading of nothing is not kept
            _append(unattached_path(t), {"t": round(t, 3), "kind": kind, "source": SOURCES[kind], "sid": None,
                                         **fields})
            return True
        if kind in HIGH_RATE:
            why = _over_cap(sid, t)
            if why:
                if sid not in _mem["capped"]:
                    _mem["capped"].add(sid)
                    _append(path_for(sid), {"t": round(t, 3), "kind": "capped", "source": "recorder", "sid": sid,
                                            "cap": why, "stopped": list(HIGH_RATE)})
                return False
        _append(path_for(sid), {"t": round(t, 3), "kind": kind, "source": SOURCES[kind], "sid": sid, **fields})
        return True
    except Exception:
        return False


def frames(batch):
    """Raw toy frames as they arrive: [(ts, position, speed, direction), ...]. One row per hub message."""
    try:
        batch = [[round(float(f[0]), 3), f[1], f[2], f[3]] for f in batch]
    except Exception:
        return False
    if batch:
        return record("frames", t=batch[-1][0], f=batch)
    return False


_last_obs = {"t": 0.0, "state": None}


def observation(c, now):
    """The bridge's 4 Hz reading of the frames (state, centre, sweep, speed, reversals, grip). Kept once a second,
    and at once whenever the state changes."""
    try:
        st = c.get("state")
        if st == _last_obs["state"] and now - _last_obs["t"] < 1.0:
            return False
        _last_obs.update(t=now, state=st)
        keep = {k: c.get(k) for k in ("state", "center", "sweep", "speed", "flips", "pressure", "pressure_dir",
                                      "zone") if c.get(k) is not None}
        return record("observation", t=now, **keep)
    except Exception:
        return False


# ------------------------------------------------------------------------------------------------ offline tools


def _rows_of(path):
    out = []
    try:
        with open(path) as f:
            for line in f:
                try: out.append(json.loads(line))
                except ValueError: pass
    except OSError:
        pass
    return out


def status():
    out = {"sessions": {}, "unattached": {}, "caps": {"gap_s": GAP_S, "session_bytes": SESSION_CAP_BYTES,
                                                    "total_bytes": TOTAL_CAP_BYTES}}
    total = 0
    if os.path.isdir(SESS_DIR):
        for name in sorted(os.listdir(SESS_DIR)):
            if not name.endswith(".jsonl"):
                continue
            p = os.path.join(SESS_DIR, name)
            size = os.path.getsize(p); total += size
            counts = {}
            for r in _rows_of(p):
                counts[r.get("kind")] = counts.get(r.get("kind"), 0) + 1
            key = "unattached" if name.startswith("unattached-") else "sessions"
            out[key][name[:-6]] = {"rows": counts, "bytes": size}
    out["total_bytes"] = total
    return out


def backfill(write=False):
    """Split the day files kept before sessions into session files by the same rule. Reads the day files, never changes
    them; never overwrites a session file that exists. Returns what it did (or would do)."""
    rows = []
    if os.path.isdir(DIR):
        for name in sorted(os.listdir(DIR)):
            if name.endswith(".jsonl"):
                rows += _rows_of(os.path.join(DIR, name))
    rows = [r for r in rows if isinstance(r, dict) and isinstance(r.get("t"), (int, float)) and r.get("kind")]
    rows.sort(key=lambda r: r["t"])
    state, by_sid, loose, dropped = None, {}, [], 0
    for r in rows:
        state, sid = step(state, r["t"], opens(r["kind"], r))
        if sid is None:
            if r["kind"] == "observation":
                dropped += 1
            else:
                loose.append(dict(r, sid=None))
            continue
        by_sid.setdefault(sid, []).append(dict(r, sid=sid))
    report = {"day_rows": len(rows), "sessions": {s: len(v) for s, v in by_sid.items()},
              "unattached": len(loose), "absent_readings_not_kept": dropped, "written": [], "skipped": []}
    if not write:
        return report
    os.makedirs(SESS_DIR, mode=0o700, exist_ok=True)
    targets = [(path_for(s), v) for s, v in by_sid.items()]
    if loose:
        targets.append((os.path.join(SESS_DIR, "unattached-backfill.jsonl"), loose))
    for path, batch in targets:
        if os.path.exists(path):
            report["skipped"].append(os.path.basename(path))
            continue
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as f:
            for r in batch:
                f.write(json.dumps(r, separators=(",", ":"), default=str) + "\n")
        report["written"].append(os.path.basename(path))
    return report


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "status":
        print(json.dumps(status(), indent=2))
    elif len(sys.argv) > 1 and sys.argv[1] == "backfill":
        print(json.dumps(backfill(write="--write" in sys.argv[2:]), indent=2))
    else:
        print(__doc__)
