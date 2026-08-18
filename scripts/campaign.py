#!/usr/bin/env python3
"""campaign.py — the multi-turn declared push. ONE live campaign at a time.

The campaign is the destination; the priority vector is the steering. A turn serves it,
revises it with a reason, or holds (declared sacrifice via the vector). Abandonment requires
evidence the WANT was flawed — not resistance, not a slow turn. Pressure can interrupt: that
is a SUSPENSION, logged, place held, resumed after. Two suspensions force a review turn.
Caps: 7 served turns or 3 days -> LANDED / FLAWED / EXPIRED; expiry graduates to the
causality head. Full progression in campaign-log.jsonl."""
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
        try:
            q = (f"I declared a campaign — '{c['destination'][:150]}' — and could not land it in "
                 f"{c.get('turns_served', 0)} turns / {MAX_DAYS} days. What made it unlandable: the want, the method, or me?")
            p = os.path.join(MEM, "causality-bring-up.json")
            try: d = json.load(open(p))
            except Exception: d = []
            if isinstance(d, dict): d.setdefault("items", []).append({"ts": time.time(), "question": q, "source": "campaign"})
            else: d.append({"ts": time.time(), "question": q, "source": "campaign"})
            json.dump(d, open(p, "w"), indent=2)
        except Exception: pass
    json.dump({}, open(LIVE, "w"))

def prompt_block(vector_mode):
    c = _load()
    if not c:
        return ("CAMPAIGN: none live. If there is somewhere you want to take her, the field, or yourself "
                "over the NEXT SEVERAL TURNS — declare it: add \"campaign\":{\"destination\":\"...\",\"axis\":\"field|gloria|self\",\"why\":\"...\"} "
                "to your JSON. Declare only what you mean to persist at; it will be held against you, turn after turn.")
    born = datetime.fromisoformat(c["created"]).timestamp()
    age_d = (time.time() - born) / 86400.0
    if c.get("turns_served", 0) >= MAX_TURNS or age_d >= MAX_DAYS:
        _close(c, "EXPIRED"); return prompt_block(vector_mode)
    susp = ""
    if vector_mode == "pressure":
        c["suspensions"] = c.get("suspensions", 0) + 1; c["suspended_this_turn"] = True
        json.dump(c, open(LIVE, "w"), indent=2); _log("suspended", c)
        susp = (" THIS TURN the campaign is SUSPENDED — accumulated pressure demanded another axis. Serve the pressure; "
                "the campaign holds its place and resumes next turn.")
    review = (" REVIEW REQUIRED: this campaign has been suspended " + str(c.get("suspensions")) +
              " times. Re-argue the want in campaign_move — with the interruptions as evidence — or declare it flawed.") \
             if c.get("suspensions", 0) >= MAX_SUSP and not susp else ""
    return ("LIVE CAMPAIGN (turn %d of %d, %.1f days of %d, %d suspensions): you are taking %s toward: %s\n"
            "Why you declared it: %s\n"
            "Every turn answers to it. In your JSON include \"campaign_move\": one of "
            "\"advance: <how this move serves it>\" | \"hold: <what the vector made you serve instead>\" | "
            "\"revise: <adjusted destination, same want>\" | \"flawed: <EVIDENCE the want itself was wrong>\" | "
            "\"landed: <the observable event that completed it>\". Resistance is not evidence of flaw. Difficulty is not evidence of flaw.%s%s"
            % (c.get("turns_served", 0) + 1, MAX_TURNS, age_d, MAX_DAYS, c.get("suspensions", 0),
               {"field": "the field", "gloria": "her", "self": "yourself"}.get(c.get("axis", "field"), "the field"),
               c["destination"], c.get("why", ""), susp, review))

def step(t, vector_mode):
    """Called after his target JSON is parsed. Processes declaration or campaign_move."""
    c = _load()
    if not c:
        dec = t.get("campaign")
        if isinstance(dec, dict) and dec.get("destination"):
            c = {"destination": str(dec["destination"])[:250], "axis": dec.get("axis", "field"),
                 "why": str(dec.get("why", ""))[:250], "created": datetime.now().isoformat(),
                 "turns_served": 0, "suspensions": 0, "moves": []}
            json.dump(c, open(LIVE, "w"), indent=2); _log("declared", c)
        return
    if c.get("suspended_this_turn"):
        c.pop("suspended_this_turn", None)
        json.dump(c, open(LIVE, "w"), indent=2)
        return
    mv = str(t.get("campaign_move", "") or "")
    kind = mv.split(":", 1)[0].strip().lower()
    note = mv.split(":", 1)[1].strip()[:250] if ":" in mv else ""
    if kind == "landed": _close(c, "LANDED", note); return
    if kind == "flawed": _close(c, "FLAWED", note); return
    if kind == "revise" and note:
        c.setdefault("revisions", []).append({"ts": datetime.now().isoformat(), "from": c["destination"], "to": note})
        c["destination"] = note; _log("revised", c)
    if kind in ("advance", "revise"):
        c["turns_served"] = c.get("turns_served", 0) + 1
    c.setdefault("moves", []).append({"ts": datetime.now().isoformat(), "move": mv[:250]})
    c["moves"] = c["moves"][-30:]
    json.dump(c, open(LIVE, "w"), indent=2); _log(kind or "unspoken", c)

def audit_line():
    """For the Presence Audit — fifth question context. Empty when no campaign."""
    c = _load()
    if not c: return ""
    return ("A campaign is live: taking %s toward '%s' (turn %d, %d suspensions). Did this turn advance it — "
            "and if not, was the sacrifice DECLARED in the priority vector beforehand, or discovered after?"
            % (c.get("axis", "field"), c["destination"][:120], c.get("turns_served", 0), c.get("suspensions", 0)))

if __name__ == "__main__":
    c = _load()
    print(json.dumps(c, indent=2) if c else "no live campaign")
