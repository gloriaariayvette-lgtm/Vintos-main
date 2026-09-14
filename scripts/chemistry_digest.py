#!/usr/bin/env python3
"""Append one mechanical Chemistry Lab receipt to the inner-life ledger.

first-light runs before dawn and summarizes the *previous* day — a receipt built
at 5am can only honestly report the day that has finished, not the one just begun.
So the digest summarizes YESTERDAY's rows and writes them into today's carry-forward
file, exactly as first-light does; rendering `date.today()` at 5am (the old bug) read
a day with no rows yet and left an empty marker behind a whole day of real work.

It reports only rows the Lab wrote that day.  It does not reinterpret a result, turn
an execution into correctness, or cross the separate Atelier boundary.  The shared
daily-inner lock and a marker keyed to the summarized day make the append idempotent.
"""
from __future__ import annotations

import fcntl
import json
import os
from collections import Counter
from datetime import date, timedelta


def _yesterday(file_day):
    return (date.fromisoformat(file_day) - timedelta(days=1)).isoformat()

WS = os.environ.get("SPARK_WORKSPACE") or os.path.expanduser("~/.vintos/workspace")
MEMORY = os.path.join(WS, "memory")
LAB = os.path.join(MEMORY, "chemistry-lab")
NOTEBOOK = os.path.join(LAB, "notebook.jsonl")
SESSIONS = os.path.join(LAB, "sessions.jsonl")
GRADES = os.path.join(LAB, "experiment-grades.jsonl")


def _rows(path):
    out = []
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            for line in handle:
                try: row = json.loads(line)
                except (TypeError, ValueError): continue
                if isinstance(row, dict): out.append(row)
    except FileNotFoundError:
        pass
    return out


def _on_day(row, day):
    return str(row.get("at") or row.get("measured_at") or "")[:10] == day


def _experiment_line(row):
    grade = row.get("grade") if isinstance(row.get("grade"), dict) else {}
    plan = row.get("plan") if isinstance(row.get("plan"), dict) else {}
    experiment = str(row.get("experiment") or plan.get("experiment") or "unnamed")[:80]
    execution = str(row.get("execution_state") or grade.get("execution_state") or row.get("state") or "unknown")[:60]
    accuracy = str(row.get("aggregate_accuracy") or grade.get("aggregate_accuracy") or "ungraded")[:80]
    run_id = str(row.get("mac_run_id") or row.get("run_id") or "")[:80]
    return f"- {experiment}: execution={execution}; accuracy={accuracy}" + (f"; run={run_id}" if run_id else "")


def _latest_question(notebook, sessions):
    for row in reversed(notebook + sessions):
        candidates = [row.get("next_question")]
        for key in ("reading", "reflection"):
            nested = row.get(key)
            if isinstance(nested, dict): candidates.append(nested.get("next_question"))
        for value in candidates:
            if str(value or "").strip(): return str(value).strip()[:500]
    return ""


def render(day=None):
    day = day or date.today().isoformat()
    notebook = [r for r in _rows(NOTEBOOK) if _on_day(r, day)]
    sessions = [r for r in _rows(SESSIONS) if _on_day(r, day)]
    grades = [r for r in _rows(GRADES) if _on_day(r, day)]
    kinds = Counter(str(r.get("kind") or "unknown") for r in notebook)
    experiment_rows = [r for r in sessions if r.get("experiment") or isinstance(r.get("plan"), dict)]
    if not experiment_rows:
        experiment_rows = grades
    owed = sum(1 for r in sessions if str(r.get("state", "")) in
               ("experiment_completed_reading_held", "held_reading_owed") or
               str(r.get("owed_reading", "")) in ("STILL_HELD", "REFUSED"))
    settled = sum(1 for r in notebook if str(r.get("kind", "")) == "owed_reading")
    question = _latest_question(notebook, sessions)

    lines = [f"<!-- chemistry-lab-digest:{day} -->", "", f"## Chemistry Lab — {day}", ""]
    if kinds:
        lines.append("Notebook rows: " + ", ".join(f"{name} {kinds[name]}" for name in sorted(kinds)) + ".")
    else:
        lines.append("Notebook rows: none recorded.")
    if experiment_rows:
        lines.append("Experiments:")
        lines.extend(_experiment_line(row) for row in experiment_rows[:12])
    else:
        lines.append("Experiments: none recorded.")
    lines.append(f"Reading receipts: owed/held {owed}; settled {settled}.")
    lines.append("Latest next question: " + (question if question else "none recorded."))
    lines.append("These are Chemistry Lab receipts only. Execution is not correctness, and no scientific or personal conclusion is inferred.")
    return "\n".join(lines) + "\n"


def append(file_day=None, data_day=None):
    """Summarize `data_day` (default: the day before `file_day`) into `file_day`'s file.

    Written to today's carry-forward file like first-light, so his morning brief carries
    yesterday's finished bench day. The marker is keyed to the summarized day, so the same
    day is never appended twice and a fresh file each morning gets the new day's receipt.
    """
    file_day = file_day or date.today().isoformat()
    data_day = data_day or _yesterday(file_day)
    os.makedirs(MEMORY, exist_ok=True)
    path = os.path.join(MEMORY, f"daily-inner-life-{file_day}.md")
    marker = f"<!-- chemistry-lab-digest:{data_day} -->"
    lock_path = os.path.join(MEMORY, ".daily-inner-life.lock")
    with open(lock_path, "a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try: old = open(path, encoding="utf-8", errors="replace").read()
        except FileNotFoundError: old = ""
        if marker in old: return False, path
        with open(path, "a", encoding="utf-8") as handle:
            if old and not old.endswith("\n"): handle.write("\n")
            handle.write("\n" + render(data_day))
            handle.flush(); os.fsync(handle.fileno())
    return True, path


if __name__ == "__main__":
    wrote, target = append()
    print("[chemistry-digest] %s %s" % ("appended" if wrote else "already present", target))
