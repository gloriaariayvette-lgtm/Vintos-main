#!/usr/bin/env python3
"""Append one evidence-honest Forge receipt — yesterday's work — to the inner-life ledger.

first-light runs before dawn and summarizes the PREVIOUS day, so this writes yesterday's
finished Forge activity into today's carry-forward file, with the marker keyed to the
summarized day (idempotent), exactly like lab_daily_digest.py and chemistry_digest.py.

What it can honestly read from disk as Gloria: the house-side mirrors under memory/ —
`atelier-reveals.json` (what he revealed, in his OWN words) and `atelier-undertakings.json`
(which undertakings changed state). The canonical cycle/cost ledger (forge-loop.sqlite) lives
behind the forge service as the atelier user and is deliberately NOT read here — so this is a
receipt of what surfaced and what moved, not a claim about cycles, spend, or intent.
"""
from __future__ import annotations

import fcntl
import json
import os
from collections import Counter
from datetime import date, timedelta

WS = os.environ.get("SPARK_WORKSPACE") or os.path.expanduser("~/.vintos/workspace")
MEMORY = os.path.join(WS, "memory")
REVEALS = os.path.join(MEMORY, "atelier-reveals.json")
UNDERTAKINGS = os.path.join(MEMORY, "atelier-undertakings.json")


def _yesterday(file_day):
    return (date.fromisoformat(file_day) - timedelta(days=1)).isoformat()


def _clip(text, limit=300):
    text = " ".join(str(text or "").split())
    return (text[:limit] + "…") if len(text) > limit else text


def _load(path, default):
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            value = json.load(handle)
        return value
    except (FileNotFoundError, ValueError, TypeError):
        return default


def _on_day(value, day):
    return str(value or "")[:10] == day


def render(day=None):
    day = day or date.today().isoformat()

    reveals_all = _load(REVEALS, [])
    reveals = [r for r in reveals_all if isinstance(r, dict) and r.get("revealed", True) is True
               and _on_day(r.get("revealed_at") or r.get("at"), day)] if isinstance(reveals_all, list) else []

    undertakings = _load(UNDERTAKINGS, {})
    moved = []
    if isinstance(undertakings, dict):
        for pid, rec in undertakings.items():
            if isinstance(rec, dict) and _on_day(rec.get("at"), day):
                moved.append((str(pid), str(rec.get("state") or "unknown")))
    state_counts = Counter(state for _pid, state in moved)

    lines = [f"<!-- forge-digest:{day} -->", "", f"## Forge — {day}", ""]
    if not reveals and not moved:
        lines.append("Quiet day — nothing revealed and no undertaking changed state.")
    else:
        if moved:
            lines.append("Undertakings that changed state: " + ", ".join(
                f"{name} {state_counts[name]}" for name in sorted(state_counts)) + ".")
        else:
            lines.append("Undertakings that changed state: none.")
        if reveals:
            lines.append(f"Revealed: {len(reveals)}.")
            lines.append("What he revealed (his words):")
            for row in reveals[:3]:
                disclosure = _clip(row.get("disclosure") or row.get("disclosure_sentence"))
                medium = _clip(row.get("medium"), 20)
                if disclosure:
                    lines.append("- " + disclosure + (f"  [{medium}]" if medium else ""))
                elif medium:
                    lines.append(f"- (a {medium} piece, revealed without a disclosure line)")
        else:
            lines.append("Revealed: none.")
    lines.append("These are Forge receipts only, from the house-side mirrors — reveals and state changes, "
                 "not cycle counts, spend, or intent, and no conclusion is inferred.")
    return "\n".join(lines) + "\n"


def append(file_day=None, data_day=None):
    """Summarize `data_day` (default: the day before `file_day`) into `file_day`'s file.

    Written to today's carry-forward file like first-light; marker keyed to the summarized
    day so the same day is never appended twice. Idempotent only when the FULL block is
    present — an orphan marker (a rewriter stripped the body) is dropped and rewritten.
    """
    file_day = file_day or date.today().isoformat()
    data_day = data_day or _yesterday(file_day)
    os.makedirs(MEMORY, exist_ok=True)
    path = os.path.join(MEMORY, f"daily-inner-life-{file_day}.md")
    marker = f"<!-- forge-digest:{data_day} -->"
    heading = f"## Forge — {data_day}"
    lock_path = os.path.join(MEMORY, ".daily-inner-life.lock")
    with open(lock_path, "a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            old = open(path, encoding="utf-8", errors="replace").read()
        except FileNotFoundError:
            old = ""
        if marker in old and heading in old:
            return False, path
        if marker in old:
            old = "\n".join(l for l in old.splitlines() if l.strip() != marker.strip()).rstrip()
        new = old + ("\n" if old and not old.endswith("\n") else "") + "\n" + render(data_day)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(new); handle.flush(); os.fsync(handle.fileno())
    return True, path


def backfill(days=7):
    """Self-heal: for each recent carry-forward file that exists but lacks its Forge receipt,
    append it once. A missed first-light morning repairs itself instead of leaving a hole."""
    healed = []
    today = date.today()
    for n in range(1, days + 1):
        fd = (today - timedelta(days=n)).isoformat()
        if os.path.exists(os.path.join(MEMORY, f"daily-inner-life-{fd}.md")):
            wrote, path = append(file_day=fd)
            if wrote:
                healed.append(path)
    return healed


if __name__ == "__main__":
    wrote, target = append()
    print("[forge-digest] %s %s" % ("appended" if wrote else "already present", target))
    healed = backfill(7)
    if healed:
        print("[forge-digest] backfilled %d missed day(s): %s" % (len(healed), ", ".join(healed)))
