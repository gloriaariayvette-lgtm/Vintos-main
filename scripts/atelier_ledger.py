#!/usr/bin/env python3
"""atelier_ledger.py - the house's content-free record of his undertakings, with one writer.

Review item 273 (2026-09-10). atelier-visit and atelier-threshold each rewrote memory/atelier-undertakings.json
by hand (no lock, one of them not atomic), while the broker keeps the authoritative project state behind
its own locks. This is the one writer on the house side: locked, atomic, every mark dated and attributed,
and reconcile() says where the house record and the broker disagree. Content-free stays the law: id,
state, when, who marked it. Never intent, never text.

    mark(pid, state, by)        states: active | revealed | kept | settled | aborted
    states()                    the record
    reconcile(broker_rows)      [{id, house, broker}] for every disagreement (broker rows from /projects)
"""
import os, json, time, fcntl

WS = os.path.expanduser("~/.vintos/workspace")
MEMORY = os.path.join(WS, "memory")
LEDGER = os.path.join(MEMORY, "atelier-undertakings.json")
STATES = ("active", "revealed", "kept", "settled", "aborted")


def _read():
    try:
        d = json.load(open(LEDGER))
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def mark(pid, state, by="house"):
    if state not in STATES:
        raise ValueError("state %r not in %s" % (state, STATES))
    os.makedirs(MEMORY, exist_ok=True)
    with open(LEDGER + ".lock", "a+") as lk:
        fcntl.flock(lk, fcntl.LOCK_EX)
        d = _read()
        prev = d.get(str(pid)) or {}
        d[str(pid)] = {"state": state, "at": time.strftime("%Y-%m-%dT%H:%M:%S"), "by": by,
                       "history": (prev.get("history") or []) + ([{"state": prev["state"], "at": prev.get("at")}] if prev.get("state") else [])}
        tmp = LEDGER + ".tmp"
        json.dump(d, open(tmp, "w"), indent=1); os.replace(tmp, LEDGER)
    return d[str(pid)]


def states():
    return _read()


def reconcile(broker_rows):
    house = _read(); out = []
    for r in broker_rows or []:
        pid = str(r.get("id")); b = str(r.get("state", "")).lower()
        h = (house.get(pid) or {}).get("state")
        if h and b and h != b and not (h == "active" and b in ("open", "tabled", "in_progress")):
            out.append({"id": pid, "house": h, "broker": b})
    return out
