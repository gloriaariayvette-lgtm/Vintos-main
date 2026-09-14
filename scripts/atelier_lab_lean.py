#!/usr/bin/env python3
"""An explicit Atelier choice may lean one day of the visible Chemistry Lab.

The lean is not an override, experiment, finding, or permission. It crosses
the room only when he writes the dedicated tag, carries its undertaking
lineage, expires with the local calendar day, and leaves every no-lean day
unchanged.
"""
from __future__ import annotations
import fcntl, json, os
from datetime import datetime

WS = os.environ.get("SPARK_WORKSPACE", os.path.expanduser("~/.vintos/workspace"))
STORE = os.path.join(WS, "memory", "chemistry-lab", "atelier-leans.jsonl")
LOCK = STORE + ".lock"


def write(project_id, root, root_type, direction):
    text = str(direction or "").strip()
    if not text: return {"ok": False, "error": "a Lab lean needs his chosen direction"}
    row = {"lean_id": "LEAN-" + datetime.now().strftime("%Y%m%d-%H%M%S-%f")[:22],
           "day": datetime.now().date().isoformat(), "at": datetime.now().isoformat(),
           "direction": text[:1000], "project_id": str(project_id)[:40],
           "root": str(root or "")[:80], "root_type": str(root_type or "")[:40],
           "provenance": "explicit_atelier_choice",
           "truth_status": "atelier_authored_direction_not_lab_result"}
    os.makedirs(os.path.dirname(STORE), exist_ok=True)
    with open(LOCK, "a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        with open(STORE, "a", encoding="utf-8") as out:
            out.write(json.dumps(row, ensure_ascii=False) + "\n"); out.flush(); os.fsync(out.fileno())
    return {"ok": True, **row}


def today(day=None):
    wanted = day or datetime.now().date().isoformat()
    rows = []
    try:
        with open(STORE, encoding="utf-8") as source:
            rows = [json.loads(line) for line in source if line.strip()]
    except Exception: return None
    return next((row for row in reversed(rows) if row.get("day") == wanted), None)


def context_block(day=None):
    row = today(day)
    if not row: return "", None
    return ("[TODAY'S ATELIER LAB LEAN]\n%s\nThis is his chosen direction for today: "
            "let it bias the question, never replace evidence or the Lab's perimeter." % row["direction"], row)
