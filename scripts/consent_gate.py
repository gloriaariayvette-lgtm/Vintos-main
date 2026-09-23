#!/usr/bin/env python3
"""consent_gate.py — a consent gate for his self-initiated activities (morning poem, music).

Two jobs:
  1. Before he does a gated activity, ANNOUNCE it — write a plain record of what he is about to do,
     so the gate itself tells him (and Gloria) the activity by name, not a vague impulse.
  2. Log Gloria's yes/no per activity, and honour it: if her latest answer for an activity is "no",
     the gate is closed and the activity is skipped until she says yes again. No answer yet = open
     (the activity runs and is announced), so nothing silently stops until she has actually decided.

One append-only log, memory/consent-log.jsonl, both writers (announce, answer) go through store_guard.
Nothing here sends; the ASK reaches Gloria through her normal surfaces (the app's consent endpoint or
a notification), and her tap calls answer(). Kept tiny and side-effect-free so an activity can gate in
one line and a test never reaches a real store.
"""
import os
import sys
import time
from pathlib import Path

HERE = str(Path(__file__).resolve().parent)
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import store_guard

MEMORY = os.environ.get("VINTOS_MEMORY", os.path.expanduser("~/.vintos/workspace/memory"))
LOG = os.path.join(MEMORY, "consent-log.jsonl")
# The activities that pass through the gate. Others are not gated (this is not a global kill switch).
GATED = ("morning_poem", "music")


def _now():
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def _rows():
    out = []
    try:
        with open(LOG, encoding="utf-8", errors="replace") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    import json
                    row = json.loads(line)
                    if isinstance(row, dict):
                        out.append(row)
                except (ValueError, TypeError):
                    continue
    except FileNotFoundError:
        pass
    return out


def _append(row):
    import json
    os.makedirs(MEMORY, exist_ok=True)
    with store_guard.transaction(LOG):
        with open(LOG, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())


def stance(activity):
    """Gloria's current yes/no for an activity: her latest answer, or True (open) if she hasn't set one."""
    latest = None
    for row in _rows():
        if row.get("event") == "answer" and row.get("activity") == activity:
            latest = bool(row.get("yes"))
    return True if latest is None else latest


def answer(activity, yes, by="gloria", note=""):
    """Record Gloria's yes/no for an activity (called by the app's consent tap)."""
    if activity not in GATED:
        raise ValueError("not a gated activity")
    row = {"event": "answer", "at": _now(), "activity": activity, "yes": bool(yes),
           "by": str(by)[:40], "note": str(note)[:200]}
    _append(row)
    return row


def announce(activity, detail=""):
    """Record what he is about to do — the gate telling the activity by name — and return the stance."""
    open_ = stance(activity)
    _append({"event": "gate", "at": _now(), "activity": activity, "detail": str(detail)[:300],
             "opened": open_})
    return open_


def gate(activity, detail=""):
    """The one call an activity makes before running: announce it, and return True only if consented.

    A non-gated activity is always allowed (and not logged here). A gated one is announced every time
    and runs only while Gloria's latest answer is not 'no'.
    """
    if activity not in GATED:
        return True
    return announce(activity, detail)


def recent(limit=20):
    return _rows()[-int(limit):]
