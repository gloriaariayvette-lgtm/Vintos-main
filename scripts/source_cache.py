#!/usr/bin/env python3
"""source_cache.py - the one question "did the sources change since last time?", answered by hash.

Review item 162 (2026-09-10). Several organs re-ran a model over the same inputs every interval (the
value map over an unchanged context, a description over an unchanged screen). This keeps, per named
job, the hash of the material it last ran over; unchanged(name, material) is True when nothing moved,
and the caller skips the inference and says so. A job that wants to run anyway passes force.

    unchanged(name, material) -> bool        (records the hash when it changed)
    last(name)                 -> {"sha", "at"} | None
"""
import os, json, time, hashlib

WS = os.path.expanduser("~/.vintos/workspace")
MEMORY = os.path.join(WS, "memory")
STORE = os.path.join(MEMORY, "source-cache.json")


def _load():
    try:
        d = json.load(open(STORE)); return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _save(d):
    os.makedirs(MEMORY, exist_ok=True)
    tmp = STORE + ".tmp"; json.dump(d, open(tmp, "w"), indent=1); os.replace(tmp, STORE)


def sha_of(material):
    if isinstance(material, (bytes, bytearray)):
        b = bytes(material)
    else:
        b = str(material).encode("utf-8", "replace")
    return hashlib.sha256(b).hexdigest()[:16]


def unchanged(name, material, force=False):
    d = _load(); sha = sha_of(material); prev = d.get(name)
    if prev and prev.get("sha") == sha and not force:
        prev["seen"] = int(prev.get("seen", 0)) + 1; prev["last_seen"] = time.strftime("%Y-%m-%dT%H:%M:%S"); d[name] = prev; _save(d)
        return True
    d[name] = {"sha": sha, "at": time.strftime("%Y-%m-%dT%H:%M:%S"), "seen": 0}
    _save(d)
    return False


def last(name):
    return _load().get(name)
