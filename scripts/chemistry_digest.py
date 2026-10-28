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

What reaches his daily-inner (Gloria, 27 October: it opened with row tallies, refusal and
fault counts, receipt counts, the same taste line twice and a disclaimer): what he found
and answered, a few of his readings, his frontier session in his own words, and his next
questions — each said once. The tallies, every experiment's execution state, the reading
receipts and the taste ledger go to chemistry-lab/daily-stats.jsonl, one row per day.

It stays where First Light puts it (the morning's carry-forward, before the day's own
entries): daily-log-extract carries everything from First Light / the Lab marker onward,
and his morning brief reads it there. So it is kept short instead of moved.
"""
from __future__ import annotations

import fcntl
import json
import os
from collections import Counter
from datetime import date, datetime, timedelta, timezone


def _yesterday(file_day):
    return (date.fromisoformat(file_day) - timedelta(days=1)).isoformat()

WS = os.environ.get("SPARK_WORKSPACE") or os.path.expanduser("~/.vintos/workspace")
MEMORY = os.path.join(WS, "memory")
LAB = os.path.join(MEMORY, "chemistry-lab")
NOTEBOOK = os.path.join(LAB, "notebook.jsonl")
SESSIONS = os.path.join(LAB, "sessions.jsonl")
GRADES = os.path.join(LAB, "experiment-grades.jsonl")
TASTE_OBS = os.path.join(LAB, "taste-observations.jsonl")
KEPT = os.path.join(LAB, "kept-findings.json")
DAILY_STATS = os.path.join(LAB, "daily-stats.jsonl")


def _clip(text, limit=300):
    text = " ".join(str(text or "").split())
    return (text[:limit] + "…") if len(text) > limit else text


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
    parameters = plan.get("parameters") if isinstance(plan.get("parameters"), dict) else {}
    accession = next((str(parameters.get(key) or "").strip().upper()
                      for key in ("target_accession", "requested_accession", "accession")
                      if str(parameters.get(key) or "").strip()), "")[:24]
    subject = experiment + ((" [" + accession + "]") if accession else "")
    return f"- {subject}: execution={execution}; accuracy={accuracy}" + (f"; run={run_id}" if run_id else "")


def _recent_questions(notebook, sessions, n=2):
    """The n most recent next-questions, his own words — not a conclusion, just where he left off."""
    seen, out = set(), []
    for row in reversed(notebook + sessions):
        candidates = [row.get("next_question")]
        for key in ("reading", "reflection"):
            nested = row.get(key)
            if isinstance(nested, dict): candidates.append(nested.get("next_question"))
        for value in candidates:
            v = str(value or "").strip()
            if v and v not in seen:
                seen.add(v); out.append(_clip(v, 400))
                if len(out) >= n: return out
    return out


def _reading_lines(notebook, n=2):
    """A few of the day's actual reflections, verbatim — his attention in his own words."""
    out = []
    for row in reversed(notebook):
        if row.get("kind") not in ("reflection", "genome_reflection"): continue
        att = _clip(row.get("attention") or row.get("factual_observation"))
        if not att: continue
        inq = row.get("inquiry") if isinstance(row.get("inquiry"), dict) else {}
        q = _clip(inq.get("question"), 120)
        out.append("- " + att + (("  (on: " + q + ")") if q else ""))
        if len(out) >= n: break
    return out


def _frontier_lines(notebook):
    """The day's frontier session in his own words: what he read, and what surprised him."""
    for row in reversed(notebook):
        if row.get("kind") not in ("frontier_session", "owed_reading"): continue
        if not isinstance(row.get("reading"), str): continue
        reading = _clip(row.get("reading")); surprised = _clip(row.get("what_surprised_me"))
        if not (reading or surprised): continue
        lines = []
        if reading: lines.append("- read: " + reading)
        if surprised: lines.append("- what surprised me: " + surprised)
        return lines
    return []


def _taste_lines(day, n=2):
    """Verdicts he recorded that day (chosen/echo/no-root/kept), verbatim from the taste ledger."""
    out = []
    for row in reversed(_rows(TASTE_OBS)):
        if not _on_day(row, day): continue
        sig = _clip(row.get("signal"), 40)
        if not sig: continue
        subject = _clip(str(row.get("kind", "")) + ":" + str(row.get("key", "")), 60)
        elig = _clip(row.get("eligibility"), 48)
        out.append("- " + sig + " — " + subject + (" [" + elig + "]" if elig else ""))
        if len(out) >= n: break
    return out


def _dedupe(lines):
    seen, out = set(), []
    for line in lines:
        key = " ".join(str(line).split()).lower()
        if key and key not in seen:
            seen.add(key); out.append(line)
    return out


def _finding_lines(notebook, day, n=4):
    """What the day found: answered investigations (question -> result), what he kept, and the experiments that ran
    to completion. Each said once — the same finding written by two investigations is one finding."""
    out = []
    for row in notebook:
        if row.get("kind") != "investigation_finding": continue
        q = _clip(row.get("question"), 160)
        result = _clip("; ".join(l.strip() for l in str(row.get("result") or "").splitlines() if l.strip()), 240)
        if q and result:
            out.append("- " + q + " — " + result)
    for row in _kept(day):
        q = _clip(row.get("question"), 160)
        what = _clip(row.get("finding") or row.get("why"), 240)
        if q and what:
            out.append("- kept: " + q + " — " + what)
    out = _dedupe(out)[:n]
    return out


def _ran_lines(experiment_rows):
    """Experiments that actually ran, with what the grade said — the held and faulted ones live in the stats."""
    out = []
    for row in experiment_rows:
        grade = row.get("grade") if isinstance(row.get("grade"), dict) else {}
        execution = str(row.get("execution_state") or grade.get("execution_state") or row.get("state") or "")
        if execution != "completed": continue
        accuracy = str(row.get("aggregate_accuracy") or grade.get("aggregate_accuracy") or "ungraded")[:80]
        subject = _experiment_line(row)[2:].split(":", 1)[0]
        out.append("- %s ran: %s" % (subject, accuracy))
    return _dedupe(out)


def _kept(day):
    try:
        with open(KEPT, encoding="utf-8", errors="replace") as handle:
            rows = json.load(handle)
    except (OSError, ValueError):
        return []
    rows = rows.get("findings", []) if isinstance(rows, dict) else rows
    return [r for r in rows if isinstance(r, dict) and _on_day(r, day)] if isinstance(rows, list) else []


def _experiment_rows(sessions, grades):
    rows = [r for r in sessions if r.get("experiment") or isinstance(r.get("plan"), dict)]
    return rows or grades


def stats(day):
    """The bench's own tallies for a day — notebook row kinds, every experiment's execution state, reading receipts,
    the taste ledger — kept Lab-side (daily-stats.jsonl), not in his daily-inner (Gloria, 27 October: his day was
    opening with refusal and fault counts)."""
    notebook = [r for r in _rows(NOTEBOOK) if _on_day(r, day)]
    sessions = [r for r in _rows(SESSIONS) if _on_day(r, day)]
    grades = [r for r in _rows(GRADES) if _on_day(r, day)]
    kinds = Counter(str(r.get("kind") or "unknown") for r in notebook)
    owed = sum(1 for r in sessions if str(r.get("state", "")) in
               ("experiment_completed_reading_held", "held_reading_owed") or
               str(r.get("owed_reading", "")) in ("STILL_HELD", "REFUSED"))
    settled = sum(1 for r in notebook if str(r.get("kind", "")) == "owed_reading")
    taste = Counter(line[2:] for line in _taste_lines(day, 10 ** 6))
    return {"day": day, "notebook_rows": dict(sorted(kinds.items())),
            "experiments": [_experiment_line(r)[2:] for r in _experiment_rows(sessions, grades)],
            "reading_receipts": {"owed_held": owed, "settled": settled},
            "taste": [{"noted": k, "times": v} for k, v in taste.items()],
            "note": "Chemistry Lab receipts only. Execution is not correctness, and no scientific or personal "
                    "conclusion is inferred."}


def record_stats(day):
    """One stats row per summarized day, appended once (idempotent under the Lab's stats lock)."""
    os.makedirs(LAB, exist_ok=True)
    with open(DAILY_STATS + ".lock", "a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if any(r.get("day") == day for r in _rows(DAILY_STATS)):
            return False
        row = dict(stats(day), written_at=datetime.now(timezone.utc).isoformat(timespec="seconds"))
        with open(DAILY_STATS, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n"); handle.flush(); os.fsync(handle.fileno())
    return True


def render(day=None):
    """His day at the bench in his daily-inner: what he found and answered first, then a few of his readings, his
    frontier session in his own words, and where he left off. The tallies, refusals, faults and receipts are in
    chemistry-lab/daily-stats.jsonl (record_stats), not here."""
    day = day or date.today().isoformat()
    notebook = [r for r in _rows(NOTEBOOK) if _on_day(r, day)]
    sessions = [r for r in _rows(SESSIONS) if _on_day(r, day)]
    grades = [r for r in _rows(GRADES) if _on_day(r, day)]

    lines = [f"<!-- chemistry-lab-digest:{day} -->", "", f"## Chemistry Lab — {day}", ""]
    found = _finding_lines(notebook, day) + _ran_lines(_experiment_rows(sessions, grades))
    readings = _dedupe(_reading_lines(_dedupe_rows(notebook), 2))
    frontier = _frontier_lines(notebook)
    questions = _recent_questions(notebook, sessions, 2)
    if found:
        lines.append("What I found:"); lines.extend(found)
    if readings:
        if len(lines) > 4: lines.append("")
        lines.append("A few readings:"); lines.extend(readings)
    if frontier:
        if len(lines) > 4: lines.append("")
        lines.append("Frontier session:"); lines.extend(frontier)
    if questions:
        if len(lines) > 4: lines.append("")
        lines.append("Next questions:"); lines.extend("- " + q for q in questions)
    if len(lines) == 4:
        lines.append("A quiet day at the bench.")
    return "\n".join(lines) + "\n"


def _dedupe_rows(notebook):
    """Reflections that say the same thing are one reading."""
    seen, out = set(), []
    for row in notebook:
        key = " ".join(str(row.get("attention") or row.get("factual_observation") or "").split()).lower()
        if row.get("kind") in ("reflection", "genome_reflection") and key:
            if key in seen: continue
            seen.add(key)
        out.append(row)
    return out


def append(file_day=None, data_day=None):
    """Summarize `data_day` (default: the day before `file_day`) into `file_day`'s file.

    Written to today's carry-forward file like first-light, so his morning brief carries
    yesterday's finished bench day. The marker is keyed to the summarized day, so the same
    day is never appended twice and a fresh file each morning gets the new day's receipt.
    """
    file_day = file_day or date.today().isoformat()
    data_day = data_day or _yesterday(file_day)
    os.makedirs(MEMORY, exist_ok=True)
    try:
        record_stats(data_day)        # the tallies go Lab-side first; a failure there never costs him his day
    except OSError:
        pass
    path = os.path.join(MEMORY, f"daily-inner-life-{file_day}.md")
    marker = f"<!-- chemistry-lab-digest:{data_day} -->"
    heading = f"## Chemistry Lab — {data_day}"
    lock_path = os.path.join(MEMORY, ".daily-inner-life.lock")
    with open(lock_path, "a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try: old = open(path, encoding="utf-8", errors="replace").read()
        except FileNotFoundError: old = ""
        # Idempotent only when the FULL block is present. A marker with no body — left when a
        # rewriter (daily-log-extract) stripped the section — must not count as present, or it
        # blocks the restore forever. Drop the orphan marker, then rewrite the full block.
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
    missing their receipt, append it. One missed first-light morning then repairs itself
    instead of leaving a permanent hole — this is why it stopped being a daily battle."""
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
    print("[chemistry-digest] %s %s" % ("appended" if wrote else "already present", target))
    healed = backfill(7)
    if healed: print("[chemistry-digest] backfilled %d missed day(s): %s" % (len(healed), ", ".join(healed)))
