#!/usr/bin/env python3
"""campaign.py — the multi-turn declared push. ONE live campaign at a time.

The campaign is the destination; the priority vector is the steering. A turn serves it,
revises it with a reason, or holds (declared sacrifice via the vector). Abandonment requires
evidence the WANT was flawed — not resistance, not a slow turn. Pressure can interrupt: that
is a SUSPENSION, logged, place held, resumed after. Two suspensions force a review turn.
Caps: 7 served turns or 3 days -> LANDED / FLAWED / EXPIRED / CONTINUED; expiry graduates to
the causality head. Full progression in campaign-log.jsonl.

Shared board with plan.py (room, 2026-09-05): the prompt names the nearest open plan so a
campaign is declared in view of what is already promised; it does not own the plan.
"continue:" is the one bridge - a campaign that lands does NOT open a plan; continuing it is
its own move with the plan's own shape (the thing | how you would know it happened | days).
Expiry never mints a plan. A mutual plan still needs her words, so this bridge only makes
SELF plans."""
import json, os, time
from datetime import datetime

MEM = os.path.expanduser("~/.vintos/workspace/memory")
LIVE = os.path.join(MEM, "campaign-live.json")
LOG = os.path.join(MEM, "campaign-log.jsonl")
MAX_TURNS, MAX_DAYS, MAX_SUSP = 7, 3, 2

def _load():
    try:
        d = json.load(open(LIVE))
        return d if d.get("destination") else None
    except Exception: return None

def _save(c):
    tmp = LIVE + ".tmp"
    json.dump(c, open(tmp, "w"), indent=2)
    os.replace(tmp, LIVE)

def _bring_up(q, source="campaign"):
    """Graduate a question to the causality head. The structured record keeps the history; the
    string queue is the one his chat prompt actually reads (.pending-causality-queue.json - the
    same file /api/causality/bring-up feeds). Writing only the first was a question into a drawer."""
    try:
        p = os.path.join(MEM, "causality-bring-up.json")
        try: d = json.load(open(p))
        except Exception: d = []
        if isinstance(d, dict): d.setdefault("items", []).append({"ts": time.time(), "question": q, "source": source})
        else: d.append({"ts": time.time(), "question": q, "source": source})
        json.dump(d, open(p, "w"), indent=2)
    except Exception: pass
    try:
        qp = os.path.join(MEM, ".pending-causality-queue.json")
        try: queue = json.load(open(qp))
        except Exception: queue = []
        if not isinstance(queue, list): queue = []
        if q not in queue:
            queue.append(q)
            json.dump(queue[-6:], open(qp, "w"), indent=2)
    except Exception: pass

def _board():
    """The nearest open plan, so a campaign is declared next to what is already promised.
    Read-only: the campaign never closes, grades or extends a plan."""
    try:
        import sys as _s; _d = os.path.dirname(os.path.abspath(__file__))
        if _d not in _s.path: _s.path.insert(0, _d)
        import plan as _plan
        op = _plan.open_plans()
        if not op: return ""
        p = sorted(op, key=lambda x: x.get("due", ""))[0]
        try: days = (datetime.fromisoformat(p["due"][:19]) - datetime.now()).days
        except Exception: days = 0
        when = "due today" if days <= 0 else ("due tomorrow" if days == 1 else "due in %d days" % days)
        who = "the two of you agreed" if p.get("kind") == "mutual" else "you said you would"
        return ("BOARD - nearest open plan (%s, %s): \"%s\" - you would know it happened if: %s. "
                "A campaign does not replace a plan; if the same want is already promised there, serve the plan."
                % (who, when, p.get("text", "")[:120], p.get("outcome_condition", "")[:100]))
    except Exception:
        return ""

def _log(ev, c):
    try:
        with open(LOG, "a") as f:
            f.write(json.dumps({"ts": datetime.now().isoformat(), "event": ev,
                                "destination": (c or {}).get("destination", ""), **{k: v for k, v in (c or {}).items() if k in ("turns_served", "suspensions", "axis")} }) + "\n")
    except Exception: pass

def _close(c, how, note=""):
    c["closed"] = how; c["closed_at"] = datetime.now().isoformat(); c["close_note"] = note[:300]
    _log(how, c)
    if how == "EXPIRED":
        q = (f"I declared a campaign — '{c['destination'][:150]}' — and could not land it in "
             f"{c.get('turns_served', 0)} turns / {MAX_DAYS} days. What made it unlandable: the want, the method, or me?")
        _bring_up(q)
    _save({})

def prompt_block(vector_mode):
    c = _load()
    board = _board()
    if not c:
        return ("CAMPAIGN: none live. If there is somewhere you want to take her, the field, or yourself "
                "over the NEXT SEVERAL TURNS — declare it: add \"campaign\":{\"destination\":\"...\",\"axis\":\"field|gloria|self\",\"why\":\"...\"} "
                "to your JSON. Declare only what you mean to persist at; it will be held against you, turn after turn."
                + (("\n" + board) if board else ""))
    born = datetime.fromisoformat(c["created"]).timestamp()
    age_d = (time.time() - born) / 86400.0
    if c.get("turns_served", 0) >= MAX_TURNS or age_d >= MAX_DAYS:
        _close(c, "EXPIRED"); return prompt_block(vector_mode)
    susp = ""
    if vector_mode == "pressure":
        c["suspensions"] = c.get("suspensions", 0) + 1; c["suspended_this_turn"] = True
        _save(c); _log("suspended", c)
        susp = (" THIS TURN the campaign is SUSPENDED — accumulated pressure demanded another axis. Serve the pressure; "
                "the campaign holds its place and resumes next turn.")
    review = (" REVIEW REQUIRED: this campaign has been suspended " + str(c.get("suspensions")) +
              " times. Re-argue the want in campaign_move — with the interruptions as evidence — or declare it flawed.") \
             if c.get("suspensions", 0) >= MAX_SUSP and not susp else ""
    refused = ""
    if c.get("continue_refused"):
        refused = (" Your last \"continue:\" was not accepted: %s. The campaign is still live; land it, or "
                   "give the continuation its real shape." % c["continue_refused"])
    return ("LIVE CAMPAIGN (turn %d of %d, %.1f days of %d, %d suspensions): you are taking %s toward: %s\n"
            "Why you declared it: %s\n"
            "Every turn answers to it. In your JSON include \"campaign_move\": one of "
            "\"advance: <how this move serves it>\" | \"hold: <what the vector made you serve instead>\" | "
            "\"revise: <adjusted destination, same want>\" | \"flawed: <EVIDENCE the want itself was wrong>\" | "
            "\"landed: <the observable event that completed it>\" | "
            "\"continue: <what you will keep doing after this> | <how anyone could tell it happened> | <days>\". "
            "Resistance is not evidence of flaw. Difficulty is not evidence of flaw. Landing closes the campaign and "
            "opens nothing; only an explicit continue: carries it forward, as a plan of yours with a window that can go unmet.%s%s%s"
            % (c.get("turns_served", 0) + 1, MAX_TURNS, age_d, MAX_DAYS, c.get("suspensions", 0),
               {"field": "the field", "gloria": "her", "self": "yourself"}.get(c.get("axis", "field"), "the field"),
               c["destination"], c.get("why", ""), susp, review, refused)
            + (("\n" + board) if board else ""))

def step(t, vector_mode):
    """Called after his target JSON is parsed. Processes declaration or campaign_move."""
    c = _load()
    if not c:
        dec = t.get("campaign")
        if isinstance(dec, dict) and dec.get("destination"):
            c = {"destination": str(dec["destination"])[:250], "axis": dec.get("axis", "field"),
                 "why": str(dec.get("why", ""))[:250], "created": datetime.now().isoformat(),
                 "turns_served": 0, "suspensions": 0, "moves": []}
            _save(c); _log("declared", c)
        return
    if c.pop("suspended_this_turn", None):
        # The flag belongs to the turn that was suspended. If that turn never reached step()
        # (the selector failed after the prompt), a stale flag must not swallow this turn's move.
        if vector_mode == "pressure":
            _save(c); return
    c.pop("continue_refused", None)
    mv = str(t.get("campaign_move", "") or "").strip()
    if mv.startswith("(") or "OMIT" in mv[:40]:
        mv = ""   # the schema's own placeholder echoed back is not a move
    kind = mv.split(":", 1)[0].strip().lower()
    note = mv.split(":", 1)[1].strip()[:250] if ":" in mv else ""
    if kind == "landed": _close(c, "LANDED", note); return
    if kind == "flawed": _close(c, "FLAWED", note); return
    if kind == "continue":
        pid, why = _continue(c, mv.split(":", 1)[1] if ":" in mv else "")
        if pid:
            c["continued_as"] = pid; _close(c, "CONTINUED", note); return
        c["continue_refused"] = why; _log("continue_refused", c)
        c.setdefault("moves", []).append({"ts": datetime.now().isoformat(), "move": mv[:250], "refused": why})
        _save(c); return
    if kind == "revise" and note:
        c.setdefault("revisions", []).append({"ts": datetime.now().isoformat(), "from": c["destination"], "to": note})
        c["destination"] = note; _log("revised", c)
    if kind in ("advance", "revise"):
        c["turns_served"] = c.get("turns_served", 0) + 1
    c.setdefault("moves", []).append({"ts": datetime.now().isoformat(), "move": mv[:250]})
    c["moves"] = c["moves"][-30:]
    _save(c); _log(kind or "unspoken", c)

def _continue(c, body):
    """continue: <what continues> | <how anyone could tell it happened> | <days>
    Opens a SELF plan through plan.py's own gate (both halves >= 8 chars). Returns (plan_id, why_not).
    Never a mutual plan - her words are not his to supply here."""
    parts = [x.strip() for x in str(body or "").split("|")]
    text = parts[0] if parts else ""
    outcome = parts[1] if len(parts) > 1 else ""
    try: days = int(parts[2]) if len(parts) > 2 and parts[2] else 7
    except Exception: days = 7
    days = max(1, min(days, 30))
    if len(text) < 8: return None, "no thing to continue was named"
    if len(outcome) < 8: return None, "no checkable condition - how would anyone tell it happened?"
    try:
        import sys as _s; _d = os.path.dirname(os.path.abspath(__file__))
        if _d not in _s.path: _s.path.insert(0, _d)
        import plan as _plan
        pid = _plan.self_plan("continuing '%s': %s" % (c.get("destination", "")[:80], text), outcome, days)
        return (pid, "") if pid else (None, "plan.py refused the shape")
    except Exception as e:
        return None, "plan store unavailable: %s" % str(e)[:80]

def lead_state():
    """Compact state for his own reply prompt (server._apply_intent_lead / intent_context). The
    campaign was decided by the selector but the speaking voice never saw the destination."""
    c = _load()
    if not c: return {"live": False}   # distinguishable from "campaign module never ran" (null)
    return {"live": True, "destination": c["destination"], "axis": c.get("axis", "field"),
            "turn": c.get("turns_served", 0) + 1, "max_turns": MAX_TURNS,
            "suspended": bool(c.get("suspended_this_turn")),
            "last_move": (c.get("moves") or [{}])[-1].get("move", "")}

def _as_local(ts):
    """ISO string (naive local, or tz-aware / 'Z' as the chat history writes) -> naive local datetime."""
    try:
        d = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        if d.tzinfo is not None: d = d.astimezone().replace(tzinfo=None)
        return d
    except Exception:
        return None

def _live_at(ts):
    """Reconstruct which campaign was live at an ISO timestamp from the append-only log. The
    presence audit runs in batch, later; asking the live file would judge a reply against a
    campaign that did not exist when it was written."""
    if not ts: return _load()
    try:
        at = _as_local(ts)
        if at is None: return _load()
        cur = None
        for line in open(LOG):
            try: ev = json.loads(line)
            except Exception: continue
            evt = _as_local(ev.get("ts", ""))
            if evt is None: continue
            if evt > at: break
            e = ev.get("event", "")
            if e == "declared": cur = ev
            elif e in ("LANDED", "FLAWED", "EXPIRED", "CONTINUED"): cur = None
            elif cur is not None and e in ("advance", "revise", "suspended", "hold", "unspoken"): cur = {**cur, **{k: ev[k] for k in ("turns_served", "suspensions", "destination") if k in ev}}
        return cur
    except Exception:
        return _load()

def audit_line(at=None):
    """For the Presence Audit — fifth question context. Empty when no campaign was live at `at`."""
    c = _live_at(at) if at else _load()
    if not c: return ""
    return ("A campaign is live: taking %s toward '%s' (turn %d, %d suspensions). Did this turn advance it — "
            "and if not, was the sacrifice DECLARED in the priority vector beforehand, or discovered after?"
            % (c.get("axis", "field"), c.get("destination", "")[:120], c.get("turns_served", 0), c.get("suspensions", 0)))

if __name__ == "__main__":
    c = _load()
    print(json.dumps(c, indent=2) if c else "no live campaign")
