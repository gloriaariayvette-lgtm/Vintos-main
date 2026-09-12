#!/usr/bin/env python3
"""Append one evidence-honest Q1 Lab digest to today's inner-life ledger.

This is a mechanical receipt, not a verdict. It says what the hypothesis ledger
recorded and which advisory blocks were withheld in shadow. It deliberately does
not infer functional contribution: shadow-trials.jsonl contains assignments, not
consequences, and presence/withholding counts are not fitness.
"""
import fcntl
import json
import os
from collections import Counter
from datetime import date

WS = os.environ.get("SPARK_WORKSPACE") or os.path.expanduser("~/.vintos/workspace")
MEMORY = os.path.join(WS, "memory")
HYPOTHESES = os.path.join(MEMORY, "hypothesis-ledger.jsonl")
TRIALS = os.path.join(MEMORY, "shadow-trials.jsonl")


def _rows(path):
    out = []
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            for line in handle:
                try:
                    row = json.loads(line)
                except (TypeError, ValueError):
                    continue
                if isinstance(row, dict):
                    out.append(row)
    except FileNotFoundError:
        pass
    return out


def _on_day(row, day):
    return str(row.get("at", ""))[:10] == day


def render(day=None):
    day = day or date.today().isoformat()
    events = [r for r in _rows(HYPOTHESES) if _on_day(r, day)]
    trials = [r for r in _rows(TRIALS) if _on_day(r, day)]
    event_counts = Counter(str(r.get("event") or "unknown") for r in events)
    trial_counts = Counter(str(r.get("block") or r.get("mod") or "unknown") for r in trials)

    lines = [f"<!-- q1-lab-digest:{day} -->", "", "## Admission Lab — daily receipt", ""]
    if event_counts:
        lines.append("Hypothesis-ledger events: " + ", ".join(
            f"{name} {event_counts[name]}" for name in sorted(event_counts)))
        touched = []
        for row in events:
            hid = str(row.get("id") or "").strip()
            block = str(row.get("block") or "").strip()
            label = hid + (f"/{block}" if block else "")
            if hid and label not in touched:
                touched.append(label)
        if touched:
            lines.append("Hypotheses touched: " + ", ".join(touched[:12]))
    else:
        lines.append("Hypothesis-ledger events: none recorded today.")

    if trial_counts:
        lines.append("Shadow withholdings: " + str(len(trials)) + " (" + ", ".join(
            f"{name} {trial_counts[name]}" for name in sorted(trial_counts)) + ").")
    else:
        lines.append("Shadow withholdings: none recorded today.")
    lines.append("These are ledger and assignment receipts only. Functional consequence was not measured here; no result or fitness is inferred.")
    return "\n".join(lines) + "\n"


def append(day=None):
    day = day or date.today().isoformat()
    os.makedirs(MEMORY, exist_ok=True)
    path = os.path.join(MEMORY, f"daily-inner-life-{day}.md")
    marker = f"<!-- q1-lab-digest:{day} -->"
    lock_path = os.path.join(MEMORY, ".daily-inner-life.lock")
    with open(lock_path, "a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            old = open(path, encoding="utf-8", errors="replace").read()
        except FileNotFoundError:
            old = ""
        if marker in old:
            return False, path
        with open(path, "a", encoding="utf-8") as handle:
            if old and not old.endswith("\n"):
                handle.write("\n")
            handle.write("\n" + render(day))
    return True, path


if __name__ == "__main__":
    wrote, target = append()
    print("[lab-digest] %s %s" % ("appended" if wrote else "already present", target))
