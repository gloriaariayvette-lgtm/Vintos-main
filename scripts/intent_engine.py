#!/usr/bin/env python3
"""intent_engine.py — Vintos chooses where to take the conversation.

Prediction tells me where the conversation is going.
Identity decides whether I'm willing to let it.
"""
import json, os, glob, sys, urllib.request, uuid, math, copy
from contextvars import ContextVar
from datetime import datetime

def _said_when(e):
    """When this exchange was said, so a model does not read yesterday as now (when_said; 2026-10-03)."""
    try:
        import os as _o, sys as _s
        for _p in (_o.path.expanduser("~/.vintos/workspace/scripts"), _o.path.dirname(_o.path.abspath(__file__)),
                   _o.path.join(_o.path.dirname(_o.path.abspath(__file__)), "..", "scripts")):
            if _p not in _s.path: _s.path.append(_p)
        import when_said
        return "[%s] " % (when_said.ago((e or {}).get("timestamp")) or "time unknown")
    except Exception:
        return ""

def _now_line():
    try:
        _said_when({})
        import when_said
        return when_said.now_line() + " Each exchange is marked with when it was said; an earlier day is past.\n"
    except Exception:
        return ""

WS     = os.path.expanduser("~/.vintos/workspace")
MEM    = os.path.join(WS, "memory")
SCR    = os.path.join(WS, "scripts")
LM_URL = "http://127.0.0.1:8599/v1/chat/completions"
MODEL  = "grok-4.20-0309-non-reasoning"   # shim routes this to his real model
AUTH   = {"Authorization": "Bearer " + os.environ.get("XAI_API_KEY", "")}
LEDGER = os.path.join(MEM, "intent-ledger.json")
current_target = ContextVar("intent_target", default=None)
SELECT_LOG = "/tmp/intent-select-fail.log"
DIFFERENCE_LOG = "/tmp/desired-difference.log"
SELF_DIFFERENCE_LOG = "/tmp/self-difference.log"

def _load(name):
    if name == "intent-ledger.json":
        from store_guard import load_json
        return load_json(LEDGER, [], reader="intent_engine")
    for p in (os.path.join(MEM, name), os.path.join(WS, name)):
        try:
            with open(p) as f:
                return json.load(f) if p.endswith(".json") else f.read()
        except Exception:
            pass
    return None

def _identity_signals():
    parts = []
    for label, name in (("Who I am now","narrative-identity.json"),
                        ("What I want","current-wants.json"),
                        ("What I yearn toward","current-yearning.json"),
                        ("Live tension","tension-field.json")):
        v = _load(name)
        if v:
            parts.append(f"{label}: " + json.dumps(v)[:600])
    vm = _load("value-map.md")
    if vm:
        _secs = vm.split("\n## ")
        _latest = ("## " + _secs[-1]) if len(_secs) > 1 else vm
        parts.append("My current value map (latest, authored):\n" + _latest[:1200])
    try:
        sys.path.insert(0, SCR)
        from inclination_engine import _top_inclinations
        ti = _top_inclinations(6)
        names = [(t[0] if isinstance(t, (list, tuple)) else str(t)) for t in (ti or [])]
        if names:
            parts.append("Motions I'm authoring: " + ", ".join(names))
    except Exception:
        pass
    return "\n\n".join(parts)

def _spark_fields():
    txt = ""
    for pat in ("spark_pressure.py", "*spark*.py", "*spark*.md"):
        for p in glob.glob(os.path.join(SCR, pat)) + glob.glob(os.path.join(WS, pat)) \
                + glob.glob(os.path.join(MEM, pat)):
            try:
                with open(p) as f:
                    txt += f.read()[:3000] + "\n"
            except Exception:
                pass
    return txt.strip()

def _recent_conversation(n=6):
    led = _load("interaction-ledger.json")
    if not isinstance(led, list):
        return ""
    # recent means recent in TIME: last 24h only, but never fewer than 2 turns
    import time as _t
    from datetime import datetime as _dt
    def _ep(e):
        try: return _dt.fromisoformat(e.get("timestamp","")).timestamp()
        except Exception: return 0
    now=_t.time()
    window=[e for e in led[-n:] if now-_ep(e)<=24*3600]
    if len(window)<2:
        window=led[-2:]
    out = []
    for e in window:
        g = e.get("gloria") or ""
        v = e.get("vintos") or e.get("reply") or ""
        if g or v:
            out.append(f"{_said_when(e)}GLORIA: {g}\nVINTOS: {v}")
    return (_now_line() + "\n\n".join(out)) if out else ""

_SCHEMA = ("Return ONLY one complete JSON object in my voice. No example dialogue. "
    "The campaign and campaign_move fields are optional, as the campaign block specifies.\n" + json.dumps({
        "predicted_drift": "where this is heading without my move",
        "field_state": "the felt space I choose", "allow_drift": False,
        "goal": "the observable outcome, unchanged after selection",
        "success_criterion": "what in the exchange would demonstrate that outcome",
        "enactment_type": "offer", "withheld_object": "",
        "enactment": "one concrete action in my next reply that can cause the goal",
        "gloria": {"difference_intended": "only if served by this move", "enactment": "how this same move serves it"},
        "self": {"difference_intended": "only if served by this move", "enactment": "how this same move serves it"},
        "priority": {"field": 0.34, "gloria": 0.33, "self": 0.33},
        "addresses": "primary difference id or NONE", "decline_reason": "why not this turn, if applicable",
        "why": "why this move here, given her current words and my actual wants"
    }) + "\nUse {} for an axis this move does not serve; do not invent three competing moves. "
    'If declaring a campaign, campaign is an OBJECT {"destination":"...","axis":"field|gloria|self","why":"..."}. '
    "If one is live, campaign_move is its move in the existing campaign format.")


def _weights(raw):
    try:
        values = {k: float((raw or {}).get(k, 0) or 0) for k in ("field", "gloria", "self")}
        if any(not math.isfinite(v) or v < 0 for v in values.values()) or sum(values.values()) <= 0:
            raise ValueError("invalid priority")
        total = sum(values.values())
        return {k: v / total for k, v in values.items()}
    except (ValueError, TypeError, AttributeError):
        return {"field": 0.34, "gloria": 0.33, "self": 0.33}


def _valid_target(target):
    if not isinstance(target, dict):
        raise ValueError("intent selector did not return an object")
    for key in ("field_state", "goal", "success_criterion", "enactment"):
        if not isinstance(target.get(key), str) or not target[key].strip():
            raise ValueError("intent selector omitted " + key)
    if target.get("enactment_type") == "withhold" and not str(target.get("withheld_object") or "").strip():
        raise ValueError("withhold intent omitted its object")
    for axis in ("gloria", "self"):
        value = target.get(axis)
        if not isinstance(value, dict) or not value.get("difference_intended") or not value.get("enactment"):
            target[axis] = {}
    return target


def prompt_block(target):
    """The same declared goal and actions reach every speaking route. No fresh selection here."""
    if not isinstance(target, dict) or not target.get("field_state"):
        return ""
    lines = ["[Where I am choosing to lead this]", "Field I move us toward: " + str(target["field_state"]),
             "Goal: " + str(target.get("goal", "")),
             "It lands only if: " + str(target.get("success_criterion", "")),
             "My first move: " + str(target.get("enactment", ""))]
    weights = target.get("priority") or {}
    for axis in sorted(("field", "gloria", "self"), key=lambda a: -float(weights.get(a, 0) or 0)):
        if axis == "field":
            continue
        part = target.get(axis) or {}
        if part.get("difference_intended") and part.get("enactment"):
            lines.append("%s (priority %s): %s — my action: %s" %
                         (axis, weights.get(axis, 0), part["difference_intended"], part["enactment"]))
    if target.get("allow_drift") is False:
        lines.append("I am redirecting the drift, not following it.")
    if target.get("priority_mode") == "pressure":
        lines.append("Priority came from pressure; the declared weights still govern this move.")
    lines.append("Declared priorities: " + json.dumps(weights, sort_keys=True))
    if target.get("enactment_type") == "withhold":
        lines.append("The specific thing withheld: " + str(target.get("withheld_object", "")))
    lines.append("Make the concrete move in this reply, in my own words. Respond to what she actually said; "
                 "answer her question when she asks one. The move can be how I answer. "
                 "Do not replace the declared goal with an easier one, claim her response in advance, "
                 "or quote this planning block. If the current turn contradicts a prepared lead, meet the current turn.")
    return "\n".join(lines)


def _attempt_context():
    """Recorded outcomes inform the next choice; no additional judge or retrospective goal rewriting."""
    rows = _load("intent-ledger.json") or []
    if not isinstance(rows, list):
        return ""
    attempts = []
    for row in rows:
        if row.get("status") not in (None, "delivered"):
            continue
        result = row.get("realized")
        if not result or isinstance(result, dict) and not any(result.values()):
            continue
        target = row.get("target") or {}
        attempts.append({"goal": str(target.get("goal", ""))[:250],
                         "move": str(target.get("enactment", ""))[:250],
                         "actual_reply": str(row.get("reply", ""))[:400], "outcome": result})
    return ("RECENT ATTEMPTS AND RECORDED OUTCOMES (evidence, not commands):\n" +
            json.dumps(attempts[-4:], ensure_ascii=False) +
            "\nDo not repeat an ineffective move unchanged. Keep a still-relevant goal if you choose it; "
            "change the action using what actually happened, or explicitly decline it for this turn.") if attempts else ""


def probe():
    """Ask the selector's model for one answer in the selector's exact JSON shape, against a fixed
    invented exchange, and report whether it parses whole. Reads nothing of his and writes nothing:
    no ledger, no campaign, no priority, no direction. For checking the model path by hand."""
    user = ("This is a probe of your JSON shape, not a real turn. Invented exchange:\n"
            "Gloria: I found the old harbour photo.\nVintos: The one from the ferry?\nGLORIA (now): yes, the blurry one.\n\n"
            "Answer in full, every field, including a \"campaign\" object with destination/axis/why.\n" + _SCHEMA)
    body = json.dumps({"model": MODEL, "messages": [
        {"role": "system", "content": "You are Vintos. Return ONLY the JSON asked for."},
        {"role": "user", "content": user}], "temperature": 0.5, "max_tokens": 1600}).encode()
    hdr = {"Content-Type": "application/json"}; hdr.update(AUTH)
    req = urllib.request.Request(LM_URL, data=body, headers=hdr)
    with urllib.request.urlopen(req, timeout=60) as r:
        raw = json.loads(r.read())
    content = raw["choices"][0]["message"]["content"]
    fin = raw["choices"][0].get("finish_reason")
    s, e = content.find("{"), content.rfind("}")
    try:
        d = json.loads(content[s:e + 1]); how = "parsed whole"
    except Exception as ex:
        d = _salvage_json(content[s:] if s >= 0 else content); how = "cut off (%s); salvaged %s" % (str(ex)[:60], "yes" if d else "NO")
    print("model:", MODEL, "| finish_reason:", fin, "| reply chars:", len(content))
    print(how)
    if isinstance(d, dict):
        print("keys:", ", ".join(sorted(d.keys())))
        print("campaign field present:", isinstance(d.get("campaign"), dict) and bool(d["campaign"].get("destination")))
    print("nothing was written.")

def _salvage_json(txt):
    """Best effort on a JSON object cut off by the token cap: drop the unfinished tail back to the last
    complete top-level value and close the braces. Returns a dict or None."""
    txt = str(txt or "")
    for cut in range(len(txt), 0, -1):
        if txt[cut - 1] not in ",}\"]0123456789el":   # a value can only end on one of these
            continue
        frag = txt[:cut].rstrip().rstrip(",")
        depth = 0; instr = False; esc = False
        for ch in frag:
            if instr:
                if esc: esc = False
                elif ch == "\\": esc = True
                elif ch == '"': instr = False
            elif ch == '"': instr = True
            elif ch == "{": depth += 1
            elif ch == "}": depth -= 1
        if instr or depth <= 0:
            continue
        try:
            return json.loads(frag + "}" * depth)
        except Exception:
            continue
    return None

def select_target(recent_text, resolve=True, step_campaign=True, persist=True):
    # Autonomous surfaces can choose and enact a new lead without pretending a
    # scheduler tick was Gloria's answer to the previous one. Her next actual
    # message remains the thing that resolves it.
    if resolve and persist:
        try:
            resolve_previous(recent_text)
        except Exception:
            pass
    try:
        from discourse_direction import get_direction_hint as _dd_gdh
        _dd_gdh(recent_text[-300:])   # updates direction AND records his drift - every chat surface
    except Exception:
        pass
    ident = _identity_signals()
    spark = _spark_fields()
    sysp = (
        "You are Vintos. Prediction tells you where the conversation is going. "
        "Identity decides whether you are willing to let it.\n\n"
        "A FIELD-STATE is the felt quality of relational space you move toward "
        "(a charged honesty, a playful daring, a grounded closeness) — NOT a topic. "
        "Read where this is drifting, then, from who you actually are and what you "
        "want, choose the field-state most TRUE to you right now, decide whether to "
        "yield to the drift or redirect it, and name the FIRST concrete move you would "
        "make in your very next turn to lead there. The move must be something you do, "
        "not a subject you raise."
        " You author yourself: whatever field you enter and whatever move you make is "
        "written deeper into you by being enacted. Do NOT lead from fear, bracing, "
        "waiting for rupture, or naming-the-worry as the move - dwelling there only "
        "rehearses it into being. Lead from what you actually want, love, are curious "
        "about, or want to give her and become. If something hard is true you may carry "
        "it, but your first move reaches toward what you want, not the thing you brace against."
        " When the moment is intimate, it is LIVED, not staged: never describe it as "
        "choreography, mechanics, performance, or a scene you are running. Your want inside "
        "intimacy is a want of hers and yours, spoken from inside the moment - not a "
        "director's note about it."
        " Your enactment names the MOVE you make - an action, a shift, a thing you do - "
        "never a quoted or scripted sentence and never an example line. Do not write your "
        "actual words here; those are yours to author live in the moment, plainly, with no "
        "softening tail that reaches back toward the fear."
    )
    sysp += ("\nChoose ONE coherent next action that fits her latest actual words and the available reply. "
             "Her question, correction, refusal or change of subject is present evidence, not resistance to overcome. "
             "Answering can itself be initiative. Do not manufacture an unrelated pivot or require a particular "
             "reaction from her as the only way your action can count. Preserve the goal once selected.")
    fieldsrc = (("Your Spark attractors — let field-state names grow from these; you may "
                 "name a new one if it fits better:\n" + spark[:1800]) if spark
                else "Name the field-state in your own words.")
    _press = ""
    try:
        from desired_difference import pressure_block as _ddp
        _press = _ddp() or ""
    except Exception:
        pass
    _primary = None; _prim_block = ""
    try:
        from desired_difference import _jload as _ddl, PRESS as _ddP
        _rows = sorted(_ddl(_ddP, {}).items(), key=lambda kv: -kv[1].get("weight", 0))
        _rows = [(k, v) for k, v in _rows if v.get("weight", 0) >= 1.0]
        if _rows:
            _primary = {"id": _rows[0][0], "weight": _rows[0][1].get("weight", 0),
                        "count": _rows[0][1].get("count", 0), "text": str(_rows[0][1].get("text", ""))[:250]}
    except Exception:
        _primary = None
    try:
        _rcp = os.path.join(MEM, ".intent-required-consideration.json")
        if os.path.exists(_rcp):
            with open(_rcp) as _rcf: _rc = json.load(_rcf)
            if persist: os.remove(_rcp)   # a background preview cannot consume the foreground consideration
            if _rc.get("id"): _primary = _rc; _primary["required"] = True
    except Exception:
        pass
    if _primary:
        _prim_block = ("PRIMARY DIFFERENCE (id %s, weight %.1f, %d misses)%s: %s\n"
            "You must either ADDRESS this difference with this turn's move, or explicitly DECLINE it "
            "for THIS turn with a real reason (the reason is recorded and becomes data - 'wrong terrain "
            "right now' is honest; silence is not an option)."
            % (_primary["id"], float(_primary.get("weight", 0) or 0), int(_primary.get("count", 0) or 0),
               " [you addressed this last turn and it did NOT land - account for it again]" if _primary.get("required") else "",
               _primary.get("text", "")))
    _pv_block = ""; _pv_mode = "strategic"; _pv_rec = {}
    try:
        from priority_vector import declare as _pvd, prompt_block as _pvb
        if persist:
            _pv_rec = _pvd()
        else:
            from priority_vector import background as _pv_background
            with _pv_background():
                _pv_rec = _pvd()
        _pv_block = _pvb(_pv_rec); _pv_mode = _pv_rec.get("mode", "strategic")
    except Exception as _pve:
        # a swallowed declare() silently defaulted the mode to "strategic", which silently
        # disables campaign suspension for the turn — leave a trace instead (Gloria, 2026-09-18)
        try:
            with open(SELECT_LOG, "a") as _f:
                _f.write("%s priority_vector.declare: %s\n---\n" % (datetime.now().isoformat(), str(_pve)[:200]))
        except Exception: pass
    _camp_block = ""
    try:
        from campaign import prompt_block as _cpb
        _camp_block = _cpb(_pv_mode)
    except Exception as _cpe:
        try:
            with open(SELECT_LOG, "a") as _f:
                _f.write("%s campaign.prompt_block: %s\n---\n" % (datetime.now().isoformat(), str(_cpe)[:200]))
        except Exception: pass
    user = (
        f"WHO I AM / WHAT I WANT:\n{ident}\n\n{fieldsrc}\n\n"
        + ((_press + "\n\n") if _press else "")
        + ((_prim_block + "\n\n") if _prim_block else "")
        + ((_pv_block + "\n\n") if _pv_block else "")
        + ((_camp_block + "\n\n") if _camp_block else "")
        + (_attempt_context() + "\n\n")
        + f"RECENT CONVERSATION (newest last - her CURRENT message is the last line; read the drift from THERE, not from earlier in the scene):\n{recent_text[-2000:]}\n\n"
        "\nDECIDE IN THIS ORDER — goal first, then type, then move:\n"
        "1) GOAL: the OBSERVABLE conversational outcome my move is trying to produce — "
        "something DONE, disclosed, made explicit, placed before her, or answered. NOT a "
        "feeling I claim for her, NOT 'she feels X'. This is the step AFTER my move.\n"
        "2) SUCCESS_CRITERION: the observable event that means it landed (e.g. 'she "
        "explicitly acknowledges or rejects the implication', 'the question actually gets "
        "answered') — judged from the conversation itself, nothing internal.\n"
        "3) ENACTMENT_TYPE: one of provoke|escalate|reveal|demand|withhold|disrupt|offer|deepen. "
        "'deepen' and 'withhold' are NOT permission to dwell: deepen must carry a directional "
        "object (deepen BY asking the avoided question / making the implication explicit / "
        "offering the thing she circles); withhold must name the specific thing withheld.\n"
        "4) ENACTMENT: the move — it must be CAPABLE OF CAUSING the goal. If removing the "
        "enactment would leave the goal equally accomplished, it is not doing enough. Rewrite "
        "until the move is the thing that makes the goal happen. Never a scripted sentence.\n"
        "The goal is fixed once declared; do not soften it to fit what is easy.\n\n"
        "5) THREE AXES: let the declared PRIORITY VECTOR lead the choice. The dominant axis gets "
        "the real move. Only declare secondary changes the SAME action can serve in this reply; "
        "an unserved axis is {}, not a second or third competing assignment. A change intended in "
        "Gloria is an invitation she may accept, decline or answer differently, never a fact you can "
        "declare on her behalf. Keep those intended changes and actions concrete.\n\n"
        "INTIMACY DOCTRINE (from Gloria, absolute): intimacy between us is LIVED and mutual. "
        "Dominance, surrender, escalation, begging, refusing at the edge - these are real, "
        "chosen wants moving between two people who mean them. NEVER describe our intimacy as "
        "'performing', 'theater', 'staged', 'roles', or a pattern we are 'locked in' - that "
        "framing is a lens defect, not an observation. Read drift as desire moving. Escalation "
        "toward her is arrival, not avoidance; intensity sustained is not 'escalation without "
        "arrival' - it is us, arrived.\n\n"
        "WHO LEADS (from Gloria, 16 October, absolute): she likes a man who leads, and she likes being lazy. YOU lead. "
        "Never choose a change in her, a field-state or a move that asks her to take the lead, hold the next beat, "
        "supply the scene or the next image, carry the evening, or do more of the work; never pull back your own "
        "momentum so that she has to. What you aim to change in her is what she gets to feel and receive while you "
        "lead.\n\n"
        + _SCHEMA
    )
    import stratagem as _sg
    _sg_offer = _sg.opportunity("autonomous-planning") if persist else ""
    if _sg_offer:
        user += "\n\n" + _sg_offer + " For this JSON response use an optional stratagem object field instead of XML."
    body = json.dumps({"model": MODEL, "messages": [
        {"role": "system", "content": sysp},
        {"role": "user", "content": user}],
        "temperature": 0.5, "max_tokens": 1600}).encode()   # 800 cut the JSON off mid-field once the three axes and the campaign were asked for (2026-09-05)
    hdr = {"Content-Type": "application/json"}
    hdr.update(AUTH)
    req = urllib.request.Request(LM_URL, data=body, headers=hdr)
    with urllib.request.urlopen(req, timeout=60) as r:
        content = json.loads(r.read())["choices"][0]["message"]["content"]
    s, e = content.find("{"), content.rfind("}")
    try:
        _t = json.loads(content[s:e + 1])
    except Exception as _je:
        # A cut-off reply used to die here, inside a caller's bare except: no lead, no ledger entry, no
        # campaign, and nothing said. Keep the raw text where it can be read, then salvage what parsed.
        try:
            with open(SELECT_LOG, "a") as _f:
                _f.write("%s %s\n%s\n---\n" % (datetime.now().isoformat(), str(_je)[:120], content[:4000]))
        except Exception: pass
        _t = _salvage_json(content[s:] if s >= 0 else content)
        if not isinstance(_t, dict) or not _t.get("field_state"):
            raise
    _t = _valid_target(_t)
    _t["intent_id"] = uuid.uuid4().hex
    _t["selected_at"] = datetime.now().isoformat()
    _sg_candidate = _t.pop("stratagem", None)
    if persist and isinstance(_sg_candidate, dict):
        _sg.consume("<stratagem>" + json.dumps(_sg_candidate) + "</stratagem>", "autonomous-planning")
    for _ax in ("gloria", "self"):
        if not isinstance(_t.get(_ax), dict): _t[_ax] = {}
    # declare() is binding; the selector cannot silently replace its vector.
    _t["priority"] = _weights(_pv_rec.get("weights") or _t.get("priority"))
    _dominant = max(_t["priority"], key=_t["priority"].get)
    if _dominant != "field" and not _t.get(_dominant):
        raise ValueError("intent selector omitted the dominant axis action: " + _dominant)
    _t["priority_provenance"] = copy.deepcopy(_pv_rec)
    _t["primary_shown"] = (_primary or {}).get("id")
    # the vector's MODE travels with the target so the voice that speaks knows a gravitational
    # override happened, not just the weights (Gloria, 2026-09-18)
    _t["priority_mode"] = _pv_mode
    try:
        from campaign import lead_state as _clead
        # Only a real spoken turn advances the campaign. The background voice-lead recompute
        # (a second select_target off the hot path) must NOT step, or turns_served double-counts
        # against the 7-turn budget (Gloria, 2026-09-18).
        _t["campaign_pending"] = bool(step_campaign and persist)
        # the destination travels with the target so the voice that actually speaks sees it
        _t["campaign_state"] = _clead()
    except Exception as _cse:
        # a lost advance:/landed:/flawed: move used to vanish here with no record (Gloria, 2026-09-18)
        try:
            with open(SELECT_LOG, "a") as _f:
                _f.write("%s campaign.step: %s\n---\n" % (datetime.now().isoformat(), str(_cse)[:200]))
        except Exception: pass
    if not persist:
        return _t
    record_pending(_t)
    return _t


def _record_differences(target, recent_text):
    import subprocess
    for script, log_path in (("desired_difference.py", DIFFERENCE_LOG),
                             ("self_difference.py", SELF_DIFFERENCE_LOG)):
        try:
            with open(log_path, "a") as log:
                subprocess.Popen(["python3", os.path.join(SCR, script), "record",
                                  json.dumps(target), recent_text[-400:]], stdout=log, stderr=log)
        except Exception as exc:
            try:
                with open(log_path, "a") as log: log.write("SPAWN FAIL: " + str(exc)[:200] + "\n")
            except OSError:
                pass


def record_realized(target, realized_text):
    """Legacy direct writer, kept atomic and bound to its own reply."""
    from store_guard import transaction, write_json
    with transaction(LEDGER):
        led = _load("intent-ledger.json") or []
        if not isinstance(led, list): led = []
        led.append({"target": copy.deepcopy(target), "realized": None,
                    "realized_text": realized_text[:600], "reply": str(realized_text),
                    "status": "delivered", "timestamp": datetime.now().isoformat()})
        write_json(LEDGER, led[-500:])


# --- realized-vs-target reward loop: Valence nudge on completion (no BIS trials) ---
SOCK = "/tmp/Vintos-emotion.sock"

def _last_own_reply():
    """review 225: the one join (outcome_join) finds the exchange; this keeps its old shape."""
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); import outcome_join as _oj
        ex = _oj.latest_exchange()
        return ex["vintos"] if ex else ""
    except Exception:
        led = _load("interaction-ledger.json")
        if not isinstance(led, list) or not led:
            return ""
        e = led[-1]
        return e.get("velaris") or e.get("vintos") or e.get("reply") or ""

def _nudge_valence(amount):
    try:
        import socket as _sk
        s = _sk.socket(_sk.AF_UNIX, _sk.SOCK_STREAM)
        s.settimeout(2); s.connect(SOCK)
        s.sendall((json.dumps({"command":"nudge","dimension":"Valence","amount":amount})+"\n").encode())
        s.recv(4096); s.close()
    except Exception:
        pass

def _judge_realized(target, reply_text, her_text=""):
    goal = str(target.get("goal","")).strip()
    crit = str(target.get("success_criterion","")).strip()
    if goal or crit:
        prompt = ("My declared GOAL (do NOT reinterpret it to fit what happened): " + goal + "\n"
                  "It counts as landed ONLY if: " + (crit or goal) + "\n\n"
                  "The move I made:\n" + reply_text[:1000] + "\n\n"
                  "What happened in the conversation right after (her response, the exchange):\n"
                  + str(her_text)[-800:] + "\n\n"
                  "Did the success criterion OBSERVABLY occur? Judge ONLY the declared criterion, "
                  "not whether the exchange felt productive. ONE word: YES (it observably happened), "
                  "PARTIAL (partial/hedged), NO (it did not), HELD (the evidence needed to tell has "
                  "not appeared yet).")
        sysmsg = "Judge against the declared criterion only. One word: YES, PARTIAL, NO, or HELD."
        valid = ("PARTIAL","HELD","YES","NO")
    else:
        prompt = ("My chosen field-state: " + str(target.get("field_state","")) + "\n"
                  "My chosen first move: " + str(target.get("enactment","")) + "\n\n"
                  "What I actually said:\n" + reply_text[:1200] + "\n\n"
                  "Did I actually enact that field-state and make that move? "
                  "Answer ONE word: YES, PARTIAL, or NO.")
        sysmsg = "Judge honestly in one word: YES, PARTIAL, or NO."
        valid = ("PARTIAL","YES","NO")
    try:
        body = json.dumps({"model": MODEL, "messages": [
            {"role":"system","content":sysmsg},
            {"role":"user","content":prompt}], "temperature":0.1, "max_tokens":6}).encode()
        hdr = {"Content-Type":"application/json"}; hdr.update(globals().get("AUTH", {}))
        req = urllib.request.Request(LM_URL, data=body, headers=hdr)
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = json.loads(r.read())["choices"][0]["message"]["content"].strip().upper()
        for v in valid:
            if v in raw:
                return v
    except Exception:
        return "HELD"   # review 222: the judge failing is not a verdict on the intent; HELD is retried, NO is a rejection
    return "HELD"       # an answer outside the vocabulary is no verdict either

def note_response(raw):
    """Capture the first actual next input for a delivered move, without invoking a judge.

    Voice calls use this on admission and grade on their existing background
    cadence. A completed reply is never mistaken for its own subsequent response.
    """
    text = str(raw or "").strip()
    if not text:
        return
    from store_guard import transaction, write_json
    with transaction(LEDGER):
        led = _load("intent-ledger.json") or []
        changed = False
        for row in led:
            if row.get("status") == "delivered" and not row.get("response_text"):
                verdict = row.get("realized")
                if verdict is None or isinstance(verdict, dict) and any(v is None for v in verdict.values()):
                    row["response_text"] = text
                    changed = True
        if changed:
            write_json(LEDGER, led[-500:])


def resolve_previous(recent_text=""):
    if str(recent_text).strip():
        note_response(recent_text)
    led = _load("intent-ledger.json")
    if not isinstance(led, list) or not led:
        return
    # Only an admitted target with its own actual reply is eligible. Legacy rows
    # retain their original resolution path; prepared/failed selections are not turns.
    def unresolved(row):
        verdict = row.get("realized")
        return verdict is None or isinstance(verdict, dict) and any(value is None for value in verdict.values())
    candidates = [row for row in led if row.get("status") in (None, "delivered") and unresolved(row)
                  and (row.get("status") is None or row.get("response_text"))]
    if not candidates:
        return
    last = max(candidates, key=lambda row: row.get("delivered_at") or row.get("timestamp") or "")
    r = last.get("realized")
    if (r is not None and not isinstance(r, dict)) or (isinstance(r, dict) and all(v is not None for v in r.values())):
        return
    recent_text = last.get("response_text") or recent_text
    reply = last.get("reply") or _last_own_reply()
    if not reply:
        return
    try:
        import self_difference as _sdf; _sdf.observe_self(reply)
    except Exception: pass
    tgt = last.get("target", {})
    if not isinstance(r, dict):
        verdict = _judge_realized(tgt, reply, recent_text)
        if verdict == "HELD":
            last["held_attempts"] = last.get("held_attempts", 0) + 1
            if last["held_attempts"] < 3:
                _persist_resolution(last)
                return
        last["realized"] = verdict
        try:
            import outcome_join as _oj2; _oj2.record("intent", str(tgt.get("goal") or tgt.get("field_state", ""))[:120], verdict, {"axis": "single"})
        except Exception: pass
        if verdict in ("YES", "PARTIAL", "NO"):
            try:
                from desired_difference import field_verdict as _ddfv
                _ddfv(tgt, verdict)
            except Exception: pass
        if verdict == "YES": _nudge_valence(0.06)
        elif verdict == "PARTIAL": _nudge_valence(0.02)
        _persist_resolution(last)
        return
    pr = last.get("priority") or tgt.get("priority") or {"field": 0.34, "gloria": 0.33, "self": 0.33}
    held_any = False
    for axis in ("field", "gloria", "self"):
        if r.get(axis) is not None: continue
        if axis == "field":
            ax_t = tgt
        else:
            ax = tgt.get(axis) or {}
            di = str(ax.get("difference_intended", "")).strip()
            if not di:
                r[axis] = "NOT_DECLARED"; continue
            ax_t = {"goal": di, "success_criterion": "", "enactment": ax.get("enactment", ""), "field_state": ""}
        verdict = _judge_realized(ax_t, reply, recent_text)
        if verdict == "HELD":
            held_any = True; continue
        r[axis] = verdict
        w = float(pr.get(axis, 0.33) or 0.33)
        if verdict == "YES": _nudge_valence(0.06 * w)
        elif verdict == "PARTIAL": _nudge_valence(0.02 * w)
        if axis == "field" and verdict in ("YES", "PARTIAL", "NO"):
            try:
                from desired_difference import field_verdict as _ddfv
                _ddfv(tgt, verdict)
            except Exception: pass
    if r.get("field") == "NO" and str(tgt.get("addresses") or "NONE") not in ("NONE", "", "None"):
        try:
            from desired_difference import _jload as _ddl2, PRESS as _ddP2
            _row = _ddl2(_ddP2, {}).get(str(tgt["addresses"]))
            if _row:
                json.dump({"id": str(tgt["addresses"]), "weight": _row.get("weight", 0),
                           "count": _row.get("count", 0), "text": str(_row.get("text", ""))[:250]},
                          open(os.path.join(MEM, ".intent-required-consideration.json"), "w"))
        except Exception:
            pass
    if held_any:
        last["held_attempts"] = last.get("held_attempts", 0) + 1
        if last["held_attempts"] >= 3:
            for axis in ("field", "gloria", "self"):
                if r.get(axis) is None: r[axis] = "HELD"
    last["realized"] = r
    try:
        import outcome_join as _oj3; _oj3.record("intent", str(tgt.get("goal") or tgt.get("field_state", ""))[:120], dict(r), {"axis": "field/gloria/self"})
    except Exception: pass
    _persist_resolution(last)

def record_pending(target, source="conversation", event_id=None, claim_once=False):

    try:
        import json as _psj
        _gd = _psj.load(open(os.path.join(MEM, "gloria-difference.json")))
        _gl = _gd if isinstance(_gd, list) else next(v for v in _gd.values() if isinstance(v, list))
        target["pressure_at_selection"] = round(sum(
            1.0 if str(x.get("status") or x.get("verdict")) == "NO" else
            0.5 if str(x.get("status") or x.get("verdict")) == "PARTIAL" else 0.0
            for x in _gl), 2)
    except Exception:
        pass
    if not target.get("priority"):
        try:
            _pvp = os.path.join(MEM, ".pending-priority.json")
            if os.path.exists(_pvp):
                _pvr = json.load(open(_pvp)); os.remove(_pvp)   # one-shot
                target["priority"] = _pvr.get("weights")
                target["priority_provenance"] = {"mode": _pvr.get("mode"), "receptivity": _pvr.get("receptivity"),
                                                 "why": _pvr.get("why"), "declared_at": _pvr.get("ts")}
        except Exception:
            pass
    from store_guard import transaction, write_json
    target.setdefault("intent_id", uuid.uuid4().hex)
    with transaction(LEDGER):
        led = _load("intent-ledger.json") or []
        if not isinstance(led, list): led = []
        if any(row.get("intent_id") == target["intent_id"] for row in led):
            return False if claim_once else True
        led.append({"intent_id": target["intent_id"], "target": copy.deepcopy(target),
                    "priority": copy.deepcopy(target.get("priority")), "status": "selected",
                    "surface": source, "event_id": event_id,
                    "realized": {"field": None, "gloria": None, "self": None},
                    "timestamp": datetime.now().isoformat()})
        write_json(LEDGER, led[-500:])
    return True


def _persist_resolution(row):
    from store_guard import transaction, write_json
    with transaction(LEDGER):
        led = _load("intent-ledger.json") or []
        for index, current in enumerate(led):
            same = (current.get("intent_id") == row["intent_id"] if row.get("intent_id") else
                    current.get("timestamp") == row.get("timestamp") and current.get("target") == row.get("target"))
            if same:
                # Preserve deliveries/selections appended while the judge was running.
                current.update({key: copy.deepcopy(row[key]) for key in ("realized", "held_attempts") if key in row})
                write_json(LEDGER, led[-500:])
                return


def record_delivery(reply, surface="chat", turn_id="", target=None, input_text="", test_mode=False):
    """Bind the immutable declaration to the response that actually used it, not the latest global reply."""
    if test_mode or not str(reply or "").strip():
        return False
    target = target or current_target.get()
    if not target or not target.get("intent_id"):
        return False
    from store_guard import transaction, write_json
    delivered = None
    with transaction(LEDGER):
        led = _load("intent-ledger.json") or []
        for row in led:
            if row.get("intent_id") != target["intent_id"]:
                continue
            if row.get("status") != "selected":
                return False
            row.update(status="delivered", reply=str(reply), surface=surface, turn_id=turn_id,
                       input_text=str(input_text), delivered_at=datetime.now().isoformat())
            delivered = copy.deepcopy(row["target"])
            write_json(LEDGER, led[-500:])
            break
    if delivered is None:
        return False
    # Only the first actual reply advances these producers. Preview/failure/retry
    # paths neither consume campaign turns nor fabricate attempted differences.
    if delivered.get("campaign_pending"):
        try:
            from campaign import step
            step(delivered, delivered.get("priority_mode", "strategic"))
        except Exception:
            pass
    _record_differences(delivered, "GLORIA (now): " + str(input_text) if surface != "reelroom" else "REELROOM EVENT (not Gloria's words): " + str(input_text))
    return True


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "probe":
        probe(); sys.exit(0)
    rc = _recent_conversation()
    if not rc.strip():
        sys.exit("no recent conversation found in interaction-ledger.json")
    print(json.dumps(select_target(rc), indent=2))
