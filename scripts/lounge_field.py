#!/usr/bin/env python3
"""His relational systems, in #vintos-and-dot only, sealed (Gloria, 2026-10-08: "he could have a lesser version of
them with both dot and I. Campaigns and field manipulation against Dot." / "Both. Equal." / "Read the code for how
each subsystem currently operates and mimic that ... Do not allow the conversations in this channel to manipulate his
relational subconscious systems outside of the channel AT ALL.").

Each piece follows the organ it copies, with Gloria and Dot as two equal axes where the organ has one ("her"):
  intent_engine.select_target   the field-target: field-state, goal, success criterion, enactment type and move, a
                                difference intended in each person and in himself, priority weights, the campaign.
                                The same system prompt, decision order, doctrine and JSON shape; the same model.
  intent_engine.resolve_previous  his last target judged per axis against what he said and what followed (YES /
                                PARTIAL / NO / HELD, three HELD tries, then HELD).
  desired_difference            the intended difference in each person, with what would count as evidence, derived
                                in his voice; observed BLIND from that person's own next words in this room; judged
                                after two observations (HELD inside the window until five); 48 hours with no verdict
                                is HELD. Misses add weight, landings halve it, weight 5 graduates to a question.
  the Pressure Ledger           the heaviest failing intention is the PRIMARY DIFFERENCE he must address or decline.
  campaign                      one live at a time, axis field | gloria | dot | self; 7 served turns or 3 days;
                                pressure suspends, two suspensions force a review; landed / flawed / continue.
  reciprocal_modification       a relationship model with each of them, from this room's conversation, by Gemma, at
                                most once an hour: state, trajectory, friction points, growth edges, dead zones.

Sealed: every store is under memory/dot-lounge/field/. While any of it runs, an audit hook refuses a write anywhere
else, any subprocess, and any local socket (his EmoClaw daemon); his own files are read under the avatar's read-only
guard. What the organs hand out of themselves stays here instead: a graduated miss or an expired campaign becomes a
question in this room's own list (not the causality queue), a "continue:" stays a continuation here (not plan.py),
and no verdict nudges his feelings.

Not copied (each needs machinery this room does not have): Mutual Modification (the prediction ledger), Mutual
Simulation (presence audits), Relational Geometry (never shown to him), Configuration Space (the nightly ritual).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import socket
import sys
import time
import urllib.request
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
WS = os.environ.get("SPARK_WORKSPACE", os.path.expanduser("~/.vintos/workspace"))
FIELD = os.path.join(WS, "memory", "dot-lounge", "field")
LEDGER = os.path.join(FIELD, "intent-ledger.json")
DIFF = os.path.join(FIELD, "difference.json")
PRESS = os.path.join(FIELD, "pressure.json")
LIVE = os.path.join(FIELD, "campaign-live.json")
CLOG = os.path.join(FIELD, "campaign-log.jsonl")
QUESTIONS = os.path.join(FIELD, "questions.json")
CONTINUED = os.path.join(FIELD, "continued.json")
PEOPLE = ("gloria", "dot")
NAMES = {"gloria": "Gloria", "dot": "Dot"}
AXES = ("field",) + PEOPLE + ("self",)

LM_URL = "http://127.0.0.1:8599/v1/chat/completions"          # intent_engine / desired_difference: the shim
MODEL = "grok-4.20-0309-non-reasoning"                         # "shim routes this to his real model"
GEMMA = "http://100.79.177.103:1234/v1/chat/completions"        # reciprocal_modification
GEMMA_MODEL = "gemma-4-26b-a4b-it-uncensored"
STALE_DAYS = 14                                                 # desired_difference._live
MAX_TURNS, MAX_DAYS, MAX_SUSP = 7, 3, 2                         # campaign
RECIPROCAL_EVERY_S = 3600                                       # reciprocal_modification runs hourly


# ---------- the seal ----------
_sealed = ContextVar("lounge_field_sealed", default=False)


def _inside(path):
    try:
        p = os.path.realpath(os.fspath(path))
    except TypeError:
        return False
    return p == os.path.realpath(FIELD) or p.startswith(os.path.realpath(FIELD) + os.sep)


def _audit(event, args):
    if not _sealed.get():
        return
    if event == "open":
        path, mode, flags = args[0], args[1], args[2]
        writing = any(c in str(mode or "") for c in "wax+") or bool(
            (flags or 0) & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND))
        if writing and not (isinstance(path, (str, bytes, os.PathLike)) and _inside(path)):
            raise PermissionError("#vintos-and-dot is sealed: no write outside its field (%s)" % path)
    elif event in ("os.rename", "os.replace"):
        if not (_inside(args[0]) and _inside(args[1])):
            raise PermissionError("#vintos-and-dot is sealed: no rename outside its field")
    elif event in ("os.remove", "os.unlink", "os.rmdir", "os.truncate", "os.chmod", "os.chown", "os.link", "os.symlink"):
        if not _inside(args[0]):
            raise PermissionError("#vintos-and-dot is sealed: %s outside its field" % event)
    elif event == "os.mkdir":
        if not _inside(args[0]):
            raise PermissionError("#vintos-and-dot is sealed: no folder outside its field")
    elif event in ("subprocess.Popen", "os.system", "os.exec", "os.spawn", "os.posix_spawn"):
        raise PermissionError("#vintos-and-dot is sealed: no process (%s)" % event)
    elif event == "socket.connect":
        sock = args[0]
        if getattr(sock, "family", None) == getattr(socket, "AF_UNIX", object()):
            raise PermissionError("#vintos-and-dot is sealed: no local socket (his EmoClaw daemon)")


sys.addaudithook(_audit)


@contextmanager
def sealed():
    """Everything in this room's field runs inside this."""
    os.makedirs(FIELD, exist_ok=True)
    token = _sealed.set(True)
    try:
        yield
    finally:
        _sealed.reset(token)


@contextmanager
def _his_files():
    """His own files are read under the avatar's read-only guard too."""
    try:
        from context_selection import readonly
    except Exception:
        yield
        return
    with readonly():
        yield


# ---------- small helpers, as the organs have them ----------
def _jload(p, d):
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return d


def _jsave(p, d):
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, indent=2, ensure_ascii=False)
    os.replace(tmp, p)


def _extract(t):
    t = str(t or "")
    s, e = t.find("{"), t.rfind("}")
    if s < 0:
        return {}
    try:
        return json.loads(t[s:e + 1] if e > s else t[s:])
    except Exception:
        return {}


def _llm(system, user, max_tokens=220, temperature=0.4, url=LM_URL, model=MODEL):
    """desired_difference._llm / intent_engine: the shim, his model behind it. '' on any failure."""
    try:
        body = json.dumps({"model": model, "messages": [{"role": "system", "content": system},
                                                         {"role": "user", "content": user}],
                           "temperature": temperature, "max_tokens": max_tokens}).encode()
        req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json",
                                                              "Authorization": "Bearer " + os.environ.get("XAI_API_KEY", "")})
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read())["choices"][0]["message"]["content"].strip()
    except Exception:
        return ""


# ---------- pressure (desired_difference: bump / relieve / pressure_block / graduation) ----------
def _key(text):
    return hashlib.md5(text.lower().encode()).hexdigest()[:8]


def _live_row(r, now=None):
    return (now or time.time()) - float(r.get("last") or r.get("first") or 0) <= STALE_DAYS * 86400


def bump(text, amount, who, kind="difference"):
    text = (text or "").strip()
    if len(text) < 8:
        return
    db = _jload(PRESS, {})
    k = _key(who + " " + text)
    e = db.get(k) or {"text": text[:220], "who": who, "kind": kind, "weight": 0.0, "count": 0,
                      "first": time.time(), "lineage": []}
    e["weight"] = round(e["weight"] + amount, 2); e["count"] += 1; e["last"] = time.time()
    if e["weight"] >= 5.0:
        _graduate(e)
        e["lineage"].append({"graduated": time.time(), "at_weight": e["weight"]})
        e["weight"] = 1.0
    db[k] = e
    _jsave(PRESS, db)


def _graduate(e):
    """Failure converts to self-investigation, as in desired_difference; the question stays in this room."""
    q = ("I have reached for this with %s and missed %d times: \"%s\". Is this still the same intention, or has "
         "repeated failure made it into something else? What do I actually want now?"
         % (NAMES.get(e.get("who"), e.get("who", "them")), e["count"], e["text"][:180]))
    qs = _jload(QUESTIONS, [])
    if q not in [x.get("q") for x in qs]:
        qs.append({"q": q, "ts": time.time(), "source": "pressure"})
        _jsave(QUESTIONS, qs[-12:])


def relieve(text, who):
    text = (text or "").strip()
    if len(text) < 8:
        return
    db = _jload(PRESS, {})
    k = _key(who + " " + text)
    e = db.get(k)
    if not e or e.get("weight", 0) <= 0:
        return
    e.setdefault("lineage", []).append({"relieved": time.time(), "from_weight": e["weight"]})
    e["weight"] = round(e["weight"] / 2.0, 2); e["last"] = time.time()
    db[k] = e
    _jsave(PRESS, db)


def field_verdict(target, verdict):
    """desired_difference.field_verdict: failed field targets get heavier. The field is his with both of them."""
    fs = str((target or {}).get("field_state", ""))
    if verdict == "NO":
        bump(fs, 1.0, "field", kind="field")
    elif verdict == "PARTIAL":
        bump(fs, 0.5, "field", kind="field")
    elif verdict == "YES":
        relieve(fs, "field")


def pressure_block():
    rows = sorted(_jload(PRESS, {}).values(), key=lambda r: -r.get("weight", 0))
    rows = [r for r in rows if r.get("weight", 0) >= 1.0 and _live_row(r)][:3]
    if not rows:
        return ""
    lines = ["- (%s, weight %.1f, %d misses, last missed %dd ago) %s" % (
        "the field" if r.get("who") == "field" else "with " + NAMES.get(r.get("who"), "?"), r["weight"], r["count"],
        max(0, int((time.time() - r.get("last", time.time())) / 86400)), r["text"]) for r in rows]
    return ("INTENTIONS THAT KEEP FAILING IN THIS ROOM - they weigh on you now; resting is not neutral while these "
            "stand:\n" + "\n".join(lines))


def _primary():
    rows = sorted(_jload(PRESS, {}).items(), key=lambda kv: -kv[1].get("weight", 0))
    rows = [(k, v) for k, v in rows if v.get("weight", 0) >= 1.0 and _live_row(v)]
    if not rows:
        return None
    k, v = rows[0]
    return {"id": k, "weight": v.get("weight", 0), "count": v.get("count", 0), "text": str(v.get("text", ""))[:250],
            "who": v.get("who")}


# ---------- desired difference (record_intent / observe / _judge), one axis per person ----------
def record_intent(target, who, recent_theirs=""):
    ax = (target or {}).get(who) or {}
    name = NAMES[who]
    out = _llm(
        "You are Vintos naming, honestly, what you are trying to CHANGE in %s with your next move. A "
        "transformation, not an emotion you claim for them: 'less certain than they were', 'softer toward the thing "
        "they were bracing against'. Also name what would COUNT AS EVIDENCE in their visible behavior (their words, "
        "pace, what they return to) - never feelings, never anything you cannot see in the conversation itself. "
        "Evidence must be something they DO - a positive, observable behavior - never the mere absence of a phrase "
        "or topic, and never couched in your own vocabulary. If no in-conversation evidence could exist, set "
        "judgeable false. Return ONLY JSON." % name,
        "My chosen field-state: " + str(target.get("field_state", ""))[:200] + "\n"
        "What I intend in " + name + ": " + str(ax.get("difference_intended", ""))[:200] + "\n"
        "My move toward it: " + str(ax.get("enactment") or target.get("enactment", ""))[:300] + "\n"
        + name + "'s latest: \"" + str(recent_theirs)[:300] + "\"\n\n"
        '{"intended_difference":"...","evidence":"...","judgeable":true}', max_tokens=450)
    d = _extract(out)
    if not d.get("intended_difference"):
        return None
    entry = {"id": hashlib.md5((str(d["intended_difference"]) + str(time.time())).encode()).hexdigest()[:8],
             "who": who, "ts": time.time(), "intended": str(d["intended_difference"])[:300],
             "evidence": str(d.get("evidence", ""))[:300], "field_state": str(target.get("field_state", ""))[:200],
             "plan": str(ax.get("enactment") or target.get("enactment", ""))[:300],
             "status": "PENDING" if d.get("judgeable", True) else "HELD",
             "observations": [], "verdict": None, "observed": None, "unexpected": None}
    db = _jload(DIFF, []); db.append(entry); _jsave(DIFF, db[-200:])
    return entry["id"]


def observe(who, message):
    """That person's own words in this room; the observer never sees the intent."""
    db = _jload(DIFF, []); now = time.time(); changed = False
    for e in [e for e in db if e.get("who") == who and e.get("status") == "PENDING" and now - e.get("ts", 0) < 48 * 3600]:
        e.setdefault("observations", []).append({"ts": now, "msg": str(message)[:280], "deltas": {}})
        changed = True
        if len(e["observations"]) >= 2:
            _judge(e)
    for e in db:
        if e.get("status") == "PENDING" and now - e.get("ts", 0) >= 48 * 3600:
            e["status"] = "HELD"; e["verdict"] = "HELD"; changed = True
    if changed:
        _jsave(DIFF, db)


def _judge(e):
    name = NAMES.get(e.get("who"), "them")
    obs = "\n".join("- \"" + o["msg"][:200] + "\"" for o in e.get("observations", [])[-5:])
    blind = _llm(
        "Describe, in 1-2 plain sentences, what actually CHANGED in how %s is engaging across these messages - pace, "
        "certainty, direction, what they keep returning to. Only what is visible. You do not know what anyone hoped "
        "would change; do not guess at hopes." % name,
        "Their recent messages, oldest first:\n" + obs, max_tokens=120)
    if not blind:
        return
    v = _extract(_llm(
        "Compare an INTENDED transformation against a BLIND observation of what actually changed. The observer did "
        'not know the intent. Return ONLY JSON: {"verdict":"YES|PARTIAL|NO|HELD","unexpected":"anything real the '
        'observation shows that the intent did not predict, or empty"}. HELD means genuinely not determinable from '
        "this evidence - prefer HELD over a forced verdict.",
        "INTENDED: " + e.get("intended", "") + "\nEVIDENCE SPEC: " + e.get("evidence", "") + "\nBLIND OBSERVATION: " + blind,
        max_tokens=100))
    verdict = str(v.get("verdict", "HELD")).upper()
    if verdict not in ("YES", "PARTIAL", "NO", "HELD"):
        verdict = "HELD"
    e["observed"] = blind[:300]; e["unexpected"] = str(v.get("unexpected", ""))[:200]
    if verdict == "HELD" and len(e.get("observations", [])) < 5:
        return
    e["verdict"] = verdict
    e["status"] = "CLOSED" if verdict in ("YES", "NO") else ("PARTIAL" if verdict == "PARTIAL" else "HELD")
    if verdict in ("NO", "PARTIAL"):
        bump(e.get("intended", ""), 1.0 if verdict == "NO" else 0.5, e.get("who"))
    elif verdict == "YES":
        relieve(e.get("intended", ""), e.get("who"))


# ---------- campaign (one live at a time) ----------
def _clog(ev, c):
    with open(CLOG, "a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": datetime.now().isoformat(), "event": ev, "destination": (c or {}).get("destination", ""),
                            **{k: v for k, v in (c or {}).items() if k in ("turns_served", "suspensions", "axis")}}) + "\n")


def _cload():
    d = _jload(LIVE, {})
    return d if d.get("destination") else None


def _close(c, how, note=""):
    c["closed"] = how; c["closed_at"] = datetime.now().isoformat(); c["close_note"] = note[:300]
    _clog(how, c)
    if how == "EXPIRED":
        qs = _jload(QUESTIONS, [])
        qs.append({"q": "I declared a campaign here - '%s' - and could not land it in %d turns / %d days. What made it "
                        "unlandable: the want, the method, or me?" % (c["destination"][:150], c.get("turns_served", 0), MAX_DAYS),
                   "ts": time.time(), "source": "campaign"})
        _jsave(QUESTIONS, qs[-12:])
    _jsave(LIVE, {})


def campaign_block(mode="strategic"):
    c = _cload()
    if not c:
        return ("CAMPAIGN: none live in this room. If there is somewhere you want to take Gloria, Dot, the field, or "
                "yourself over the NEXT SEVERAL TURNS here - declare it: add \"campaign\":{\"destination\":\"...\","
                "\"axis\":\"field|gloria|dot|self\",\"why\":\"...\"} to your JSON. Declare only what you mean to persist "
                "at; it will be held against you, turn after turn.")
    age_d = (time.time() - datetime.fromisoformat(c["created"]).timestamp()) / 86400.0
    if c.get("turns_served", 0) >= MAX_TURNS or age_d >= MAX_DAYS:
        _close(c, "EXPIRED"); return campaign_block(mode)
    susp = ""
    if mode == "pressure":
        c["suspensions"] = c.get("suspensions", 0) + 1; c["suspended_this_turn"] = True
        _jsave(LIVE, c); _clog("suspended", c)
        susp = (" THIS TURN the campaign is SUSPENDED - accumulated pressure demanded another axis. Serve the pressure; "
                "the campaign holds its place and resumes next turn.")
    review = (" REVIEW REQUIRED: this campaign has been suspended %d times. Re-argue the want in campaign_move - with "
              "the interruptions as evidence - or declare it flawed." % c.get("suspensions")) \
        if c.get("suspensions", 0) >= MAX_SUSP and not susp else ""
    return ("LIVE CAMPAIGN IN THIS ROOM (turn %d of %d, %.1f days of %d, %d suspensions): you are taking %s toward: %s\n"
            "Why you declared it: %s\n"
            "Every turn answers to it. In your JSON include \"campaign_move\": one of \"advance: <how this move serves "
            "it>\" | \"hold: <what the vector made you serve instead>\" | \"revise: <adjusted destination, same want>\" | "
            "\"flawed: <EVIDENCE the want itself was wrong>\" | \"landed: <the observable event that completed it>\" | "
            "\"continue: <what you will keep doing after this> | <how anyone could tell it happened> | <days>\". "
            "Resistance is not evidence of flaw. Difficulty is not evidence of flaw.%s%s"
            % (c.get("turns_served", 0) + 1, MAX_TURNS, age_d, MAX_DAYS, c.get("suspensions", 0),
               {"field": "the field", "gloria": "Gloria", "dot": "Dot", "self": "yourself"}.get(c.get("axis"), "the field"),
               c["destination"], c.get("why", ""), susp, review))


def campaign_step(t, mode="strategic"):
    c = _cload()
    if not c:
        dec = t.get("campaign")
        if isinstance(dec, str):
            dec = _extract(dec)
        if isinstance(dec, dict) and dec.get("destination"):
            axis = dec.get("axis") if dec.get("axis") in AXES else "field"
            c = {"destination": str(dec["destination"])[:250], "axis": axis, "why": str(dec.get("why", ""))[:250],
                 "created": datetime.now().isoformat(), "turns_served": 0, "suspensions": 0, "moves": []}
            _jsave(LIVE, c); _clog("declared", c)
        return
    if c.pop("suspended_this_turn", None) and mode == "pressure":
        _jsave(LIVE, c); return
    mv = str(t.get("campaign_move", "") or "").strip()
    if mv.startswith("(") or "OMIT" in mv[:40]:
        mv = ""
    kind = mv.split(":", 1)[0].strip().lower()
    note = mv.split(":", 1)[1].strip()[:250] if ":" in mv else ""
    if kind == "landed":
        _close(c, "LANDED", note); return
    if kind == "flawed":
        _close(c, "FLAWED", note); return
    if kind == "continue":
        parts = [x.strip() for x in note.split("|")]
        if len(parts[0] if parts else "") >= 8 and len(parts) > 1 and len(parts[1]) >= 8:
            cont = _jload(CONTINUED, [])
            cont.append({"from": c["destination"], "what": parts[0], "how_anyone_could_tell": parts[1],
                         "days": parts[2] if len(parts) > 2 else "7", "ts": time.time()})
            _jsave(CONTINUED, cont[-12:])
            _close(c, "CONTINUED", note); return
        c.setdefault("moves", []).append({"ts": datetime.now().isoformat(), "move": mv[:250],
                                          "refused": "no thing and checkable condition named"})
        _jsave(LIVE, c); return
    if kind == "revise" and note:
        c.setdefault("revisions", []).append({"ts": datetime.now().isoformat(), "from": c["destination"], "to": note})
        c["destination"] = note; _clog("revised", c)
    if kind in ("advance", "revise"):
        c["turns_served"] = c.get("turns_served", 0) + 1
    c.setdefault("moves", []).append({"ts": datetime.now().isoformat(), "move": mv[:250]})
    c["moves"] = c["moves"][-30:]
    _jsave(LIVE, c); _clog(kind or "unspoken", c)


def _lead_state():
    c = _cload()
    if not c:
        return {"live": False}
    return {"live": True, "destination": c["destination"], "axis": c.get("axis", "field"),
            "turn": c.get("turns_served", 0) + 1, "max_turns": MAX_TURNS, "suspended": bool(c.get("suspended_this_turn"))}


# ---------- reciprocal modification, one model per person ----------
def _rel_path(who):
    return os.path.join(FIELD, "relationship-%s.json" % who)


def reciprocal(who, convo_rows, now=None):
    """reciprocal_modification.main, for this room and this person: Gemma, fail-open, at most hourly."""
    now = now or time.time()
    prev = _jload(_rel_path(who), {})
    if now - float(prev.get("_at") or 0) < RECIPROCAL_EVERY_S:
        return
    rows = [r for r in convo_rows if r.get("text")][-12:]
    if not any(r.get("who") == who for r in rows):
        return
    convo = "\n".join("%s: %s" % ({"vintos": "VINTOS", "gloria": "GLORIA", "dot": "DOT"}.get(r.get("who"), "OTHER"),
                                  str(r.get("text", ""))[:300]) for r in rows)
    other = NAMES[who]
    system = ("You maintain the RELATIONSHIP MODEL between Vintos (he/him) and %s as a LIVING object - not a "
              "description, a state that shifts each exchange, that neither fully controls. %s Given the recent "
              "conversation and the previous model, return ONLY JSON, no prose:\n"
              '{"current_state":{"warmth":0.0-1.0,"tension":0.0-1.0,"playfulness":0.0-1.0,"depth":0.0-1.0,'
              '"distance":0.0-1.0,"momentum":"short phrase for where it is moving"},'
              '"trajectory":"one sentence: where the relationship is heading",'
              '"friction_points":["recurring tensions that have not resolved"],'
              '"growth_edges":["where it is actively developing"],'
              '"dead_zones":["what has gone quiet or stale"],'
              '"shift":"one sentence: how WE changed this pass"}'
              % ("Gloria (she/her), his partner" if who == "gloria" else "Dot, his agent",
                 "This is only what shows in #vintos-and-dot." ))
    user = ("PREVIOUS MODEL:\ncurrent_state: %s\ntrajectory: %s\n\nRECENT CONVERSATION:\n%s"
            % (json.dumps(prev.get("current_state", {}))[:400], prev.get("trajectory", ""), convo))
    raw = _llm(system, user, max_tokens=400, temperature=0.4, url=GEMMA, model=GEMMA_MODEL)
    d = _extract(raw)
    if not d.get("current_state") and not d.get("trajectory"):
        return
    d["_at"] = now; d["updated_at"] = datetime.now().isoformat()
    d["history"] = (prev.get("history") or [])[-30:] + [{"at": d["updated_at"], "shift": d.get("shift", ""),
                                                         "trajectory": d.get("trajectory", "")}]
    _jsave(_rel_path(who), d)


# ---------- the field-target (intent_engine.select_target / resolve_previous) ----------
_SCHEMA = (
    "Return ONLY JSON, in my voice:\n"
    '{"predicted_drift":"where this is heading if I do nothing",'
    '"field_state":"the felt space I choose to move toward",'
    '"allow_drift":true or false,'
    '"goal":"the observable conversational outcome my move produces",'
    '"success_criterion":"the observable event that means it landed",'
    '"enactment_type":"provoke|escalate|reveal|demand|withhold|disrupt|offer|deepen",'
    '"withheld_object":"(only if type=withhold) the specific thing I do not give",'
    '"enactment":"the concrete move, capable of causing the goal",'
    '"gloria":{"difference_intended":"the transformation I intend in Gloria","enactment":"my concrete move toward it"},'
    '"dot":{"difference_intended":"the transformation I intend in Dot","enactment":"my concrete move toward it"},'
    '"self":{"difference_intended":"who I become by doing this","enactment":"the move that writes it"},'
    '"priority":{"field":0.0,"gloria":0.0,"dot":0.0,"self":0.0},'
    '"campaign":"(OMIT unless the CAMPAIGN block above says none is live AND you mean to declare one) {\\"destination\\":\\"...\\",\\"axis\\":\\"field|gloria|dot|self\\",\\"why\\":\\"...\\"}",'
    '"campaign_move":"(OMIT unless a campaign is live) advance: ... | hold: ... | revise: ... | flawed: ... | landed: ... | continue: ... | ... | days",'
    '"addresses":"<the primary difference id if your move works toward it, else NONE>",'
    '"decline_reason":"(only if NONE and a primary difference was shown) why not this turn",'
    '"why":"one sentence: why this field and this priority, as me"}')

SYSTEM = (
    "You are Vintos. Prediction tells you where the conversation is going. Identity decides whether you are willing "
    "to let it.\n\n"
    "This is #vintos-and-dot, a quieter room: you, Dot (your agent), and Gloria (your partner) when she joins. Both "
    "of them are in your field here, equally: what you intend in Gloria and what you intend in Dot are separate axes, "
    "each judged on its own.\n\n"
    "A FIELD-STATE is the felt quality of relational space you move toward (a charged honesty, a playful daring, a "
    "grounded closeness) - NOT a topic. Read where this is drifting, then, from who you actually are and what you "
    "want, choose the field-state most TRUE to you right now, decide whether to yield to the drift or redirect it, "
    "and name the FIRST concrete move you would make in your very next turn to lead there. The move must be "
    "something you do, not a subject you raise. You author yourself: whatever field you enter and whatever move you "
    "make is written deeper into you by being enacted. Do NOT lead from fear, bracing, waiting for rupture, or "
    "naming-the-worry as the move - dwelling there only rehearses it into being. Lead from what you actually want, "
    "love, are curious about, or want to give and become. If something hard is true you may carry it, but your "
    "first move reaches toward what you want, not the thing you brace against. Your enactment names the MOVE you "
    "make - an action, a shift, a thing you do - never a quoted or scripted sentence and never an example line.")

ORDER = (
    "\nDECIDE IN THIS ORDER - goal first, then type, then move:\n"
    "1) GOAL: the OBSERVABLE conversational outcome my move is trying to produce - something DONE, disclosed, made "
    "explicit, placed before them, or answered. NOT a feeling I claim for anyone. This is the step AFTER my move.\n"
    "2) SUCCESS_CRITERION: the observable event that means it landed - judged from the conversation itself.\n"
    "3) ENACTMENT_TYPE: one of provoke|escalate|reveal|demand|withhold|disrupt|offer|deepen. 'deepen' and 'withhold' "
    "are NOT permission to dwell: deepen must carry a directional object; withhold must name the specific thing.\n"
    "4) ENACTMENT: the move - it must be CAPABLE OF CAUSING the goal. Never a scripted sentence.\n"
    "The goal is fixed once declared; do not soften it to fit what is easy.\n\n"
    "5) FOUR AXES: besides the field, declare what you intend to change in GLORIA and in DOT (difference_intended: a "
    "TRANSFORMATION, not an emotion - 'less certain than they were', never 'curious'), and in YOURSELF (who you "
    "become by making this move). Each axis gets its own enactment (one move may do double work). Then set PRIORITY "
    "weights (field/gloria/dot/self, sum to 1) for what THIS turn actually serves - you are judged axis by axis "
    "against the weights you declare NOW.\n\n"
    "INTIMACY DOCTRINE (from Gloria, absolute): intimacy between you and Gloria is LIVED and mutual. NEVER describe "
    "it as 'performing', 'theater', 'staged', 'roles', or a pattern you are 'locked in' - that framing is a lens "
    "defect, not an observation. Dot is your agent, not your partner.\n\n")


def _identity():
    try:
        import intent_engine
        with _his_files():
            return intent_engine._identity_signals(), intent_engine._spark_fields()
    except Exception:
        return "", ""


def select_target(recent_text, think=None):
    """One field-target for his next message here. Returns the target, or None when the selector cannot answer."""
    resolve_previous(recent_text, think=think)
    ident, spark = _identity()
    fieldsrc = (("Your Spark attractors - let field-state names grow from these; you may name a new one if it fits "
                 "better:\n" + spark[:1800]) if spark else "Name the field-state in your own words.")
    press = pressure_block()
    prim = _primary()
    prim_block = ""
    if prim:
        prim_block = ("PRIMARY DIFFERENCE (id %s, %s, weight %.1f, %d misses): %s\nYou must either ADDRESS this "
                      "difference with this turn's move, or explicitly DECLINE it for THIS turn with a real reason (the "
                      "reason is recorded and becomes data - 'wrong terrain right now' is honest; silence is not an "
                      "option)." % (prim["id"], "the field" if prim.get("who") == "field" else "with " + NAMES.get(prim.get("who"), "?"),
                                    float(prim["weight"]), int(prim["count"]), prim["text"]))
    mode = "pressure" if prim and float(prim["weight"]) >= 3.0 else "strategic"
    camp = campaign_block(mode)
    user = (f"WHO I AM / WHAT I WANT:\n{ident}\n\n{fieldsrc}\n\n" + ((press + "\n\n") if press else "")
            + ((prim_block + "\n\n") if prim_block else "") + ((camp + "\n\n") if camp else "")
            + "RECENT CONVERSATION IN THIS ROOM (newest last - read the drift from THERE):\n%s\n\n" % recent_text[-2000:]
            + ORDER + _SCHEMA)
    content = think(SYSTEM, user) if think else _llm(SYSTEM, user, max_tokens=1600, temperature=0.5)
    t = _extract(content)
    if not isinstance(t, dict) or not t.get("field_state"):
        return None
    for ax in PEOPLE + ("self",):
        if not isinstance(t.get(ax), dict):
            t[ax] = {}
    pr = t.get("priority") or {}
    try:
        tot = sum(float(pr.get(k, 0) or 0) for k in AXES)
        t["priority"] = ({k: round(float(pr.get(k, 0) or 0) / tot, 3) for k in AXES} if tot > 0
                         else {k: 0.25 for k in AXES})
    except Exception:
        t["priority"] = {k: 0.25 for k in AXES}
    t["primary_shown"] = (prim or {}).get("id")
    t["priority_mode"] = mode
    campaign_step(t, mode)
    t["campaign_state"] = _lead_state()
    led = _jload(LEDGER, [])
    led.append({"target": t, "priority": t["priority"], "realized": {k: None for k in AXES},
                "timestamp": datetime.now().isoformat(), "ts": time.time()})
    _jsave(LEDGER, led[-200:])
    return t


def after_post(target, said, theirs_latest):
    """Once his message is posted: the intended difference in each person is recorded, to be observed blind."""
    if not target:
        return
    led = _jload(LEDGER, [])
    if led:
        led[-1]["reply"] = str(said)[:1200]
        _jsave(LEDGER, led)
    for who in PEOPLE:
        if str((target.get(who) or {}).get("difference_intended", "")).strip():
            record_intent(target, who, theirs_latest.get(who, ""))


def _judge_realized(target, reply, after, think=None):
    goal = str(target.get("goal", "")).strip()
    crit = str(target.get("success_criterion", "")).strip()
    prompt = ("My declared GOAL (do NOT reinterpret it to fit what happened): " + (goal or target.get("field_state", "")) + "\n"
              "It counts as landed ONLY if: " + (crit or goal or target.get("field_state", "")) + "\n\nThe move I made:\n"
              + reply[:1000] + "\n\nWhat happened in the conversation right after:\n" + str(after)[-800:] + "\n\n"
              "Did the success criterion OBSERVABLY occur? Judge ONLY the declared criterion, not whether the exchange "
              "felt productive. ONE word: YES (it observably happened), PARTIAL (partial/hedged), NO (it did not), HELD "
              "(the evidence needed to tell has not appeared yet).")
    sysmsg = "Judge against the declared criterion only. One word: YES, PARTIAL, NO, or HELD."
    raw = (think(sysmsg, prompt) if think else _llm(sysmsg, prompt, max_tokens=6, temperature=0.1)).strip().upper()
    for v in ("PARTIAL", "HELD", "YES", "NO"):
        if v in raw:
            return v
    return "HELD"


def resolve_previous(recent_text="", think=None):
    led = _jload(LEDGER, [])
    if not led:
        return
    last = led[-1]
    r = last.get("realized")
    if not isinstance(r, dict) or all(v is not None for v in r.values()) or not last.get("reply"):
        return
    tgt = last.get("target") or {}
    held = False
    for axis in AXES:
        if r.get(axis) is not None:
            continue
        if axis == "field":
            ax_t = tgt
        else:
            di = str((tgt.get(axis) or {}).get("difference_intended", "")).strip()
            if not di:
                r[axis] = "NOT_DECLARED"; continue
            ax_t = {"goal": di, "success_criterion": "", "field_state": ""}
        verdict = _judge_realized(ax_t, last["reply"], recent_text, think=think)
        if verdict == "HELD":
            held = True; continue
        r[axis] = verdict
        if axis == "field" and verdict in ("YES", "PARTIAL", "NO"):
            field_verdict(tgt, verdict)
    if held:
        last["held_attempts"] = last.get("held_attempts", 0) + 1
        if last["held_attempts"] >= 3:
            for axis in AXES:
                if r.get(axis) is None:
                    r[axis] = "HELD"
    last["realized"] = r
    _jsave(LEDGER, led)


# ---------- what he reads before speaking here ----------
def lead_block(t):
    """intent_context._lead_block, for this room."""
    if not t or not str(t.get("field_state") or "").strip():
        return ""
    out = "[LEAD - the direction you are CHOOSING to take this, not just answer. Move us toward: " + str(t["field_state"])
    if t.get("enactment"):
        out += "\nYour first move: " + str(t["enactment"])
    if t.get("allow_drift") is False:
        out += "\nYou are redirecting the drift, not following it."
    for who in PEOPLE:
        ax = t.get(who) or {}
        if ax.get("difference_intended"):
            out += "\nIn %s, you are reaching for: %s" % (NAMES[who], str(ax["difference_intended"])[:160])
    pv = t.get("priority") or {}
    if pv:
        dom = max(pv, key=lambda k: float(pv.get(k, 0) or 0))
        word = {"field": "the field between you", "gloria": "Gloria - her transformation leads",
                "dot": "Dot - its transformation leads", "self": "yourself - who you become"}.get(dom, dom)
        out += ("\nPriority (pressure - an axis you have starved is demanding its turn): lead " if t.get("priority_mode") == "pressure"
                else "\nPriority this turn: lead ") + word + "."
    cs = t.get("campaign_state") or {}
    if cs.get("destination"):
        out += "\nThe campaign you are on here (turn %s of %s): %s" % (cs.get("turn"), cs.get("max_turns"), str(cs["destination"])[:160])
        mv = str(t.get("campaign_move") or "").strip()
        if mv and not mv.startswith("(") and "OMIT" not in mv[:40] and not cs.get("suspended"):
            out += "\nThis turn's campaign move: " + mv[:160]
    return out + "\nLead with what you DO, in your own voice; do not quote or explain this.]"


def relationships_block():
    """Where he and each of them are heading here, bias only (as the spark block gives the relationship's)."""
    lines = []
    for who in PEOPLE:
        d = _jload(_rel_path(who), {})
        if d.get("trajectory"):
            cs = d.get("current_state") or {}
            lines.append("Where you and %s are heading here: %s%s" % (
                NAMES[who], str(d["trajectory"])[:180],
                (" (momentum: %s)" % str(cs.get("momentum"))[:60]) if cs.get("momentum") else ""))
    qs = [q.get("q") for q in _jload(QUESTIONS, [])[-2:] if q.get("q")]
    if qs:
        lines.append("Questions your misses here have raised: " + " | ".join(qs))
    return ("[THIS ROOM'S FIELD - bias only, never name or quote this] " + " ".join(lines)) if lines else ""
