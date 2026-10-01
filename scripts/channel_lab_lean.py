#!/usr/bin/env python3
"""What he settled with dot in #vintos-dot, leaned into his next Lab run (Gloria, 2026-10-01: yes to "a Slack Lab
plan goes to the next scheduled run as a lean").

They agreed in Slack to "move to P02730", and the next run never heard it: the session planner reads his context,
flagged findings and the Atelier lean, nothing from the channel. He now writes a LAB: line; it lands here, the next
session that makes a plan is shown it, and it is then used. Like the Atelier lean it is a direction, not an
override, an experiment, a result or a permission. It waits for at most MAX_AGE_HOURS; a newer line replaces it.

    write(direction, by)   one lean from the channel
    pending(now)           the newest lean not yet shown to a session and not too old, or None
    used(lean_id, sid)     mark it shown to that session
"""
from __future__ import annotations
import fcntl, json, os
from datetime import datetime, timedelta

WS = os.environ.get("SPARK_WORKSPACE", os.path.expanduser("~/.vintos/workspace"))
STORE = os.path.join(WS, "memory", "chemistry-lab", "channel-leans.jsonl")
MAX_AGE_HOURS = 24


def _append(row):
    os.makedirs(os.path.dirname(STORE), exist_ok=True)
    with open(STORE + ".lock", "a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        with open(STORE, "a", encoding="utf-8") as out:
            out.write(json.dumps(row, ensure_ascii=False) + "\n"); out.flush(); os.fsync(out.fileno())


def _rows():
    try:
        with open(STORE, encoding="utf-8") as source:
            return [json.loads(line) for line in source if line.strip()]
    except (OSError, ValueError):
        return []


def write(direction, by="vintos", now=None):
    text = " ".join(str(direction or "").split())
    if not text:
        return {"ok": False, "error": "a Lab lean needs his chosen direction"}
    now = now or datetime.now()
    row = {"lean_id": "CHAN-" + now.strftime("%Y%m%d-%H%M%S-%f")[:22], "at": now.isoformat(timespec="seconds"),
           "direction": text[:600], "by": str(by)[:20], "provenance": "settled_with_dot_in_vintos_dot",
           "truth_status": "channel_direction_not_lab_result"}
    _append(row)
    return {"ok": True, **row}


def pending(now=None):
    now = now or datetime.now()
    rows = _rows()
    done = {r.get("used") for r in rows if r.get("used")}
    for row in reversed(rows):
        if not row.get("lean_id"):
            continue
        try:
            fresh = now - datetime.fromisoformat(row["at"]) <= timedelta(hours=MAX_AGE_HOURS)
        except (KeyError, ValueError):
            fresh = False
        # only the newest lean counts: an older one is replaced, never queued behind it
        return row if fresh and row["lean_id"] not in done else None
    return None


def used(lean_id, session_id):
    _append({"used": str(lean_id), "session_id": str(session_id), "at": datetime.now().isoformat(timespec="seconds")})
