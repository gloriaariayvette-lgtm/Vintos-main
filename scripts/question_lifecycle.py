#!/usr/bin/env python3
"""question_lifecycle.py - every question he is carrying, in one lifecycle, and what changed since last time.

Review items 260 and 262 (2026-09-10). Questions live in four places with four vocabularies: the
causality bring-up queue (queued), the thread pool (a thread of kind question, consumed by a dream or
not), the unsaid questions (turns waited, asked or not), and the tension questions (HYPOTHESIS /
SUPPORTED / CONTESTED / CONTRADICTED). This module reads all four into one lifecycle -

    selected -> explored -> consolidated -> resolved (with basis) | released_unresolved (with basis)

- never rewriting the sources, and keeps a cross-session view: each run compares against the last
view and records which question changed state, why (the basis the source carries), and what remains
open.

    view()                      the questions with their state and basis
    changes(write=True)         {changed: [...], open: [...], resolved_since: [...]} against the last view
    advance(qid, state, basis)  a state he or an organ asserts explicitly (memory/question-lifecycle.jsonl)
    python3 question_lifecycle.py
"""
import os, sys, json, time

WS = os.path.expanduser("~/.vintos/workspace")
MEMORY = os.path.join(WS, "memory")
STATES = ("selected", "explored", "consolidated", "resolved", "released_unresolved")
VIEW = os.path.join(MEMORY, "question-view.json")
ASSERTED = os.path.join(MEMORY, "question-lifecycle.jsonl")


def _load(name, default):
    try:
        return json.load(open(os.path.join(MEMORY, name)))
    except Exception:
        return default


def _asserted():
    out = {}
    try:
        for ln in open(ASSERTED):
            try:
                r = json.loads(ln); out[r["id"]] = r
            except Exception:
                pass
    except Exception:
        pass
    return out


def _from_bring_up():
    d = _load("causality-bring-up.json", [])
    items = d.get("items", []) if isinstance(d, dict) else d
    for x in items or []:
        if not isinstance(x, dict) or not x.get("question"):
            continue
        st = {"queued": "selected", "asked": "explored", "answered": "resolved", "graduated": "consolidated", "held": "explored"}.get(str(x.get("status", "queued")), "selected")
        yield {"id": x.get("id") or ("CQ-" + str(x.get("question"))[:24]), "question_id": x.get("id"), "question": x["question"], "source": "causality:" + str(x.get("source", "")),
               "state": st, "basis": "status %s in the bring-up queue" % x.get("status", "queued"), "since": x.get("formed")}


def _from_threads():
    for t in _load("unfinished-threads.json", []) or []:
        if not isinstance(t, dict) or t.get("kind") != "question":
            continue
        if t.get("retired"):
            st, basis = ("resolved", "archived: " + str(t.get("retired_reason") or t.get("consumed_by", ""))) if t.get("retired_reason") not in ("expired", "released") else ("released_unresolved", str(t.get("retired_reason", "released")))
        elif t.get("consumed") and t.get("consumed_by") == "dream-resolved":
            st, basis = "consolidated", "a dream resolved it (%s)" % t.get("last_dream_verdict", "resolved")
        elif t.get("dream_passes", 0) or t.get("mirror_passes", 0) or t.get("last_dream_verdict"):
            st, basis = "explored", "dream passes %s, mirror passes %s, last verdict %s" % (t.get("dream_passes", 0), t.get("mirror_passes", 0), t.get("last_dream_verdict"))
        else:
            st, basis = "selected", "in the pool, not yet taken up"
        yield {"id": t.get("id"), "question": t.get("thread", ""), "source": "thread:" + str(t.get("source", "")), "state": st, "basis": basis, "since": t.get("timestamp")}


def _from_unsaid():
    for i, x in enumerate(_load("unsaid-questions.json", []) or []):
        if not isinstance(x, dict) or not x.get("question"):
            continue
        st = "explored" if x.get("asked") else "selected"
        yield {"id": "UQ-" + str(x.get("id") or i), "question": x["question"], "source": "unsaid", "state": st,
               "basis": ("asked her" if x.get("asked") else "held %s turns" % x.get("turns", 0)), "since": x.get("at") or x.get("created")}


def _from_tensions():
    d = _load("tension-questions.json", [])
    rows = d.get("tensions", d) if isinstance(d, dict) else d
    for t in rows or []:
        if not isinstance(t, dict):
            continue
        s = str(t.get("status", "")).upper()
        st = {"HYPOTHESIS": "selected", "SUPPORTED": "explored", "CONFIRMED": "consolidated", "CONTESTED": "explored", "CONTRADICTED": "released_unresolved"}.get(s, "selected")
        yield {"id": t.get("tension_id") or t.get("id"), "question": t.get("question") or t.get("description", ""), "source": "tension", "state": st,
               "basis": "tension status %s, corrections %s" % (s, t.get("correction_count", 0)), "since": t.get("formed") or t.get("created")}


def view():
    rows = list(_from_bring_up()) + list(_from_threads()) + list(_from_unsaid()) + list(_from_tensions())
    asserted = _asserted()
    for r in rows:
        a = asserted.get(r["id"])
        if a:
            r["state"], r["basis"], r["asserted_at"] = a["state"], "asserted: " + a["basis"], a["at"]
    return rows


def advance(qid, state, basis):
    if state not in STATES:
        raise ValueError("state %r not in %s" % (state, STATES))
    if state in ("resolved", "released_unresolved") and len(str(basis or "").strip()) < 8:
        raise ValueError("a question cannot be %s without a basis" % state)
    row = {"id": qid, "state": state, "basis": str(basis)[:300], "at": time.strftime("%Y-%m-%dT%H:%M:%S")}
    os.makedirs(MEMORY, exist_ok=True)
    with open(ASSERTED, "a") as f:
        f.write(json.dumps(row) + "\n")
    return row


def changes(write=True, now=None):
    """Against the last view: which question changed state and why, what is open, what resolved."""
    prev = _load(os.path.basename(VIEW), {})
    before = {r["id"]: r for r in prev.get("questions", [])} if isinstance(prev, dict) else {}
    cur = view()
    changed = []
    for r in cur:
        b = before.get(r["id"])
        if b is None:
            changed.append({"id": r["id"], "question": r["question"][:120], "from": None, "to": r["state"], "why": r["basis"]})
        elif b.get("state") != r["state"]:
            changed.append({"id": r["id"], "question": r["question"][:120], "from": b.get("state"), "to": r["state"], "why": r["basis"]})
    gone = [{"id": k, "question": v.get("question", "")[:120], "from": v.get("state"), "to": None, "why": "no longer in any source"} for k, v in before.items() if k not in {r["id"] for r in cur}]
    out = {"at": now or time.strftime("%Y-%m-%dT%H:%M:%S"), "previous_at": prev.get("at") if isinstance(prev, dict) else None,
           "changed": changed + gone,
           "open": [{"id": r["id"], "question": r["question"][:120], "state": r["state"], "basis": r["basis"]} for r in cur if r["state"] in ("selected", "explored")],
           "resolved_since": [c for c in changed if c["to"] in ("resolved", "consolidated", "released_unresolved")],
           "questions": cur}
    if write:
        os.makedirs(MEMORY, exist_ok=True)
        tmp = VIEW + ".tmp"; json.dump(out, open(tmp, "w"), indent=1); os.replace(tmp, VIEW)
    return out


if __name__ == "__main__":
    c = changes(write="--write" in sys.argv)
    print("questions: %d open, %d changed since %s" % (len(c["open"]), len(c["changed"]), c["previous_at"] or "never"))
    for x in c["changed"]:
        print("  %s -> %s  %s  (%s)" % (x["from"], x["to"], x["question"][:70], x["why"][:60]))
