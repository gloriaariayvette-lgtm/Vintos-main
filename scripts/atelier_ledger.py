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


def broker_state(base="http://127.0.0.1:8611", timeout=3):
    """review 81: three different answers, never confused: {"broker": "unavailable"} when the socket
    does not answer, {"broker": "up", "project": None} when it answers and holds nothing, and
    {"broker": "up", "project": <id>} when a project is on the worktable. The house reads this before
    deciding a LOOK or a threshold, so a dead broker never reads as an empty atelier."""
    try:
        import urllib.request, json as _j
        with urllib.request.urlopen(base + "/health", timeout=timeout) as r:
            h = _j.loads(r.read().decode() or "{}")
    except Exception as e:
        return {"broker": "unavailable", "why": str(e)[:80], "project": None}
    try:
        import urllib.request, json as _j
        req = urllib.request.Request(base + "/worktable", data=b"{}", headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            w = _j.loads(r.read().decode() or "{}")
        return {"broker": "up", "project": w.get("id") or None, "active": bool(h.get("active"))}
    except Exception as e:
        return {"broker": "up", "project": None, "active": bool(h.get("active")), "worktable": "unreadable: %s" % str(e)[:60]}


def inspect(pid, base="http://127.0.0.1:8611", timeout=3, house_header=None):
    """review 328: one view of an undertaking from the house side: the house ledger's state and history,
    the broker's content-free row (state, artifact count, kept/revealed dates) when the broker answers,
    the reveal records naming this artifact, and the refusals. Never intent, never text."""
    out = {"id": str(pid), "house": _read().get(str(pid)), "broker": None, "reveals": [], "refusals": [], "blockers": []}
    try:
        import urllib.request, json as _j
        req = urllib.request.Request(base + "/projects", data=b"{}", headers={"Content-Type": "application/json", **({"X-Atelier-House": house_header} if house_header else {})})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            rows = _j.loads(r.read().decode() or "[]")
        rows = rows.get("projects", rows) if isinstance(rows, dict) else rows
        out["broker"] = next((x for x in rows if str(x.get("id")) == str(pid)), None)
    except Exception as e:
        out["broker"] = {"unavailable": str(e)[:80]}
    try:
        for rv in json.load(open(os.path.join(MEMORY, "atelier-reveals.json"))):
            if isinstance(rv, dict) and str(pid) in str(rv.get("artifact", "")):
                out["reveals"].append({k: rv.get(k) for k in ("revealed_at", "medium", "sha256", "bytes_verified", "artifact")})
    except Exception:
        pass
    try:
        for ln in open(os.path.join(MEMORY, "atelier-reveal-refusals.jsonl")):
            r = json.loads(ln)
            if str(pid) in str(r.get("artifact", "")): out["refusals"].append(r)
    except Exception:
        pass
    h = out["house"] or {}
    if h.get("state") == "active" and out["broker"] and isinstance(out["broker"], dict) and out["broker"].get("state") in ("held", "aborted"):
        out["blockers"].append("house says active, broker says %s" % out["broker"]["state"])
    if out["refusals"]:
        out["blockers"].append("%d reveal(s) refused on digest mismatch" % len(out["refusals"]))
    return out
