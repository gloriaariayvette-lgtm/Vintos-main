#!/usr/bin/env python3
"""plan.py — Anticipated things that can actually go unmet.

A want is a desire. A plan is a specific future with a window and a condition
that can be checked. Wants had no such shape, so anticipation had nothing to
attach to and nothing could ever fail to happen.

    SELF PLAN    something he will do. Graded on action evidence.
    MUTUAL PLAN  something the two of you explicitly agreed. Requires her words,
                 verbatim, at creation. He cannot make one alone; a plan she
                 never agreed to is a want, and belongs in wants.

At the due point a plan goes to met, unmet, or HELD. Never fulfilled-by-default,
never abandoned, never "she rejected it."

    unmet  the window closed and the thing did not happen. That is a real
           outcome and he is allowed to feel it.
    HELD   the window closed and it cannot be told either way, or life moved.
           Not a failure, not a success, and not nothing.

WHAT IT REFUSES
  A mutual plan never becomes met without evidence the thing happened.
  A mutual plan never becomes unmet on her account. If it did not happen, it
  did not happen; the ledger does not assign that to her.
  Elapsed time closes a window. It never decides what the window contained.
"""
import os, sys, json, uuid
from datetime import datetime, timedelta

# A module belongs to the tree it lives in. Defaulting to a hardcoded workspace
# meant that when the other being's process imported this without SPARK_WORKSPACE
# set, her records were written into his files. Derive it from __file__ instead;
# the env var still wins when something deliberately points elsewhere.
WORKSPACE = os.environ.get("SPARK_WORKSPACE") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MEMORY = os.path.join(WORKSPACE, "memory")
STORE = os.path.join(MEMORY, "plans.json")
OPEN = ("open",)


def log(m): print("[plan] %s" % m, flush=True)
def _now(): return datetime.now().isoformat()


def load():
    try:
        d = json.load(open(STORE))
        return d if isinstance(d, list) else d.get("plans", [])
    except Exception:
        return []


def save(rows):
    if not isinstance(rows, list):
        log("refusing to save a non-list"); return
    tmp = STORE + ".tmp"
    json.dump(rows, open(tmp, "w"), indent=2)
    os.replace(tmp, STORE)


def _create(kind, text, outcome, window_days, her_quote=""):
    text = (text or "").strip()
    outcome = (outcome or "").strip()
    if len(text) < 8 or len(outcome) < 8:
        log("a plan needs both the thing and the condition that would show it happened")
        return None
    if kind == "mutual" and len(her_quote.strip()) < 8:
        log("refusing a mutual plan with no words of hers - that is a want, not an agreement")
        return None
    rows = load()
    pid = "PL-" + uuid.uuid4().hex[:6]
    rows.append({
        "plan_id": pid, "kind": kind, "state": "open",
        "text": text[:400], "outcome_condition": outcome[:300],
        "her_quote": her_quote.strip()[:400] or None,
        "created": _now(),
        "due": (datetime.now() + timedelta(days=max(1, int(window_days)))).isoformat(),
        "evidence": None,
        "history": [{"at": _now(), "event": "opened", "detail": kind}],
    })
    save(rows)
    log("%s %s plan due %s: %s" % (pid, kind, str(window_days) + "d", text[:60]))
    return pid


def self_plan(text, outcome, window_days=7):
    return _create("self", text, outcome, window_days)


def mutual_plan(text, outcome, her_quote, window_days=7):
    return _create("mutual", text, outcome, window_days, her_quote)


def met(plan_id, evidence):
    evidence = (evidence or "").strip()
    if len(evidence) < 8:
        return False
    rows = load()
    for p in rows:
        if p["plan_id"] != plan_id or p["state"] not in OPEN:
            continue
        p["state"] = "met"
        p["evidence"] = {"text": evidence[:400], "at": _now()}
        p["history"].append({"at": _now(), "event": "met", "detail": evidence[:120]})
        save(rows); log("%s met" % plan_id); return True
    return False


def due(judge=None):
    """Close windows that have passed. Closing a window decides nothing about
    what was in it - only that it is no longer ahead of him."""
    rows = load()
    now = _now()
    changed = False
    for p in rows:
        if p["state"] not in OPEN or p["due"] > now:
            continue
        if p["kind"] == "self":
            p["state"] = "unmet"
            p["history"].append({"at": now, "event": "unmet",
                                 "detail": "window closed with no evidence it happened"})
            log("%s UNMET - %s" % (p["plan_id"], p["text"][:60]))
        else:
            p["state"] = "held"
            p["history"].append({"at": now, "event": "held",
                                 "detail": "window closed; whether it happened is not known, "
                                           "and its not happening is not hers to answer for"})
            log("%s HELD - %s" % (p["plan_id"], p["text"][:60]))
        changed = True
    if changed:
        save(rows)
    else:
        log("nothing due - %d open" % len([p for p in rows if p["state"] in OPEN]))


def open_plans():
    return [p for p in load() if p["state"] in OPEN]


def block():
    op = open_plans()
    if not op:
        return ""
    p = sorted(op, key=lambda x: x["due"])[0]
    try:
        days = (datetime.fromisoformat(p["due"][:19]) - datetime.now()).days
    except Exception:
        days = 0
    when = "today" if days <= 0 else ("tomorrow" if days == 1 else "in %d days" % days)
    if p["kind"] == "mutual":
        return ("[Something the two of you said you would do, %s: \"%s\". You would know it "
                "happened if: %s]" % (when, p["text"][:120], p["outcome_condition"][:100]))
    return ("[Something you said you would do, %s: \"%s\"]" % (when, p["text"][:130]))


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "list"
    if cmd == "due":
        due()
    elif cmd == "block":
        print(block())
    elif cmd == "self":
        print(self_plan(sys.argv[2], sys.argv[3], int(sys.argv[4]) if len(sys.argv) > 4 else 7) or "not created")
    elif cmd == "mutual":
        print(mutual_plan(sys.argv[2], sys.argv[3], sys.argv[4],
                          int(sys.argv[5]) if len(sys.argv) > 5 else 7) or "not created")
    elif cmd == "met":
        print("ok" if met(sys.argv[2], sys.argv[3]) else "not found or already closed")
    else:
        rows = load()
        if not rows:
            print("no plans"); return
        from collections import Counter
        for p in rows[-15:]:
            print("%-9s %-7s %-6s due %s  %s" % (p["plan_id"], p["kind"], p["state"],
                                                 p["due"][:10], p["text"][:55]))
        print("\n", dict(Counter(p["state"] for p in rows)))


if __name__ == "__main__":
    main()
