#!/usr/bin/env python3
"""Append one evidence-honest Forge receipt — yesterday's work — to the inner-life ledger.

first-light runs before dawn and summarizes the PREVIOUS day, so this writes yesterday's
finished Forge activity into today's carry-forward file, with the marker keyed to the
summarized day (idempotent), exactly like chemistry_digest.py.

The Forge is NOT the Atelier. The Forge builds capabilities Gloria pays for, so this receipt
NAMES what the Forge is building — its intent, state and spend — read from the Forge's own owner
API on localhost (the stored owner token the digest already runs with; no interactive code). Only
a project inside a PRIVATE interval (his opt-in Atelier-style seal, `private=True`) keeps its intent
sealed here, exactly as the Forge's own status() seals it; everything else is shown in plain words.
`atelier-reveals.json` still supplies what he chose to reveal, in his own words. If the Forge service
is unreachable the receipt falls back to the content-free house mirror rather than fabricating.
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
FORGE_BASE = os.environ.get("VINTOS_FORGE_BASE", "http://127.0.0.1:8612")
FORGE_OWNER_TOKEN = os.path.expanduser("~/.config/vintos/forge-owner")
# Terminal states are done; a daily receipt shows what is live (what she is paying for now).
LIVE_STATES = ("ready", "active", "authorized", "awaiting_application", "building", "resumed")


# The project list passed 1 MiB in October 2026 (~1.2 MB). The old 1 MiB + 1 read cut it mid-JSON, the
# parse failed, and every morning's receipt said the Forge was unreachable when it had answered.
FORGE_MAX_BYTES = 8 * 1024 * 1024
# Why the last read returned None: "unreachable", "too large" or "parse error" (each said differently).
FORGE_FAILURE = "unreachable"


def _forge_projects(transport=None, opener=None):
    """Best-effort read of the Forge's own project list (owner token, localhost). Returns a list of
    {id,state,intent,private,spent,cycles,...} or None — never raises. On None, FORGE_FAILURE says
    whether the Forge was unreachable or answered with a list too large or unreadable."""
    global FORGE_FAILURE
    FORGE_FAILURE = "unreachable"
    if transport is not None:
        try:
            return transport()
        except Exception:
            return None
    try:
        from urllib.request import Request, urlopen
        from forge_loop_runtime import secret
        req = Request(FORGE_BASE + "/api/projects", method="GET",
                      headers={"Authorization": "Bearer " + secret(FORGE_OWNER_TOKEN)})
        with (opener or urlopen)(req, timeout=6) as response:
            body = response.read(FORGE_MAX_BYTES + 1)
    except Exception:
        return None
    if len(body) > FORGE_MAX_BYTES:
        FORGE_FAILURE = "too large"
        return None
    try:
        data = json.loads(body)
    except (ValueError, TypeError):
        FORGE_FAILURE = "parse error"
        return None
    if not isinstance(data, list):
        FORGE_FAILURE = "parse error"
        return None
    return data


def _failure_words(failure):
    if failure == "too large":
        return "its project list was larger than the digest reads (over %d MiB)" % (FORGE_MAX_BYTES // (1024 * 1024))
    if failure == "parse error":
        return "its project list could not be read (parse error)"
    return "unreachable"


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


def _reveal_lines(reveals):
    out = []
    if reveals:
        out.append(f"Revealed: {len(reveals)}.")
        out.append("What he revealed (his words):")
        for row in reveals[:3]:
            disclosure = _clip(row.get("disclosure") or row.get("disclosure_sentence"))
            medium = _clip(row.get("medium"), 20)
            # a piece made from a dream stays marked as one (proposal 07)
            dreamt = "  [made from a dream he had, not something that happened]" if row.get("from_dream") else ""
            if disclosure:
                out.append("- " + disclosure + (f"  [{medium}]" if medium else "") + dreamt)
            elif medium:
                out.append(f"- (a {medium} piece, revealed without a disclosure line)" + dreamt)
    else:
        out.append("Revealed: none.")
    return out


def _cost(project):
    spent, ceiling, cycles = project.get("spent"), project.get("ceiling"), project.get("cycles", 0)
    if isinstance(spent, (int, float)) and spent:
        tail = f" of ${ceiling / 100:.2f}" if isinstance(ceiling, (int, float)) and ceiling else ""
        return f"  [${spent / 100:.2f}{tail}, {cycles} cycle(s)]"
    return f"  [{cycles} cycle(s)]" if cycles else ""


def render(day=None, projects=None):
    day = day or date.today().isoformat()

    reveals_all = _load(REVEALS, [])
    reveals = [r for r in reveals_all if isinstance(r, dict) and r.get("revealed", True) is True
               and _on_day(r.get("revealed_at") or r.get("at"), day)] if isinstance(reveals_all, list) else []

    global FORGE_FAILURE
    if projects is None:
        FORGE_FAILURE = "unreachable"
        projects = _forge_projects()
    failure = FORGE_FAILURE

    lines = [f"<!-- forge-digest:{day} -->", "", f"## Forge — {day}", ""]

    if projects is not None:
        # The Forge is what she pays for — name it. Intent is present iff the project is not in a
        # private interval (the Forge's own status() seals intent to None only while private).
        live = [p for p in projects if isinstance(p, dict) and str(p.get("state")) in LIVE_STATES]
        named = [p for p in live if p.get("intent")]
        sealed = [p for p in live if not p.get("intent")]
        if not named and not sealed and not reveals:
            lines.append("Quiet day — the Forge is building nothing and nothing was revealed.")
        else:
            if named:
                total = sum(p.get("spent") or 0 for p in live if isinstance(p.get("spent"), (int, float)))
                # it said "you are paying for this" over $0 of local work (2026-10-03: "We need to fix that 0")
                lines.append("What the Forge is working on (%s):" % (
                    "spent so far: $%.2f" % (total / 100) if total else "nothing charged: it runs on the local model, $0"))
                for p in named[:8]:
                    lines.append(f"- {_clip(p['intent'])} — {p.get('state', '?')}{_cost(p)}")
            else:
                lines.append("The Forge is building nothing right now.")
            if sealed:
                lines.append(f"Private undertakings sealed: {len(sealed)} "
                             "(his own interval — intent hidden until he reveals it or it ends).")
            lines.extend(_reveal_lines(reveals))
        lines.append("\"ready\" means waiting for its next step; nothing is needed from you unless a card asks for "
                     "your yes. These are the Forge's own figures; only a private interval stays sealed.")
    else:
        # Forge unreachable — fall back to the content-free house mirror rather than fabricate.
        undertakings = _load(UNDERTAKINGS, {})
        moved = []
        if isinstance(undertakings, dict):
            for pid, rec in undertakings.items():
                if isinstance(rec, dict) and _on_day(rec.get("at"), day):
                    moved.append((str(pid), str(rec.get("state") or "unknown")))
        state_counts = Counter(state for _pid, state in moved)
        if not reveals and not moved:
            lines.append("Quiet day — Forge %s; nothing revealed and no undertaking changed state."
                         % ("unreachable" if failure == "unreachable" else "list unread (%s)" % failure))
        else:
            if moved:
                lines.append("Undertakings that changed state: " + ", ".join(
                    f"{name} {state_counts[name]}" for name in sorted(state_counts)) + ".")
            else:
                lines.append("Undertakings that changed state: none.")
            lines.extend(_reveal_lines(reveals))
        lead = ("Forge service was unreachable this morning" if failure == "unreachable"
                else "The Forge answered this morning, but %s" % _failure_words(failure))
        lines.append(lead + " — this is the content-free house mirror "
                     "only (state changes and reveals), not intent or spend. No conclusion is inferred.")
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
