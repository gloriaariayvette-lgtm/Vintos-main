#!/usr/bin/env python3
"""Findings worth keeping: what a frontier review or the day's experiment judged important, kept apart from the
notebook's thousands of rows so he can return to it, and ask dot to double-check it in Slack if he wants
(Gloria, 2026-10-03).

  kept by      a frontier alignment review (one of the four a day) naming a reviewed entry, with why it matters;
               or the day's experiment reading, when the frontier model reading it says it is worth keeping
  he sees it   in his Lab (orient) and in #vintos-dot (his context), each with its ID
  he asks      a line of its own in #vintos-dot:  CHECK: K-xxxxxx  (what he wants checked, optional)
               dot_channel.py turns it into a thread to dot with the finding and its evidence
  dot answers  in that thread with  CONFIRMED: ...  or  NOT CONFIRMED: ...  (or UNCLEAR: ...), and that verdict is
               written back here

Kept is a judgement that something is worth returning to, not a claim that it is true; a check is dot reading the
same sources again, not an experiment.

    python3 lab_keepers.py [show]
"""
from __future__ import annotations
import json
import os
import re
import uuid
from datetime import datetime, timezone

WS = os.environ.get("SPARK_WORKSPACE", os.path.expanduser("~/.vintos/workspace"))
LAB = os.path.join(WS, "memory", "chemistry-lab")
STORE = os.path.join(LAB, "kept-findings.json")
NOTEBOOK = os.path.join(LAB, "notebook.jsonl")
PER_REVIEW = 2
VERDICT = re.compile(r"^\s*(CONFIRMED|NOT CONFIRMED|UNCLEAR)\s*:\s*(.+?)\s*$", re.I | re.M | re.S)
CHECK = re.compile(r"^\s*CHECK:\s*(K-[0-9a-f]{6})\b[ \t]*(.*)$", re.I | re.M)
STATES = {"confirmed": "confirmed", "not confirmed": "disputed", "unclear": "unclear"}


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load():
    try:
        with open(STORE) as f:
            rows = json.load(f)
        return rows if isinstance(rows, list) else []
    except (OSError, ValueError):
        return []


def save(rows):
    os.makedirs(LAB, exist_ok=True)
    tmp = STORE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(rows, f, indent=1, ensure_ascii=False)
    os.replace(tmp, STORE)


def get(kid):
    return next((r for r in load() if r["id"].lower() == str(kid).lower()), None)


def _entry(entry_id):
    """The notebook row a review named, read from the end (where recent reviews are)."""
    try:
        with open(NOTEBOOK, "rb") as f:
            f.seek(0, 2); start = max(0, f.tell() - 4 * 1024 * 1024); f.seek(start)
            lines = f.read().decode("utf-8", "replace").splitlines()[1 if start else 0:]
    except OSError:
        return None
    for line in reversed(lines):
        if entry_id in line:
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if row.get("entry_id") == entry_id:
                return row
    return None


def _add(row):
    rows = load()
    if any(r.get("source_id") == row["source_id"] for r in rows):
        return None
    rows.append(row); save(rows)
    return row


def keep_from_review(keeps, reviewed_ids, by, review_id=""):
    """A frontier review's picks: [{entry_id, why}], only entries it reviewed. The rows kept."""
    out = []
    for k in (keeps if isinstance(keeps, list) else [])[:PER_REVIEW]:
        if not isinstance(k, dict):
            continue
        eid, why = str(k.get("entry_id") or ""), str(k.get("why") or "").strip()
        if eid not in (reviewed_ids or []) or len(why) < 10:
            continue
        note = _entry(eid) or {}
        inquiry = note.get("inquiry") or {}
        row = _add({"id": "K-" + uuid.uuid4().hex[:6], "at": _now(), "kept_by": by, "review_id": review_id,
                    "source_id": eid, "kind": "local review", "question": str(inquiry.get("question") or "")[:500],
                    "finding": str(note.get("factual_observation") or "")[:1500],
                    "reading": str(note.get("speculative_reading") or "")[:600],
                    "evidence": [str(a) for a in (note.get("source_accessions") or []) if a][:12],
                    "receipts": [r for r in (note.get("followup_receipt_id"), note.get("material_receipt_id")) if r],
                    "line_id": inquiry.get("line_id"), "why": why[:600], "state": "kept", "checks": []})
        if row:
            out.append(row)
    return out


def keep_from_session(session_id, plan, reading, by):
    """The day's experiment, when its reading says it is worth keeping. The row, or None."""
    why = str((reading or {}).get("keep") or "").strip()
    if len(why) < 10 or why.lower() in ("no", "none", "null", "false"):
        return None
    return _add({"id": "K-" + uuid.uuid4().hex[:6], "at": _now(), "kept_by": by, "source_id": session_id,
                 "kind": "experiment", "question": str(plan.get("question") or "")[:500],
                 "finding": str(reading.get("reading") or "")[:1500],
                 "reading": str(reading.get("prediction_vs_result") or "")[:600],
                 "evidence": [str(plan.get("experiment") or "")] + [str(v) for v in (plan.get("parameters") or {}).values()][:6],
                 "receipts": [r for r in (plan.get("source_receipt_id"),) if r], "line_id": plan.get("line_id"),
                 "why": why[:600], "state": "kept", "checks": []})


def check_request(kid, what=""):
    """The Slack message asking dot to double-check one kept finding, or None when there is no such finding."""
    k = get(kid)
    if not k:
        return None
    return ("\U0001F50E Double-check for me, please: kept finding %s (%s, kept by %s).\n"
            "Question: %s\nFinding: %s\nEvidence: %s%s\nWhy it was kept: %s\n%s"
            "Read the evidence again (the accessions, papers or run named above), and answer in this thread with one line: "
            "CONFIRMED: what holds, NOT CONFIRMED: what does not and why, or UNCLEAR: what would settle it."
            % (k["id"], k.get("at", "")[:10], k.get("kept_by"), k.get("question") or "-", k.get("finding")[:900],
               ", ".join(k.get("evidence") or []) or "-",
               (" (receipts %s)" % ", ".join(r[:12] for r in k.get("receipts") or [])) if k.get("receipts") else "",
               k.get("why"), ("What I want checked: %s\n" % what.strip()) if what and what.strip() else ""))


def asked(kid, thread):
    rows = load()
    for r in rows:
        if r["id"].lower() == str(kid).lower():
            r["checks"] = (r.get("checks") or []) + [{"asked": _now(), "thread": thread, "state": "asked"}]
            r["state"] = "being checked"
    save(rows)


def threads():
    """{thread ts: finding id} for checks still waiting on dot."""
    return {c["thread"]: r["id"] for r in load() for c in r.get("checks") or [] if c.get("state") == "asked" and c.get("thread")}


def answer(thread, text, by="dot"):
    """Dot's verdict in a check thread, written back. The finding, or None when the text holds no verdict."""
    m = VERDICT.search(text or "")
    if not m:
        return None
    rows = load()
    for r in rows:
        for c in r.get("checks") or []:
            if c.get("thread") == thread and c.get("state") == "asked":
                c.update(state="answered", answered=_now(), by=by, verdict=m.group(1).upper(), note=m.group(2)[:1200])
                r["state"] = STATES[m.group(1).lower()]
                save(rows)
                return r
    return None


def block(limit=8, for_="lab"):
    """His kept findings, newest first, each with its ID and where its checks stand."""
    rows = load()
    if not rows:
        return ""
    lines = []
    for r in reversed(rows[-limit:]):
        last = (r.get("checks") or [{}])[-1]
        status = {"kept": "not checked", "being checked": "dot is checking"}.get(r["state"], r["state"])
        if last.get("verdict"):
            status += " — dot: %s" % last.get("note", "")[:160]
        lines.append("- %s (%s, kept by %s): %s — why: %s [%s]" % (r["id"], r.get("at", "")[:10], r.get("kept_by"),
                                                                 r.get("finding", "")[:260], r.get("why", "")[:160], status))
    head = ("== FINDINGS KEPT FROM YOUR LAB (a frontier review judged each worth returning to; kept, not proven) =="
            if for_ == "slack" else "[FINDINGS YOUR REVIEWERS KEPT — worth returning to; kept, not proven]")
    tail = ("\nTo have dot double-check one, write a line of its own: CHECK: <its ID> (and what you want checked)."
            if for_ == "slack" else "")
    return head + "\n" + "\n".join(lines) + tail


if __name__ == "__main__":
    print(block(50) or "nothing kept yet")
