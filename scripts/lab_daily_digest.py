#!/usr/bin/env python3
"""Append one evidence-honest Q1 Lab digest — yesterday's work — to the inner-life ledger.

This is a mechanical receipt, not a verdict. It says what the hypothesis ledger
recorded and which advisory blocks were withheld in shadow. It deliberately does
not infer functional contribution: shadow-trials.jsonl contains assignments, not
consequences, and presence/withholding counts are not fitness.
"""
import fcntl
import json
import os
from collections import Counter
from datetime import date, timedelta

WS = os.environ.get("SPARK_WORKSPACE") or os.path.expanduser("~/.vintos/workspace")
MEMORY = os.path.join(WS, "memory")
HYPOTHESES = os.path.join(MEMORY, "hypothesis-ledger.jsonl")
TRIALS = os.path.join(MEMORY, "shadow-trials.jsonl")


def _yesterday(file_day):
    return (date.fromisoformat(file_day) - timedelta(days=1)).isoformat()


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

    def _clip(text, limit=300):
        text = " ".join(str(text or "").split())
        return (text[:limit] + "…") if len(text) > limit else text

    lines = [f"<!-- q1-lab-digest:{day} -->", "", f"## Admission Lab — {day}", ""]
    if not events and not trials:
        lines.append("Quiet day — no hypothesis events or shadow withholdings recorded.")
    else:
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
            lines.append("Hypothesis-ledger events: none recorded.")
        if trial_counts:
            lines.append("Shadow withholdings: " + str(len(trials)) + " (" + ", ".join(
                f"{name} {trial_counts[name]}" for name in sorted(trial_counts)) + ").")
        else:
            lines.append("Shadow withholdings: none recorded.")
        # His own words, quoted — the written falsifiable claim and any ruling's reason,
        # never the sealed evaluation numbers. This is what a hypothesis IS, not a result.
        proposed = [f"- {_clip(r.get('claim'))}" for r in events
                    if r.get("event") == "proposed" and str(r.get("claim") or "").strip()][:2]
        if proposed:
            lines.append("Hypotheses proposed:"); lines.extend(proposed)
        rulings = []
        for r in events:
            if r.get("event") != "ruled":
                continue
            rid = str(r.get("id") or "").strip(); verdict = str(r.get("verdict") or "").strip()
            reason = _clip(r.get("reason"), 200)
            rulings.append("- " + (rid + " " if rid else "") + verdict + (" — " + reason if reason else ""))
            if len(rulings) >= 2:
                break
        if rulings:
            lines.append("Rulings:"); lines.extend(rulings)
    lines.append("These are ledger and assignment receipts only. Functional consequence was not measured here; no result or fitness is inferred.")
    return "\n".join(lines) + "\n"


def append(file_day=None, data_day=None):
    """Summarize `data_day` (default: the day before `file_day`) into `file_day`'s file.

    first-light summarizes the previous day; a 5am receipt of the current day is empty by
    construction. So this writes yesterday's finished receipt into today's carry-forward
    file, with the marker keyed to the summarized day for idempotence.
    """
    file_day = file_day or date.today().isoformat()
    data_day = data_day or _yesterday(file_day)
    os.makedirs(MEMORY, exist_ok=True)
    path = os.path.join(MEMORY, f"daily-inner-life-{file_day}.md")
    marker = f"<!-- q1-lab-digest:{data_day} -->"
    heading = f"## Admission Lab — {data_day}"
    lock_path = os.path.join(MEMORY, ".daily-inner-life.lock")
    with open(lock_path, "a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            old = open(path, encoding="utf-8", errors="replace").read()
        except FileNotFoundError:
            old = ""
        # Idempotent only when the FULL block is present. A marker with no body — left when a
        # rewriter stripped the section — must not count as present, or it blocks the restore
        # forever. Drop the orphan marker, then rewrite the full block.
        if marker in old and heading in old:
            return False, path
        if marker in old:
            old = "\n".join(l for l in old.splitlines() if l.strip() != marker.strip()).rstrip()
        new = old + ("\n" if old and not old.endswith("\n") else "") + "\n" + render(data_day)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(new); handle.flush(); os.fsync(handle.fileno())
    return True, path


def backfill(days=7):
    """Self-heal: for each of the last `days` carry-forward files that exist but are
    missing their receipt, append it. A missed first-light morning then repairs itself
    instead of leaving a permanent hole."""
    healed = []
    today = date.today()
    for n in range(1, days + 1):
        fd = (today - timedelta(days=n)).isoformat()
        if os.path.exists(os.path.join(MEMORY, f"daily-inner-life-{fd}.md")):
            wrote, path = append(file_day=fd)
            if wrote: healed.append(path)
    return healed


if __name__ == "__main__":
    wrote, target = append()
    print("[lab-digest] %s %s" % ("appended" if wrote else "already present", target))
    healed = backfill(7)
    if healed: print("[lab-digest] backfilled %d missed day(s): %s" % (len(healed), ", ".join(healed)))
