#!/usr/bin/env python3
"""outcome_join.py - one way to find the exchange an outcome is judged against, and one record of
every judged outcome.

Review item 225 (2026-09-10). intent_engine, lead_trials and plan each found "his reply" and "what
happened after" in their own way (last ledger row; the row at a remembered index; nothing) and wrote
their verdicts to their own files. The evaluators keep their own questions (an intent, a lead plan, a
plan window are different judgments) but they share the join and the record now, and the experimental
mechanisms that are OFF are named here rather than remembered.

    exchange_at(index=None, turn_id=None)   -> the ledger row (gloria, vintos, timestamp, turn_id) or None
    latest_exchange()                        -> the last row
    after(index)                             -> rows after that index (what happened next)
    record(kind, ref, verdict, detail=None)  -> memory/outcome-joins.jsonl
    EXPERIMENTAL                             -> named off switches
"""
import os, sys, json, time

WS = os.path.expanduser("~/.vintos/workspace")
MEMORY = os.path.join(WS, "memory")
LEDGER = os.path.join(MEMORY, "interaction-ledger.json")
JOINS = os.path.join(MEMORY, "outcome-joins.jsonl")
KINDS = ("intent", "lead", "plan", "want")

# Explicitly OFF. A reader who wonders whether these run finds the answer here, not in a comment.
EXPERIMENTAL = {
    "bis_trials": "off - intent outcomes nudge valence only; no blush, no scar (Gloria)",
    "lead_penalty": "off - a lead miss records and expires; no pressure",
    "interventions": "off unless an approved experiment exists under memory/experiments (review 209)",
}


def _rows():
    try:
        d = json.load(open(LEDGER))
    except Exception:
        return []
    rows = d if isinstance(d, list) else d.get("entries", []) if isinstance(d, dict) else []
    return [r for r in rows if isinstance(r, dict)]


def _shape(i, r):
    return {"index": i, "timestamp": r.get("timestamp", ""), "turn_id": r.get("turn_id"),
            "gloria": r.get("gloria") or "", "vintos": r.get("vintos") or r.get("velaris") or r.get("reply") or "",
            "channel": r.get("channel") or r.get("source") or ""}


def exchange_at(index=None, turn_id=None):
    rows = _rows()
    if turn_id:
        for i, r in enumerate(rows):
            if r.get("turn_id") == turn_id:
                return _shape(i, r)
        return None
    if index is None:
        return _shape(len(rows) - 1, rows[-1]) if rows else None
    if 0 <= index < len(rows):
        return _shape(index, rows[index])
    return None


def latest_exchange():
    return exchange_at()


def after(index, limit=3):
    rows = _rows()
    return [_shape(i, r) for i, r in enumerate(rows) if i > index][:limit]


def record(kind, ref, verdict, detail=None, at=None):
    if kind not in KINDS:
        raise ValueError("outcome kind %r not in %s" % (kind, KINDS))
    row = {"kind": kind, "ref": ref, "verdict": verdict, "at": at or time.strftime("%Y-%m-%dT%H:%M:%S"), "detail": detail or {}}
    try:
        os.makedirs(MEMORY, exist_ok=True)
        with open(JOINS, "a") as f:
            f.write(json.dumps(row, default=str) + "\n")
    except OSError:
        pass
    return row


def outcomes(kind=None, limit=50):
    out = []
    try:
        for ln in open(JOINS):
            try:
                r = json.loads(ln)
            except Exception:
                continue
            if kind is None or r.get("kind") == kind:
                out.append(r)
    except Exception:
        pass
    return out[-limit:]


if __name__ == "__main__":
    print("experimental:", json.dumps(EXPERIMENTAL, indent=1))
    for o in outcomes(limit=10):
        print("  %s %-6s %-8s %s" % (o["at"][:16], o["kind"], o["verdict"], o.get("ref")))
