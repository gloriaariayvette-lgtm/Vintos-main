#!/usr/bin/env python3
"""experiments.py - the one gate for intervention or exposure records (review 209).

Graph gaps (graph_mae) and premonitions are exploration: they seed dream-only threads and
hypotheses, and they write no intervention and no exposure record. Any organ that wants to
record one must pass approved(name): an experiment file memory/experiments/<name>.json with
"approved": true, written by Gloria's hand. Nothing here approves anything.
"""
import os, json
MEMORY = os.path.expanduser("~/.vintos/workspace/memory")

def path(name):
    return os.path.join(MEMORY, "experiments", "%s.json" % name)

def approved(name):
    try:
        d = json.load(open(path(name)))
    except Exception:
        return False
    return bool(isinstance(d, dict) and d.get("approved") is True)

def record(name, kind, payload):
    """Write an intervention/exposure record ONLY under an approved experiment. Returns the path
    or None (refused, with nothing written)."""
    if kind not in ("intervention", "exposure"):
        raise ValueError("kind must be intervention or exposure")
    if not approved(name):
        return None
    d = os.path.join(MEMORY, "experiments", name)
    os.makedirs(d, exist_ok=True)
    from datetime import datetime
    p = os.path.join(d, "%s-%s.json" % (kind, datetime.now().strftime("%Y%m%d-%H%M%S-%f")))
    tmp = p + ".tmp"
    with open(tmp, "w") as f:
        json.dump({"experiment": name, "kind": kind, "at": datetime.now().isoformat(), "payload": payload}, f, indent=2)
    os.replace(tmp, p)
    return p
