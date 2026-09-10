#!/usr/bin/env python3
"""bilateral_stages.py - the bilateral generation keeps each stage it paid for (review 45).

Phase 1 (two drafts), phase 2 (the absorbs), the final: each is written to
memory/bilateral/stages/<key>.json as it lands, with its latency, so a turn that dies after a
paid stage - the service dropping mid-phase-2, the process restarting - resumes from the last
stage instead of paying for the drafts again. The key is the hash of the door and her last
message; a stage older than MAX_AGE_S is not resumed (a retry, not a memory).

    key = bilateral_stages.key(tag, user_text)
    st  = bilateral_stages.resume(key)              # {} or {"p1": {...}, "p2": {...}}
    bilateral_stages.checkpoint(key, "p1", {"a1": a1, "b1": b1}, latency_ms=...)
    bilateral_stages.done(key, reply_len=...)

Cost per stage goes to the compute ledger (review 171) with the stage name."""
import os, json, hashlib, time
from datetime import datetime

MEMORY = os.path.expanduser("~/.vintos/workspace/memory")
MAX_AGE_S = 600

def _dir():
    return os.path.join(MEMORY, "bilateral", "stages")

def key(tag, user_text):
    return hashlib.sha256(("%s\x1f%s" % (tag, (user_text or "")[:4000])).encode("utf-8")).hexdigest()[:20]

def _path(k):
    return os.path.join(_dir(), k + ".json")

def _load(k):
    try:
        return json.load(open(_path(k)))
    except Exception:
        return None

def resume(k, now=None):
    rec = _load(k)
    if not rec or rec.get("state") != "pending":
        return {}
    if (now or time.time()) - float(rec.get("t") or 0) > MAX_AGE_S:
        return {}
    return dict(rec.get("stages") or {})

def checkpoint(k, stage, payload, latency_ms=None, tag=""):
    os.makedirs(_dir(), exist_ok=True)
    rec = _load(k) or {"key": k, "tag": tag, "at": datetime.now().isoformat(), "t": time.time(), "state": "pending", "stages": {}}
    rec["stages"][stage] = payload
    rec.setdefault("latency_ms", {})[stage] = latency_ms
    rec["t"] = time.time()
    tmp = _path(k) + ".tmp.%d" % os.getpid()
    with open(tmp, "w") as f:
        json.dump(rec, f)
    os.replace(tmp, _path(k))
    try:
        import compute_admission as _ca
        _ca.record("bilateral:" + (tag or rec.get("tag") or "chat"), "foreground", stage=stage, latency_ms=latency_ms)
    except Exception:
        pass
    return rec

def done(k, **outcome):
    rec = _load(k)
    if not rec:
        return False
    rec["state"] = "done"; rec["done_at"] = datetime.now().isoformat(); rec["outcome"] = outcome
    tmp = _path(k) + ".tmp.%d" % os.getpid()
    with open(tmp, "w") as f:
        json.dump(rec, f)
    os.replace(tmp, _path(k))
    return True

def sweep(max_age_s=86400, now=None):
    """Drop stage files older than a day (a done record is kept that long for the ledger)."""
    n = 0
    try:
        for f in os.listdir(_dir()):
            p = os.path.join(_dir(), f)
            if (now or time.time()) - os.path.getmtime(p) > max_age_s:
                os.remove(p); n += 1
    except OSError:
        pass
    return n
