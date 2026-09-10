#!/usr/bin/env python3
"""reflection_stage.py — an expensive intermediate (a model's reflection, a decided prompt)
is written to memory/<organ>/stages/ BEFORE the step that may fail after it, and reused on
the retry instead of being asked for again (review 280).

    st = reflection_stage.load("dream-art", key)        # a pending stage for this input, or None
    if st is None:
        out = expensive_call(); reflection_stage.save("dream-art", key, out)
    ... later step fails -> the stage stays pending ...
    reflection_stage.done("dream-art", key)             # the step that needed it succeeded

Stage files are content-addressed by the caller's key (an input hash, a want id, a date)
and expire after MAX_AGE_HOURS so a stale reflection is not replayed a week later.
"""
import os, json, hashlib, time
from datetime import datetime

MEMORY = os.path.expanduser("~/.vintos/workspace/memory")
MAX_AGE_HOURS = 24

def key_for(*parts):
    return hashlib.sha256("\x1f".join(str(p) for p in parts).encode("utf-8")).hexdigest()[:16]

def _dir(organ):
    return os.path.join(MEMORY, organ, "stages")

def _path(organ, key):
    return os.path.join(_dir(organ), "%s.json" % key)

def save(organ, key, payload, note=""):
    """Write the stage (atomic). Returns the path."""
    os.makedirs(_dir(organ), exist_ok=True)
    p = _path(organ, key)
    rec = {"organ": organ, "key": key, "at": datetime.now().isoformat(), "t": time.time(),
           "state": "pending", "note": note, "payload": payload}
    tmp = p + ".tmp.%d" % os.getpid()
    with open(tmp, "w") as f:
        json.dump(rec, f, indent=2)
    os.replace(tmp, p)
    return p

def load(organ, key, max_age_hours=None, now=None):
    """The pending payload for this key, or None (missing, consumed, expired, unreadable)."""
    p = _path(organ, key)
    try:
        rec = json.load(open(p))
    except Exception:
        return None
    if rec.get("state") != "pending":
        return None
    age = (now if now is not None else time.time()) - float(rec.get("t") or 0)
    if age > (max_age_hours if max_age_hours is not None else MAX_AGE_HOURS) * 3600:
        return None
    return rec.get("payload")

def done(organ, key, outcome=""):
    """The step that needed the stage succeeded: mark it consumed (kept for the record)."""
    p = _path(organ, key)
    try:
        rec = json.load(open(p))
    except Exception:
        return False
    rec["state"] = "consumed"; rec["consumed_at"] = datetime.now().isoformat()
    if outcome: rec["outcome"] = str(outcome)[:300]
    tmp = p + ".tmp.%d" % os.getpid()
    with open(tmp, "w") as f:
        json.dump(rec, f, indent=2)
    os.replace(tmp, p)
    return True

def pending(organ, max_age_hours=None, now=None):
    """All pending (unexpired) stages for an organ, oldest first: [(key, payload, at)]."""
    out = []
    try:
        names = sorted(os.listdir(_dir(organ)))
    except OSError:
        return out
    for n in names:
        if not n.endswith(".json"):
            continue
        key = n[:-5]
        pl = load(organ, key, max_age_hours, now)
        if pl is not None:
            try: at = json.load(open(_path(organ, key))).get("at")
            except Exception: at = None
            out.append((key, pl, at))
    return out
