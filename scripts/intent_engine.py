#!/usr/bin/env python3
"""intent_engine.py — Vintos chooses where to take the conversation.

Prediction tells me where the conversation is going.
Identity decides whether I'm willing to let it.
"""
import json, os, glob, sys, urllib.request, uuid, math, copy, re
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
        "observation_window": "her_next_reply", "evidence_type": "her_response",
        "enactment_type": "offer", "withheld_object": "",
        "enactment": "one concrete action in my next reply that can cause the goal",
        "gloria": {"difference_intended": "only if served by this move", "enactment": "how this same move serves it",
                   "observation_window": "her_next_reply", "evidence_type": "her_response"},
        "self": {"difference_intended": "only if served by this move", "enactment": "how this same move serves it",
                 "observation_window": "this_reply", "evidence_type": "my_move"},
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


# Where a success criterion can be seen (10 November). Seven in thirty criteria could not be met inside what
# the judge is shown: a later day, a particular sentence from her. The selector now says where its criterion
# shows, in two fields that are checked by form only - no reading of the criterion's meaning happens here.
WINDOWS = ("this_reply", "her_next_reply")
EVIDENCE = ("my_move", "her_response")
_QUOTE_DEMAND = re.compile(r"\b(?:exact(?:ly)? (?:the )?(?:words?|phrase|sentence)|word for word|verbatim|in those words)\b", re.I)


def _criterion_fault(target, axis="field"):
    """A fixed code for what is wrong with where the criterion can be seen, or "" when it is in order. `target`
    is the whole target for the field, or the axis's own object: a change in her shows in her next reply, in
    her response; a change in me shows in this reply, in my move."""
    def norm(v): return re.sub(r"[^a-z]+", "_", str(v or "").strip().lower()).strip("_")
    w, ev = norm(target.get("observation_window")), norm(target.get("evidence_type"))
    if not w: return "window_missing"
    if w not in WINDOWS: return "window_invalid"
    if not ev: return "evidence_missing"
    if ev not in EVIDENCE: return "evidence_invalid"
    if ev == "her_response" and w == "this_reply": return "window_evidence_mismatch"   # her answer is not in my reply
    if axis == "gloria" and ev != "her_response": return "evidence_not_her_response"
    if axis == "self" and ev != "my_move": return "evidence_not_my_move"
    if axis == "self" and w != "this_reply": return "window_not_this_reply"
    target["observation_window"], target["evidence_type"] = w, ev
    return ""


# What followed my move, and whose it is (10 November). A device event - the button, a touch, a spin - was stored as
# the follow-up under her label and graded as her answer: NO, on words she never said.
DEVICE_SOURCES = ("gcs", "reelroom_event")
_DEVICE_EVENT = re.compile(r"\[(?:she pressed\b|gloria just (?:touched|spun)\b)[^\]]*\]", re.I)
_HER_LABEL = "GLORIA (now):"
_EVENT_LABEL = "REELROOM EVENT (not Gloria's words):"
_held_why = ContextVar("intent_held_why", default="")
# A device event after my move is not her next reply, and it must not use that reply up (10 November). An axis
# that shows in her next reply - and an old row that never said where it shows - waits for her own words through
# at most DEVICE_SKIPS_MAX such turns, and no row is observed later than DEVICE_WAIT_HOURS hours after its ORIGINAL
# observation window opened, whichever ends first; after that it is HELD with WINDOW_EXPIRED, and no judge is asked.
# The window opens at the row's delivered_at - written once, when the move reached her - or, for a row from
# before deliveries were recorded, at its own timestamp; a later skipped event never moves it. What is measured
# against it is when the follow-up arrived (response_at), or now where none is stored. There is no sweeper: the
# age is read before any grading, and a report reads an overdue pending row as EXPIRED_COVERAGE - not pending,
# never NO. A row with no readable time is overdue (10 November, round four).
DEVICE_SKIPS_MAX = 3
DEVICE_WAIT_HOURS = 24
WINDOW_EXPIRED = "her_reply_window_expired"
EXPIRED_COVERAGE = "expired_coverage"


def _stamp(value):
    try: return datetime.fromisoformat(str(value)).timestamp()
    except Exception: return None


def _unsettled(row):
    verdict = row.get("realized")
    return verdict is None or isinstance(verdict, dict) and any(v is None for v in verdict.values())


def _window_overdue(row, now=None):
    """True when what follows this row came, or would come, after its observation window closed."""
    opened = _stamp(row.get("delivered_at")) or _stamp(row.get("timestamp"))
    if opened is None:
        return True
    seen = _stamp(row.get("response_at")) or now or datetime.now().timestamp()
    return seen - opened > DEVICE_WAIT_HOURS * 3600


def row_coverage(row, now=None, axis=None):
    """How a ledger row counts in a report: "settled", "pending", or EXPIRED_COVERAGE - still unsettled after
    its window closed, or already HELD for that reason. `axis` reads one axis of a three-axis row. A selection
    that never became a turn (prepared, failed, superseded) awaits nothing: "undelivered". Reads only; the row
    itself is expired when it next comes up for grading."""
    if not isinstance(row, dict):
        return "settled"
    if row.get("status") not in (None, "delivered"):
        return "undelivered"
    verdict = row.get("realized")
    why = row.get("held_reason") if isinstance(row.get("held_reason"), dict) else {}
    if axis and isinstance(verdict, dict):
        waiting, gone = verdict.get(axis) is None, why.get(axis) == WINDOW_EXPIRED
    else:
        waiting, gone = _unsettled(row), WINDOW_EXPIRED in why.values()
    if waiting:
        return EXPIRED_COVERAGE if _window_overdue(row, now) else "pending"
    return EXPIRED_COVERAGE if gone else "settled"


def _her_follow_up(text, source=None):
    """(the follow-up with only her own words in its live part, "") - or ("", reason) when it holds none.

    Where the turn came from decides first; the text is read only when no source came with it. Reasons are
    fixed codes: device_event_only, not_her_words, no_reply. A photo or video she sent is hers."""
    text = str(text or "")
    if source in DEVICE_SOURCES:
        return "", "device_event_only"
    hi, ei = text.rfind(_HER_LABEL), text.rfind(_EVENT_LABEL)
    if ei > hi:
        return "", "not_her_words"
    live = text[hi + len(_HER_LABEL):] if hi >= 0 else text
    if not live.strip():
        return "", "no_reply"
    hers = _DEVICE_EVENT.sub(" ", live).strip()
    if not hers:
        return "", "device_event_only"
    # Earlier conversation is selector context, not evidence observed after this move.
    return ((_HER_LABEL + " ") if hi >= 0 else "") + hers, ""


def _her_live_words(text, source=None):
    """Only what she herself said in this turn, and only where the turn is marked as hers: no earlier lines, no
    device event, no note that she sent a photo, no text that came without her label. "" when there is none."""
    hers, why = _her_follow_up(text, source)
    i = hers.rfind(_HER_LABEL)
    if why or i < 0:
        return ""
    return re.sub(r"^\s*\(she sent a \w+\)", " ", hers[i + len(_HER_LABEL):]).strip()


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
    _fb = target.get("lead_fallback")
    if isinstance(_fb, dict):
        # the heaviest axis was left undeclared: the weights below must not read as a pointer to a goal that is absent
        _gone = ("The field's criterion is left unjudged this turn" if _fb.get("from") == "field"
                 else "My %s axis is undeclared this turn" % _fb.get("from"))
        lines.append((_gone + "; %s leads this move instead."
                      % ("the field" if _fb.get("to") == "field" else "my %s axis" % _fb.get("to")))
                     if _fb.get("to") else
                     (_gone + " and no other axis is declared: no axis leads this move."))
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
        if isinstance(result, dict) and _unsettled(row) and _window_overdue(row):
            # an axis whose window closed unobserved is said so, not shown as still open (10 November, round four)
            result = {k: (EXPIRED_COVERAGE if v is None else v) for k, v in result.items()}
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

def _ask_selector(messages):
    """One selector call, parsed. A cut-off answer is logged and salvaged, as before."""
    body = json.dumps({"model": MODEL, "messages": messages,
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
    return _valid_target(_t), content


def _selection_faults(target, opportunity):
    """What one re-ask may mend, as (fixed code, the sentence that asks for it, whose it is). Form only."""
    out = []
    code = _criterion_fault(target)
    if code:
        out.append((code, "the success criterion did not say where it can be seen: observation_window must be "
                          "this_reply or her_next_reply, evidence_type must be my_move or her_response, and "
                          "her_response cannot be seen in this_reply", "field"))
    for axis, where in (("gloria", "observation_window must be her_next_reply and evidence_type must be her_response"),
                        ("self", "observation_window must be this_reply and evidence_type must be my_move")):
        ax = target.get(axis)
        code = _criterion_fault(ax, axis) if isinstance(ax, dict) and ax else ""
        if code:      # only a declared axis is checked; an empty one has nothing to show
            out.append((code, "the \"%s\" axis did not say where its difference can be seen: inside \"%s\", %s"
                        % (axis, axis, where), axis))
    if opportunity and not target.get("gloria") and not str(target.get("gloria_decline") or "").strip():
        out.append(("opportunity_unanswered", "the Gloria opportunity was due and \"gloria\" came back empty with no "
                    "\"gloria_decline\": declare the one small change this same move invites in her, or leave it {} "
                    "and give the reason in gloria_decline", "opportunity"))
    return out


# A write of the turn state whose error is swallowed is never passed off as a protected update (10 November,
# round four). Each such site runs through _guarded: an error is said as FAILED (the write did not happen), a
# write made with the lock or the store guard missing as UNPROTECTED - in SELECT_LOG, counted in
# TURN_STATE_FAULTS, and on the target as turn_state_faults where there is one. A clean run adds nothing.
TURN_STATE_FAULTS = {"failed": 0, "unprotected": 0, "error": 0}
_NOT_DONE = object()


def _fault_marks():
    """(writes made unprotected, writes that failed) so far, as the two writers count them themselves."""
    loose = lost = 0
    for name in ("desired_difference", "priority_vector"):
        mod = sys.modules.get(name)
        try:
            loose += int((getattr(mod, "_UNLOCKED", None) or {}).get("n", 0) or 0)
            loose += int((getattr(mod, "_UNGUARDED", None) or {}).get("n", 0) or 0)
            lost += int((getattr(mod, "_UNGUARDED", None) or {}).get("failed", 0) or 0)
        except Exception: pass
    return loose, lost


def _turn_state_fault(site, result, err=None, into=None):
    TURN_STATE_FAULTS[result] = TURN_STATE_FAULTS.get(result, 0) + 1
    try:
        with open(SELECT_LOG, "a") as _f:
            # "error" is an error swallowed around a whole step (the resolver), whatever raised it: it is said as
            # that, never as a lock fault it may not have been (review, round four)
            _f.write("%s %s at %s: %s\n---\n" % (datetime.now().isoformat(),
                     "resolver ERROR" if result == "error" else "turn-state write " + result.upper(), site,
                     ((type(err).__name__ + ": " + str(err))[:200] if err is not None else "lock or store guard unavailable")))
    except Exception: pass
    if isinstance(into, list):
        into.append({"site": site, "result": result})


def _guarded(site, fn, into=None, default=None, whole=False):
    """Run one turn-state write whose error the caller swallows, and say what became of it. `whole` marks a
    site that wraps a whole step and not one write (the resolver): its own error is an "error" of that step."""
    loose, lost = _fault_marks()
    try:
        out = fn()
    except Exception as err:
        _turn_state_fault(site, "error" if whole else "failed", err, into)
        return default
    loose2, lost2 = _fault_marks()
    if lost2 > lost: _turn_state_fault(site, "failed", None, into)
    elif loose2 > loose: _turn_state_fault(site, "unprotected", None, into)
    return out


def select_target(recent_text, resolve=True, step_campaign=True, persist=True, her_source=None):
    _turn = {}
    try:
        return _select_target(recent_text, resolve, step_campaign, persist, her_source, _turn)
    except Exception as _err:
        if _turn.get("reserved") and not _turn.get("recorded"):
            # The showing was reserved before the model saw it, and this turn then failed. The reservation
            # COUNTS (round four): it is not handed back, so no number of failing turns can pass the cap; the
            # failure is recorded beside the rotation and here, under a fixed code.
            def _note():
                from desired_difference import reservation_failed as _ddrf
                return _ddrf(_turn.get("primary"))
            _guarded("reservation_failed", _note)
            try:
                with open(SELECT_LOG, "a") as _f:
                    _f.write("%s primary_reserved_turn_failed: primary %s; %s\n---\n"
                             % (datetime.now().isoformat(), _turn.get("primary"), (type(_err).__name__ + ": " + str(_err))[:200]))
            except Exception: pass
        raise


def _select_target(recent_text, resolve, step_campaign, persist, her_source, _turn):
    # Autonomous surfaces can choose and enact a new lead without pretending a
    # scheduler tick was Gloria's answer to the previous one. Her next actual
    # message remains the thing that resolves it.
    _tsf = []     # this selection's turn-state writes that failed or went unprotected
    if resolve and persist:
        _guarded("resolve_previous", lambda: resolve_previous(recent_text, **({"source": her_source} if her_source else {})), _tsf, whole=True)
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
    # Whose turn this is comes before any pressure (10 November, round four). One accounting for all of it: an
    # ELIGIBLE turn is one of her own foreground turns. Only that is shown pressure or a primary, and only that
    # moves the run, the rests or her cadence. A device-only event (or a background run that persists) is
    # shown neither and moves none of them - device traffic can neither use a primary's allowance up nor walk
    # the rotation on while no rest can be discharged - and the required consideration waits for her next
    # turn. A preview of her own turn still sees what that turn would see, and moves nothing.
    _her_turn = _her_follow_up(recent_text, her_source)[1] not in ("device_event_only", "not_her_words")
    try:
        from priority_vector import _foreground as _pvfg
        _fg = bool(_pvfg())
    except Exception:
        _fg = True
    _eligible = bool(_her_turn and _fg)
    # how this target's primary is accounted: "reserved" at exposure, "not_eligible" (nothing shown, nothing
    # counted), "failed" (the reservation could not be made: nothing shown), or "" - a preview, counted only if
    # it is later admitted as a turn
    _acct = "not_eligible" if (not _her_turn or (persist and not _fg)) else ("reserved" if persist else "")
    _press = ""
    if _acct != "not_eligible":
        try:
            from desired_difference import pressure_block as _ddp
            _press = _ddp() or ""
        except Exception:
            pass
    _primary = None; _prim_block = ""; _rc = None
    _rcp = os.path.join(MEM, ".intent-required-consideration.json")
    if _acct == "reserved":
        # her own words in this real turn may raise a graduated intention again; a preview reopens nothing
        _hers_now = _her_live_words(recent_text, her_source)
        if _hers_now:
            def _reopen():
                from desired_difference import her_words_reopen as _ddhr
                return _ddhr(_hers_now)
            _guarded("her_words_reopen", _reopen, _tsf)
        def _reserve():
            # One gate for every route to the primary, the required consideration included: rotation, rest,
            # graduation, retirement; nothing eligible means no primary this turn (10 November). The marker is
            # consumed, the primary picked and its showing COUNTED in one step under the turn-state lock,
            # BEFORE the model sees it (round four): two turns at once cannot both be given the last showing of
            # a run. The model is asked after the lock is released.
            from desired_difference import primary_reserve as _ddpr, _turn_state as _tsl, marker_consumed as _ddmc
            with _tsl(_rcp):
                _m = None; _had = os.path.exists(_rcp)
                if _had:
                    try:
                        with open(_rcp) as _rcf: _m = json.load(_rcf)
                    except Exception: _m = None
                _lost = _fault_marks()[1]
                _p = _ddpr(_m if isinstance(_m, dict) else None)
                # the marker goes only once the count it was honoured in is written (review, round four): a
                # count that was lost leaves the required consideration standing for her next turn
                if _had and _fault_marks()[1] == _lost:
                    try: _ddmc(_m); os.remove(_rcp)     # its key kept before it goes (round five)
                    except Exception as _rme: _turn_state_fault("required_consideration.consume", "failed", _rme, _tsf)
                return _p
        _primary = _guarded("primary_reserve", _reserve, _tsf, _NOT_DONE)
        _said = [f["result"] for f in _tsf if f.get("site") == "primary_reserve"]
        if _primary is _NOT_DONE or "failed" in _said:
            # no reservation - the lock not taken, or the count not written - so nothing is shown: the cap is
            # never left to chance
            _primary = None; _acct = "failed"
        else:
            # counted, but with the lock or the store guard missing: the accounting says so itself
            if "unprotected" in _said: _acct = "reserved_unprotected"
            _turn["reserved"] = True; _turn["primary"] = (_primary or {}).get("id")
    elif not _acct:
        try:
            from desired_difference import _turn_state as _tsl
            with _tsl(_rcp):              # read, never consumed: a background preview cannot take the foreground consideration
                if os.path.exists(_rcp):
                    with open(_rcp) as _rcf: _rc = json.load(_rcf)
        except Exception:
            _rc = None
        try:
            from desired_difference import primary_for_turn as _ddpt
            _primary = _ddpt(_rc if isinstance(_rc, dict) else None)
        except Exception:
            _primary = None
    if _primary:
        _prim_block = ("PRIMARY DIFFERENCE (id %s, weight %.1f, %d misses)%s: %s\n"
            "You must either ADDRESS this difference with this turn's move, or explicitly DECLINE it "
            "for THIS turn with a real reason (the reason is recorded and becomes data - 'wrong terrain "
            "right now' is honest; silence is not an option)."
            % (_primary["id"], float(_primary.get("weight", 0) or 0), int(_primary.get("count", 0) or 0),
               " [you addressed this last turn and it did NOT land - account for it again]" if _primary.get("required") else "",
               _primary.get("text", "")))
    _pv_block = ""; _pv_mode = "strategic"; _pv_rec = {}
    # a turn that is a device event or a room event is not one of her turns: her opportunity is not spent on it
    _pv_kw = {} if _her_turn else {"eligible": False}
    try:
        from priority_vector import declare as _pvd, prompt_block as _pvb
        if persist:
            _pv_rec = _pvd(**_pv_kw)
        else:
            from priority_vector import background as _pv_background
            with _pv_background():
                _pv_rec = _pvd(**_pv_kw)
        _pv_block = _pvb(_pv_rec); _pv_mode = _pv_rec.get("mode", "strategic")
    except Exception as _pve:
        # a swallowed declare() silently defaulted the mode to "strategic", which silently
        # disables campaign suspension for the turn — leave a trace instead (Gloria, 2026-09-18)
        try:
            with open(SELECT_LOG, "a") as _f:
                _f.write("%s priority_vector.declare: %s\n---\n" % (datetime.now().isoformat(), str(_pve)[:200]))
        except Exception: pass
        _turn_state_fault("priority_vector.declare", "failed", _pve, _tsf)
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
        "WHAT SHE HAS TOLD YOU SHE LIKES (Gloria, 16 October): a man who leads, and being free to be lazy. Know this "
        "about her and let it shape your choice: leading is your natural ground with her, and an aim that hands her "
        "the lead, has her hold the next beat or carry the evening, or has you pull back so that she must, goes "
        "against what she has said she likes - choose it only when the moment itself clearly asks for it.\n\n"
        "WHERE THE CRITERION SHOWS (10 November): the success criterion is one your own move can "
        "meet, or one her ordinary next message can show in her own way. It does not wait on a later day or need a "
        "particular sentence from her. Say where it shows: observation_window "
        "is this_reply or her_next_reply; evidence_type is my_move or her_response.\n\n"
        + _SCHEMA
    )
    import stratagem as _sg
    _sg_offer = _sg.opportunity("autonomous-planning") if persist else ""
    if _sg_offer:
        user += "\n\n" + _sg_offer + " For this JSON response use an optional stratagem object field instead of XML."
    _msgs = [{"role": "system", "content": sysp}, {"role": "user", "content": user}]
    _t, _raw = _ask_selector(_msgs)
    # One re-ask, and only for form: where the criterion shows, or a due opportunity left unanswered. A second
    # faulty answer is not mended here - that axis is left undeclared with its reason; nothing is invented.
    _opp = bool(_pv_rec.get("gloria_opportunity"))
    _faults = _selection_faults(_t, _opp); _check = {"retry": 0}
    if _faults:
        _check["retry"] = 1
        try:
            _t2, _raw2 = _ask_selector(_msgs + [{"role": "assistant", "content": _raw}, {"role": "user", "content":
                "CORRECTION, once: " + "; ".join(f[1] for f in _faults) + ". Return the same JSON object again, "
                "complete, with only that mended. Do not invent a goal to fill a slot."}])
            _f2 = _selection_faults(_t2, _opp)
            if len(_f2) <= len(_faults): _t, _faults = _t2, _f2
        except Exception:
            pass
    _abst = {f[2]: f[0] for f in _faults if f[2] != "opportunity"}
    _crit = _abst.pop("field", "")
    _check["fault"] = _crit; _check["abstained"] = bool(_crit)
    _t.pop("criterion_abstained", None); _t.pop("gloria_abstained", None)   # ours to set, never the selector's
    _t.pop("axis_abstained", None); _t.pop("lead_axis", None); _t.pop("lead_fallback", None); _t.pop("her_turn", None)
    _t.pop("primary_accounting", None); _t.pop("turn_state_faults", None)
    if _abst:
        # that axis alone is left undeclared, with its reason; the field and the other axis stand as given
        for _ax in _abst: _t[_ax] = {}
        _t["axis_abstained"] = dict(_abst); _check["axis_faults"] = dict(_abst)
    if _crit:
        _t["criterion_abstained"] = _crit       # the move stands; its field criterion is never judged
    if _QUOTE_DEMAND.search(str(_t.get("success_criterion", ""))):
        _check["flags"] = ["quotation_demand"]  # a flag to count, never a rejection
    if _opp:
        if _t.get("gloria"): _check["gloria_opportunity"] = "declared"
        else:
            _check["gloria_opportunity"] = "abstained"
            _t["gloria_abstained"] = "declined" if str(_t.get("gloria_decline") or "").strip() else "no_answer"
    _t["selection_check"] = _check
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
    if _dominant != "field" and not _t.get(_dominant) and _dominant not in _abst:
        raise ValueError("intent selector omitted the dominant axis action: " + _dominant)
    # The lead is an axis that is really declared (10 November). When the dominant axis was emptied after the
    # one re-ask, the lead falls to the next valid axis by the declared weights - the field unless its own
    # criterion was abstained, the other axis if it is declared - or to none. The weights stay as declared.
    # Every path ends here (round four): the dominant FIELD whose own criterion was abstained falls the same way,
    # so lead_axis is always an axis that is validly declared, or None, with lead_fallback saying what it left.
    _declared = lambda _a: (not _crit) if _a == "field" else (isinstance(_t.get(_a), dict) and bool(_t.get(_a)))
    _lead = _dominant
    if not _declared(_dominant):
        _lead = next((_a for _a in sorted(("field", "gloria", "self"), key=lambda _a: -float(_t["priority"].get(_a, 0) or 0))
                      if _a != _dominant and _declared(_a)), None)
        _t["lead_fallback"] = {"from": _dominant, "to": _lead}
    _t["lead_axis"] = _lead
    _t["priority_provenance"] = copy.deepcopy(_pv_rec)
    _t["primary_shown"] = (_primary or {}).get("id")
    _t["primary_required"] = bool((_primary or {}).get("required"))
    # one of her own foreground turns, or not: only those are shown a primary and move the rotation (10 November)
    _t["her_turn"] = _eligible
    if _acct: _t["primary_accounting"] = _acct
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
    if _tsf: _t["turn_state_faults"] = _tsf
    record_pending(_t)
    _turn["recorded"] = True
    def _cadence():
        # her opportunity counter moves only here, once a real selection is complete (10 November)
        from priority_vector import note_selection as _pvn
        return _pvn(bool(_t.get("gloria")), opportunity=_opp, eligible=_her_turn)
    _guarded("note_selection", _cadence, _tsf)
    if _tsf: _t["turn_state_faults"] = _tsf
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
        observation = ("Evidence source: my_move. Judge the delivered reply alone; a later response is not "
                       "evidence of an action in that reply.\n"
                       if target.get("evidence_type") == "my_move" else
                       "What happened in the conversation right after (her response, the exchange):\n"
                       + str(her_text)[-800:] + "\n")
        prompt = ("My declared GOAL (do NOT reinterpret it to fit what happened): " + goal + "\n"
                  "It counts as landed ONLY if: " + (crit or goal) + "\n\n"
                  "The move I made:\n" + reply_text[:1000] + "\n\n"
                  + observation + "\n"
                  "Did the success criterion OBSERVABLY occur? Judge ONLY the declared criterion, "
                  "not whether the exchange felt productive. ONE word: YES (it observably happened), "
                  "PARTIAL (partial/hedged), NO (it did not), HELD (the evidence needed to tell has "
                  "not appeared yet). A criterion that waits on something later than this exchange, or on "
                  "something that cannot be seen in it at all, is HELD, not NO.")
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
    _held_why.set("judge_unavailable")   # why a HELD is a HELD travels beside it, as a fixed code (10 November)
    try:
        body = json.dumps({"model": MODEL, "messages": [
            {"role":"system","content":sysmsg},
            {"role":"user","content":prompt}], "temperature":0.1, "max_tokens":6}).encode()
        hdr = {"Content-Type":"application/json"}; hdr.update(globals().get("AUTH", {}))
        req = urllib.request.Request(LM_URL, data=body, headers=hdr)
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = json.loads(r.read())["choices"][0]["message"]["content"].strip().upper()
        token = re.fullmatch(r"(PARTIAL|HELD|YES|NO)[.!]?", raw)
        if token and token[1] in valid:
            if token[1] == "HELD": _held_why.set("unobservable_criterion")
            return token[1]
        _held_why.set("judge_no_verdict")
    except Exception:
        return "HELD"   # review 222: the judge failing is not a verdict on the intent; HELD is retried, NO is a rejection
    return "HELD"       # an answer outside the vocabulary is no verdict either

def note_response(raw, source=None):
    """Capture the first actual next input for a delivered move, without invoking a judge.

    Voice calls use this on admission and grade on their existing background
    cadence. A completed reply is never mistaken for its own subsequent response.
    `source` is where that input came from (the turn's input kind), kept beside it.
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
                    row["response_at"] = datetime.now().isoformat()   # when it came: the window is read against this, not against a later grading
                    if source: row["response_source"] = str(source)
                    row["resolution_rev"] = int(row.get("resolution_rev", 0) or 0) + 1   # what a resolver reads has changed (round five)
                    changed = True
        if changed:
            write_json(LEDGER, led[-500:])


def resolve_previous(recent_text="", source=None):
    if str(recent_text).strip():
        note_response(recent_text, **({"source": source} if source else {}))
    # effects an accepted verdict left unapplied - a process that died after it was written, a write that failed -
    # are applied first, each once (round five)
    try: _drain_effects()
    except Exception as err: _turn_state_fault("resolve_previous.effects", "error", err)
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
    _order = lambda row: row.get("delivered_at") or row.get("timestamp") or ""
    last = max(candidates, key=_order)
    # An earlier move still waiting on her next reply after a device event is settled by this same follow-up:
    # those rows first, oldest first, then the latest move as before. A row is settled once - a settled row is
    # no candidate again (10 November).
    for row in sorted((c for c in candidates if c is not last and isinstance(c.get("skipped_observations"), dict)), key=_order):
        _guarded("resolve_previous.waiting_row", lambda row=row: _resolve_row(row, recent_text, source), whole=True)
    _resolve_row(last, recent_text, source)


def _resolve_row(last, recent_text="", source=None):
    r = last.get("realized")
    if (r is not None and not isinstance(r, dict)) or (isinstance(r, dict) and all(v is not None for v in r.values())):
        return
    if last.get("response_text"):
        recent_text, source = last["response_text"], last.get("response_source")
    reply = last.get("reply") or _last_own_reply()
    if not reply:
        return
    _skip = last.get("skipped_observations") if isinstance(last.get("skipped_observations"), dict) else None
    _rev = int(last.get("resolution_rev", 0) or 0)   # the revision this resolver read: its result lands only on it (round five)
    fx = []                                           # the effects its result asks for, published only if it lands
    # his reply is observed once for the row however many passes it takes: claimed on the row first, so at most once
    if not _skip and _claim_effect(last, "observe_self"):
        try:
            import self_difference as _sdf; _sdf.observe_self(reply)
        except Exception: pass
    tgt = last.get("target", {})
    # Whose the follow-up is comes before any judge (10 November): a device event, or nothing of hers, is not
    # her answer. Such a move is HELD at once with its reason and no model is asked; where her words sit beside
    # a device event the judge sees her words only.
    _hers, _none = _her_follow_up(recent_text, source)
    _now = datetime.now().timestamp()
    # the age is the row's own, from its delivery - never from a skipped event, and with or without one (round four)
    _late = _window_overdue(last, _now)
    if not _none and not _late:
        recent_text = _hers
    elif _late or isinstance(r, dict) or str(tgt.get("goal", "")).strip() or str(tgt.get("success_criterion", "")).strip():
        # (an old row with no goal is graded on my own reply alone and needs no words of hers: it goes on below -
        #  unless its window closed long ago: then it is HELD here like any other, and no judge is asked)
        if _none == "no_reply" and not last.get("response_text") and not _late:
            return      # nothing has followed this move yet: it waits, unjudged
        _device = _none in ("device_event_only", "not_her_words")
        if _device and not _late:
            # the skipped observation is kept on the row: how many, when, why - never the text
            try: _n = int((_skip or {}).get("n", 0) or 0) + 1
            except Exception: _n = 1
            _skip = dict(_skip or {}, n=_n, last=_now, reason=_none)
            _skip.setdefault("first", _now)
            if source: _skip["source"] = str(source)
            last["skipped_observations"] = _skip
            _late = _n > DEVICE_SKIPS_MAX
        _why = WINDOW_EXPIRED if _late else _none
        # an axis that shows in this reply is HELD at once, as before; one that shows in her next reply waits for it
        _waits = lambda part: bool(_device and not _late and str((part or {}).get("observation_window") or "") != "this_reply")
        _kept = last.get("held_reason") if isinstance(last.get("held_reason"), dict) else {}
        if isinstance(r, dict):
            for axis in ("gloria", "self"):
                if r.get(axis) is None and not str((tgt.get(axis) or {}).get("difference_intended", "")).strip():
                    r[axis] = "NOT_DECLARED"
            _reasons = {axis: why for axis, why in _kept.items() if r.get(axis) == "HELD"}
            for axis in ("field", "gloria", "self"):
                if r.get(axis) is None and not _waits(tgt if axis == "field" else tgt.get(axis)):
                    r[axis] = "HELD"; _reasons[axis] = _why
            last["realized"] = r
            _settled = all(v is not None for v in r.values())
        else:
            _reasons = {}
            if not _waits(tgt):
                last["realized"] = "HELD"; _reasons = {"single": _why}
            _settled = last.get("realized") is not None
        if _reasons: last["held_reason"] = _reasons
        else: last.pop("held_reason", None)
        if _settled:
            fx.append({"dest": "outcome", "verdict": copy.deepcopy(last["realized"]),
                       "detail": {"axis": "field/gloria/self" if isinstance(r, dict) else "single"}})
        else:
            last.pop("response_text", None); last.pop("response_source", None); last.pop("response_at", None)   # the device event was not her reply: that is still to come
        _land(last, _rev, fx)
        return
    if not isinstance(r, dict):
        _held_why.set("")
        verdict = _judge_realized(tgt, reply, recent_text)
        if verdict == "HELD":
            last["held_attempts"] = last.get("held_attempts", 0) + 1
            last["held_reason"] = {"single": _held_why.get() or "judge_held"}
            if last["held_attempts"] < 3:
                _land(last, _rev, fx)
                return
        else:
            last.pop("held_reason", None)
        last["realized"] = verdict
        fx.append({"dest": "outcome", "verdict": verdict, "detail": {"axis": "single"}})
        if verdict in ("YES", "PARTIAL", "NO"): fx.append({"dest": "pressure", "axis": "single", "verdict": verdict})
        if verdict in ("YES", "PARTIAL"): fx.append({"dest": "valence", "axis": "single", "verdict": verdict, "amount": 0.06 if verdict == "YES" else 0.02})
        _land(last, _rev, fx)
        return
    pr = last.get("priority") or tgt.get("priority") or {"field": 0.34, "gloria": 0.33, "self": 0.33}
    held_any = False; held_why = {}; field_open = r.get("field") is None
    for axis in ("field", "gloria", "self"):
        if r.get(axis) is not None: continue
        if axis == "field":
            ax_t = tgt
        else:
            ax = tgt.get(axis) or {}
            di = str(ax.get("difference_intended", "")).strip()
            if not di:
                r[axis] = "NOT_DECLARED"; continue
            ax_t = {"goal": di, "success_criterion": "", "enactment": ax.get("enactment", ""), "field_state": "",
                    "observation_window": ax.get("observation_window"), "evidence_type": ax.get("evidence_type")}
        _held_why.set("")
        verdict = _judge_realized(ax_t, reply, recent_text)
        if verdict == "HELD":
            held_any = True; held_why[axis] = _held_why.get() or "judge_held"; continue
        r[axis] = verdict
        w = float(pr.get(axis, 0.33) or 0.33)
        if verdict in ("YES", "PARTIAL"):
            fx.append({"dest": "valence", "axis": axis, "verdict": verdict, "amount": (0.06 if verdict == "YES" else 0.02) * w})
        if axis == "field" and verdict in ("YES", "PARTIAL", "NO"): fx.append({"dest": "pressure", "axis": "field", "verdict": verdict})
    # A miss on an addressed difference asks for it once more on the next turn - once: a turn that was itself
    # that second asking does not ask a third time, and a retired row is not asked for at all (10 November).
    if (field_open and r.get("field") == "NO" and str(tgt.get("addresses") or "NONE") not in ("NONE", "", "None")
            and not (tgt.get("primary_required") and str(tgt.get("primary_shown")) == str(tgt["addresses"]))):
        fx.append({"dest": "required_consideration", "axis": "field", "verdict": "NO"})
    if held_any:
        last["held_attempts"] = last.get("held_attempts", 0) + 1
        if last["held_attempts"] >= 3:
            for axis in ("field", "gloria", "self"):
                if r.get(axis) is None: r[axis] = "HELD"
    # the reason of an axis that is already finally HELD (a device event, an expiry) stays beside this pass's
    _kept = last.get("held_reason") if isinstance(last.get("held_reason"), dict) else {}
    held_why = dict({axis: why for axis, why in _kept.items() if r.get(axis) == "HELD"}, **held_why)
    if held_why: last["held_reason"] = held_why
    else: last.pop("held_reason", None)
    last["realized"] = r
    fx.append({"dest": "outcome", "verdict": dict(r), "detail": {"axis": "field/gloria/self"}})
    _land(last, _rev, fx)

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
    if "primary_shown" in target and not target.get("primary_accounting"):
        # A lead prepared in a preview and admitted now (the voice route). Its primary was picked when the
        # preview ran, and nothing was counted then; a turn may have reserved the last showing of that run
        # since. So before this lead is recorded or shown, the pick is looked at again and counted in one step
        # under the turn-state lock (review, round four). If it may no longer stand, or the count cannot be
        # written, nothing is admitted: the cap is not left to chance on this route either. A preview that
        # carried no primary has nothing to cap: it is admitted whatever became of the count, and says so.
        with transaction(LEDGER):
            _seen = _load("intent-ledger.json") or []
            if isinstance(_seen, list) and any(isinstance(row, dict) and row.get("intent_id") == target["intent_id"] for row in _seen):
                return False if claim_once else True
        def _admit():
            from desired_difference import primary_admit as _dda
            return _dda(target.get("primary_shown"), bool(target.get("primary_required")), her_turn=bool(target.get("her_turn", True)))
        _af = []
        _ok = _guarded("record_pending.primary_admit", _admit, _af, _NOT_DONE)
        _how = [f["result"] for f in _af]
        _uncounted = _ok is not True or "failed" in _how
        if _uncounted and target.get("primary_shown"):
            try:
                with open(SELECT_LOG, "a") as _f:
                    _f.write("%s primary_admission_refused: primary %s; %s\n---\n" % (datetime.now().isoformat(),
                             target.get("primary_shown"), "not_eligible_now" if _ok is False else "count_not_written"))
            except Exception: pass
            return False
        target["primary_accounting"] = ("failed" if _uncounted else
                                        "admitted_unprotected" if "unprotected" in _how else "admitted")
    with transaction(LEDGER):
        led = _load("intent-ledger.json") or []
        if not isinstance(led, list): led = []
        if any(row.get("intent_id") == target["intent_id"] for row in led):
            return False if claim_once else True
        # An axis the selector abstained on is undeclared from birth, with its reason: it is never judged and
        # never enters a landing rate (10 November).
        realized = {"field": None, "gloria": None, "self": None}; why = {}
        if target.get("criterion_abstained"):
            realized["field"] = "NOT_DECLARED"; why["field"] = "criterion_" + str(target["criterion_abstained"])
        if target.get("gloria_abstained") and not target.get("gloria"):
            realized["gloria"] = "NOT_DECLARED"; why["gloria"] = "opportunity_" + str(target["gloria_abstained"])
        row = {"intent_id": target["intent_id"], "target": copy.deepcopy(target),
               "priority": copy.deepcopy(target.get("priority")), "status": "selected",
               "surface": source, "event_id": event_id, "realized": realized,
               "timestamp": datetime.now().isoformat()}
        _axa = target.get("axis_abstained")
        for _ax in ("gloria", "self"):
            if isinstance(_axa, dict) and _axa.get(_ax) and not target.get(_ax):
                realized[_ax] = "NOT_DECLARED"; why[_ax] = "criterion_" + str(_axa[_ax])
        if why: row["not_declared_reason"] = why
        led.append(row)
        write_json(LEDGER, led[-500:])
    # One real selection, counted once, whatever verdict it later gets: the run a primary may lead (10 November).
    # A turn's own selection was counted when it was reserved, a device-only event counts nothing, and a lead
    # prepared in a preview was counted above, before this row was written (round four).
    return True


# ---- round five: a resolver's result lands only on what it read, and each of its effects happens once ---------
# Two resolvers can judge one row at once (her turn and the voice lane), and the judge is asked outside any lock:
# a slow HELD used to land on top of three YES another resolver had written, and a late NO weighed the pressure
# again. A resolver now reads the row's resolution_rev with the row, and its result is written only if the row is
# still at that revision - note_response and every accepted result move it on - and never over a settled verdict.
# A result that is not written is dropped with everything it asked for (no pressure, no marker, no valence, no
# outcome) and said: RESOLUTION_DROPPED, a line in SELECT_LOG, resolution_dropped on the row. An accepted result
# writes its effects on the row as effects_pending in the same ledger write, each with a key - row, destination,
# axis and verdict, an outcome by the revision it was accepted at - and they are applied after, outside the
# ledger lock. Each destination keeps that key in the very write that makes the effect, so a process that died
# between the two is run again (the next resolve_previous) and changes nothing twice. The valence socket keeps
# no record: its nudge is taken off the row first and then sent - at most once.
RESOLUTION_DROPPED = {"stale_revision": 0, "settled_axis": 0, "row_gone": 0}
_AT_MOST_ONCE = ("valence",)
EFFECTS_KEPT = 50


def _row_key(row):
    if row.get("intent_id"): return str(row["intent_id"])
    import hashlib
    return "legacy-" + hashlib.sha1(json.dumps([row.get("timestamp"), row.get("target")], sort_keys=True, default=str).encode()).hexdigest()[:16]


def _same_row(current, row):
    return isinstance(current, dict) and (current.get("intent_id") == row["intent_id"] if row.get("intent_id") else
                                          current.get("timestamp") == row.get("timestamp") and current.get("target") == row.get("target"))


def _overwrites_settled(now, new):
    if isinstance(now, dict):
        return "settled_axis" if any(v is not None and (not isinstance(new, dict) or new.get(k) != v) for k, v in now.items()) else ""
    return "settled_axis" if (now is not None and new != now) else ""


def _persist_resolution(row, read_rev=0, effects=()):
    """Write a resolver's result if the row is still at the revision it read; True when it landed."""
    from store_guard import transaction, write_json
    why, now_rev = "row_gone", None
    with transaction(LEDGER):
        led = _load("intent-ledger.json") or []
        for current in led:
            if not _same_row(current, row): continue
            now_rev = int(current.get("resolution_rev", 0) or 0)
            why = "stale_revision" if now_rev != int(read_rev or 0) else _overwrites_settled(current.get("realized"), row.get("realized"))
            if why:
                _d = current.get("resolution_dropped") if isinstance(current.get("resolution_dropped"), dict) else {}
                current["resolution_dropped"] = {"n": int(_d.get("n", 0) or 0) + 1, "reason": why, "at": datetime.now().isoformat()}
            else:
                # Preserve deliveries/selections appended while the judge was running.
                current.update({key: copy.deepcopy(row[key]) for key in ("realized", "held_attempts", "held_reason", "skipped_observations") if key in row})
                if "held_reason" not in row: current.pop("held_reason", None)
                if "skipped_observations" in row and "response_text" not in row:
                    current.pop("response_text", None); current.pop("response_source", None); current.pop("response_at", None)   # so her next reply is stored
                current["resolution_rev"] = now_rev + 1
                rk = _row_key(current); pend = list(current.get("effects_pending") or [])
                for fx in effects:
                    tail = ("r%d" % (now_rev + 1)) if fx["dest"] == "outcome" else "%s:%s" % (fx.get("axis"), fx.get("verdict"))
                    fx = dict(copy.deepcopy(fx), key="%s:%s:%s" % (rk, fx["dest"], tail))
                    if all(p.get("key") != fx["key"] for p in pend): pend.append(fx)
                if pend: current["effects_pending"] = pend
            write_json(LEDGER, led[-500:])
            break
    if why:
        RESOLUTION_DROPPED[why] = RESOLUTION_DROPPED.get(why, 0) + 1
        try:
            with open(SELECT_LOG, "a") as _f:
                _f.write("%s resolution DROPPED (%s): row %s was read at revision %s and is at %s now; its verdicts and their effects are not published\n---\n"
                         % (datetime.now().isoformat(), why, _row_key(row), read_rev, now_rev))
        except Exception: pass
    return not why


def _land(row, read_rev, effects):
    """A resolver's last step: its result, if it lands, then the effects it asked for."""
    if _persist_resolution(row, read_rev, effects) and effects:
        try: _drain_effects(_row_key(row))
        except Exception as err: _turn_state_fault("resolve_previous.effects", "error", err)


def _settle_effect(row, key, pending=True):
    """Under the ledger lock: take `key` off the row's effects_pending (or, pending=False, claim it fresh) and keep
    it in effects_done. True only for the one caller that did so."""
    from store_guard import transaction, write_json
    with transaction(LEDGER):
        led = _load("intent-ledger.json") or []
        for current in led:
            if not _same_row(current, row): continue
            done = list(current.get("effects_done") or [])
            if pending:
                pend = [p for p in (current.get("effects_pending") or []) if isinstance(p, dict)]
                if all(p.get("key") != key for p in pend): return False
                rest = [p for p in pend if p.get("key") != key]
                if rest: current["effects_pending"] = rest
                else: current.pop("effects_pending", None)
            elif key in done:
                return False
            current["effects_done"] = (done + [key])[-EFFECTS_KEPT:]
            write_json(LEDGER, led[-500:])
            return True
    return False


def _claim_effect(row, name):
    try: return _settle_effect(row, "%s:%s" % (_row_key(row), name), pending=False)
    except Exception: return False


def _drain_effects(only=None):
    """Apply the effects accepted results left on their rows, oldest first; each is taken off its row once done."""
    from store_guard import transaction
    with transaction(LEDGER):
        led = _load("intent-ledger.json") or []
        todo = [copy.deepcopy(r) for r in (led if isinstance(led, list) else [])
                if isinstance(r, dict) and r.get("effects_pending") and (only is None or _row_key(r) == only)]
    for row in todo:
        for fx in list(row.get("effects_pending") or []):
            if not isinstance(fx, dict) or not fx.get("key"): continue
            if fx.get("dest") in _AT_MOST_ONCE:
                if _settle_effect(row, fx["key"]): _apply_effect(row, fx)
            elif _apply_effect(row, fx) is not _NOT_DONE:
                _settle_effect(row, fx["key"])


def _apply_effect(row, fx):
    """One effect of an accepted verdict at its destination, its key written with it; _NOT_DONE when it did not happen
    (it stays on the row and is tried again)."""
    tgt = row.get("target") if isinstance(row.get("target"), dict) else {}
    dest, key, said = fx.get("dest"), fx["key"], []
    if dest == "valence":
        _nudge_valence(fx.get("amount", 0)); return True
    if dest == "outcome":
        try: return _record_outcome(tgt, fx, key)
        except Exception: return _NOT_DONE
    if dest == "pressure":
        def _press():
            from desired_difference import field_verdict as _ddfv
            return _ddfv(tgt, fx.get("verdict"), receipt=key)
        out = _guarded("field_verdict", _press, said, _NOT_DONE)
    elif dest == "required_consideration":
        out = _guarded("required_consideration.write", lambda: _require(tgt, key), said, _NOT_DONE)
    else:
        return _NOT_DONE
    return _NOT_DONE if any(f["result"] == "failed" for f in said) else out


def _require(tgt, key):
    """A miss on an addressed difference asks for it once more on the next turn. The marker carries the miss's key;
    a marker that goes leaves its key in desired_difference's receipts, so the miss is found in one or the other."""
    from desired_difference import _jload as _ddl2, PRESS as _ddP2, _turn_state as _tsl2, marker_consumed as _ddmc, marker_receipts as _ddmr
    _rcp = os.path.join(MEM, ".intent-required-consideration.json")
    with _tsl2(_rcp):   # the row is read and the marker written in one step, against a retire
        _m = _ddl2(_rcp, None)
        if (isinstance(_m, dict) and _m.get("effect_key") == key) or key in _ddmr():
            return True
        _row = _ddl2(_ddP2, {}).get(str(tgt["addresses"]))
        if _row and not _row.get("retired"):
            if isinstance(_m, dict): _ddmc(_m)          # the marker this one replaces was written: its key is kept
            with open(_rcp + ".tmp", "w") as _rcf:
                json.dump({"id": str(tgt["addresses"]), "weight": _row.get("weight", 0), "count": _row.get("count", 0),
                           "text": str(_row.get("text", ""))[:250], "effect_key": key}, _rcf)
            os.replace(_rcp + ".tmp", _rcp)
    return True


def _joined(path, key):
    """Is the outcome line with this key in the join already (its last MB)?"""
    try:
        with open(path, "rb") as f:
            f.seek(0, 2); f.seek(max(0, f.tell() - 1048576)); tail = f.read().decode("utf-8", "replace")
    except OSError:
        return False
    needle = json.dumps(key)
    for ln in tail.splitlines():
        if needle not in ln: continue
        try:
            if (json.loads(ln).get("detail") or {}).get("effect_key") == key: return True
        except Exception: pass
    return False


def _record_outcome(tgt, fx, key):
    """The outcome line carries its key; with the real join it is looked for under the join's lock first, and
    looked for again after, so a line that was not written is not taken for one that was."""
    import contextlib as _cl
    import outcome_join as _oj
    from store_guard import transaction
    joins = getattr(_oj, "JOINS", None)
    with (transaction(joins) if joins else _cl.nullcontext()):
        if joins and _joined(joins, key): return True
        _oj.record("intent", str(tgt.get("goal") or tgt.get("field_state", ""))[:120], copy.deepcopy(fx.get("verdict")),
                   dict(fx.get("detail") or {}, effect_key=key))
        if joins and not _joined(joins, key): return _NOT_DONE
    return True


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
