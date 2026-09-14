#!/usr/bin/env python3
"""The narrow, provenance-preserving bridge between Atelier and Forge.

An explicit room choice may commission a proposal. An installed Forge build
may become a new formation root. Neither direction changes the ancestry:
relational or unclassified work never becomes self-originated by crossing.
"""
from __future__ import annotations
import fcntl, json, os
from datetime import datetime

WS = os.environ.get("SPARK_WORKSPACE", os.path.expanduser("~/.vintos/workspace"))
STORE = os.path.join(WS, "memory", "atelier-forge-roots.jsonl")
LOCK = STORE + ".lock"


def _append(row):
    os.makedirs(os.path.dirname(STORE), exist_ok=True)
    with open(LOCK, "a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        existing = []
        try:
            with open(STORE) as source: existing = [json.loads(x) for x in source if x.strip()]
        except Exception: pass
        if any(x.get("proposal_id") == row.get("proposal_id") for x in existing): return existing[-1]
        with open(STORE, "a") as out:
            out.write(json.dumps(row, ensure_ascii=False) + "\n"); out.flush(); os.fsync(out.fileno())
    return row


def record_completion(proposal):
    origin = proposal.get("origin") or {}
    provenance = origin.get("provenance_class") or "unclassified"
    commissioned = bool(origin.get("commissioned_ancestor", provenance != "self_originated"))
    row = {"proposal_id": proposal.get("id"), "at": datetime.now().isoformat(),
           "root": "forge:%s" % proposal.get("id"), "root_type": "forged_capability",
           "text": str(proposal.get("capability") or "")[:300],
           "provenance_class": provenance, "commissioned_ancestor": commissioned,
           "formed_from": ["skill-proposals.json:%s" % proposal.get("id")],
           "forge_state": proposal.get("state"), "atelier_project_id": origin.get("atelier_project_id", "")}
    return _append(row)


def roots():
    try:
        with open(STORE) as source: return [json.loads(x) for x in source if x.strip()]
    except Exception: return []
