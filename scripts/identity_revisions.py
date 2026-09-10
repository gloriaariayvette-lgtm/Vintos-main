#!/usr/bin/env python3
"""identity_revisions.py - one revision log across the identity projections (review 135).

A correction from Gloria, a fracture under pressure, a supersession of the authored BASE: each
appends one row to memory/identity-revisions.jsonl naming the projection (causal-self-model,
commitment-imprint, self-model-base, belief-sediment, narrative-identity), the entry id, what it
said before, what it says now, why, and where the change came from. Nothing is erased: the served
views read latest() for an entry and the history stays whole.

    from identity_revisions import record, latest, history
    record("causal-self-model", entry_id, old, new, reason="fractured under pressure 0.91", source="deviation-check")
"""
import os, json, hashlib
from datetime import datetime

MEMORY = os.path.expanduser("~/.vintos/workspace/memory")
PROJECTIONS = ("causal-self-model", "commitment-imprint", "self-model-base", "belief-sediment",
               "narrative-identity", "self-model")

def _path():
    return os.path.join(MEMORY, "identity-revisions.jsonl")

def entry_id_for(projection, text):
    """A stable id for an entry that has none of its own: the projection and its text."""
    return "%s:%s" % (projection, hashlib.sha1((text or "").strip().lower().encode("utf-8")).hexdigest()[:10])

def record(projection, entry_id, old, new, reason="", source="", kind="revision"):
    if projection not in PROJECTIONS:
        raise ValueError("unknown projection %r" % (projection,))
    row = {"at": datetime.now().isoformat(), "projection": projection, "entry_id": str(entry_id),
           "kind": kind, "old": (old if isinstance(old, (dict, list)) else str(old))[:600] if isinstance(old, str) else old,
           "new": (new if isinstance(new, (dict, list)) else str(new)) if not isinstance(new, str) else new[:600],
           "reason": str(reason)[:300], "source": str(source)[:80]}
    os.makedirs(MEMORY, exist_ok=True)
    with open(_path(), "a") as f:
        f.write(json.dumps(row, sort_keys=True) + "\n")
    return row

def history(projection=None, entry_id=None, limit=200):
    out = []
    try:
        for l in open(_path()):
            if not l.strip():
                continue
            r = json.loads(l)
            if projection and r.get("projection") != projection:
                continue
            if entry_id and r.get("entry_id") != str(entry_id):
                continue
            out.append(r)
    except FileNotFoundError:
        pass
    return out[-limit:]

def latest(projection, entry_id):
    h = history(projection, entry_id)
    return h[-1] if h else None

def served(projection, entry_id, current):
    """The served representation: the latest revision's `new` when one exists, else current."""
    l = latest(projection, entry_id)
    return l["new"] if l else current
