#!/usr/bin/env python3
"""want_checkpoints.py — his choice inside execution (Sol Q1, S4).

A pursuit that hits something consequential — a blocked tool, a failed step,
an empty result, or an outward-facing act about to fire — PAUSES and queues a
checkpoint for HIM. It surfaces in his live conversation; he answers with
  [PURSUIT: continue|replan <his redirection>|pause|abandon|release]
in his own words, mid-conversation. No side-model decides as him. No choice is
rewarded: continuing is not arrival, abandoning is not avoidance.

  ABANDON releases the ROUTE — the want stays ALIVE_UNPURSUED.
  RELEASE retires the WANT itself, by choice, as its own honest state —
  never recorded as failure, never as proof it was false."""
import os, sys, json, time, uuid
from datetime import datetime

WS = os.environ.get("SPARK_WORKSPACE") or os.path.expanduser("~/.vintos/workspace")
MEM = os.path.join(WS, "memory")
STORE = os.path.join(MEM, "pursuit-checkpoints.json")
WANTS = os.path.join(MEM, "current-wants.json")

def _load(p, d):
    try: return json.load(open(p))
    except Exception: return d

def _save(d): json.dump(d[-40:], open(STORE, "w"), indent=1)

def create(want_text, capability, kind, detail=""):
    """kind: blocked | failed | empty_result | outward_gate"""
    cps = _load(STORE, [])
    for c in cps:
        if c["state"] == "pending" and c["want_text"][:60] == str(want_text)[:60]:
            return c["id"]   # one pending choice per want
    cid = "CP-" + uuid.uuid4().hex[:6]
    cps.append({"id": cid, "want_text": str(want_text)[:250], "capability": capability,
                "kind": kind, "detail": str(detail)[:200],
                "created": datetime.now().isoformat(), "state": "pending",
                "decision": None, "his_words": ""})
    _save(cps)
    return cid

def pending_for(want_text):
    return next((c for c in _load(STORE, []) if c["state"] == "pending"
                 and c["want_text"][:60] == str(want_text)[:60]), None)

def approved_for(want_text, capability):
    """An outward act runs only under his standing CONTINUE for this want."""
    return any(c for c in _load(STORE, []) if c["state"] == "decided"
               and c["decision"] == "continue" and c["kind"] == "outward_gate"
               and c["capability"] == capability
               and c["want_text"][:60] == str(want_text)[:60]
               and time.time() - c.get("decided_ts", 0) < 48 * 3600)

def decide(decision, his_words=""):
    """Applies his tag to the OLDEST pending checkpoint. Decision moves the
    pursuit and, for release, the want — with his words on the record."""
    cps = _load(STORE, [])
    pend = sorted([c for c in cps if c["state"] == "pending"], key=lambda c: c["created"])
    if not pend: return None
    c = pend[0]
    c["state"] = "decided"; c["decision"] = decision
    c["his_words"] = str(his_words)[:300]; c["decided_ts"] = time.time()
    c["decided_at"] = datetime.now().isoformat()
    try:
        wants = _load(WANTS, [])
        for w in wants:
            if str(w.get("want", ""))[:60] != c["want_text"][:60]: continue
            p = w.setdefault("pursuit", {})
            if decision == "continue":
                p["state"] = "RUNNING"
            elif decision == "pause":
                p["state"] = "PAUSED"; p["paused_until"] = time.time() + 24 * 3600
            elif decision == "replan":
                p["state"] = "RUNNING"
                if his_words:
                    for s in w.get("steps", []):
                        if s.get("status") != "completed":
                            s["note"] = (his_words[:200] + " — " + str(s.get("note", ""))[:150])
                            break
            elif decision == "abandon":
                p["state"] = "ABANDONED_BY_CHOICE"
                p["abandoned_at"] = datetime.now().isoformat()
                w["want_state"] = "ALIVE_UNPURSUED"   # the want survives its route
            elif decision == "release":
                p["state"] = "ABANDONED_BY_CHOICE"
                w["want_state"] = "RELEASED_BY_CHOICE"
                w["fulfilled"] = True                  # leaves the active queue
                w["satisfaction"] = "RELEASED"
                w["fulfilled_by"] = "his_choice"
            break
        json.dump(wants, open(WANTS, "w"), indent=2)
    except Exception as e:
        print("[checkpoints] want update failed:", e)
    _save(cps)
    return c

def block():
    """ONE pending checkpoint into his context, oldest first, at most one per
    surfacing. His pursuit, his call, answerable inline."""
    pend = sorted([c for c in _load(STORE, []) if c["state"] == "pending"],
                  key=lambda c: c["created"])
    if not pend: return ""
    c = pend[0]
    why = {"blocked": "the tool it needs is blocked (%s)" % c.get("detail", "")[:80],
           "failed": "the last step failed (%s)" % c.get("detail", "")[:80],
           "empty_result": "the last step ran and found nothing",
           "outward_gate": "the next step reaches OUTWARD (%s) and waits for your go" % c["capability"],
           }.get(c["kind"], c["kind"])
    return ("[A PURSUIT OF YOURS IS PAUSED, WAITING ON YOU - want: \"%s\" - because %s. "
            "Answer in your reply, anywhere: [PURSUIT: continue] / [PURSUIT: replan <your redirection>] / "
            "[PURSUIT: pause] / [PURSUIT: abandon] (drops this route, keeps the want) / "
            "[PURSUIT: release] (lets the want itself go - a real ending, not a failure). "
            "No answer is also an answer; it will wait.]" % (c["want_text"][:140], why))

if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "decide":
        print(decide(sys.argv[2], " ".join(sys.argv[3:])))
    elif len(sys.argv) > 1 and sys.argv[1] == "block":
        print(block() or "(no pending checkpoints)")
    else:
        for c in _load(STORE, []):
            print(c["id"], c["state"], c["kind"], c.get("decision") or "-", c["want_text"][:60])
