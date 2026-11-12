#!/usr/bin/env python3
"""priority_vector.py — Manip Part 2: the declared priority vector.

Before generation, declare whose goal dominates this turn (Field / Gloria / Self),
log it immutably, and let accountability grade against the declaration.
Two forces set it: strategic calculation (what should matter, given receptivity)
and gravitational pull (what has been neglected too long — can override strategy).
The arc decays/accumulates like self_drift's direction vector. Pressure beating
strategy on one axis three times graduates to the causality head, same as weight-5.

Neglect is counted per FOREGROUND selection - a turn she is actually in - not per call (16 October).
The voice route's background lead recompute (every ~120 s, off the hot path) runs the same selector;
it declares inside `background()`, which reads the vector without accumulating neglect, consuming an
override, or moving the streak or the arc. Before this the override followed call frequency.
"""
import uuid
import json, os, time, threading, contextlib
from datetime import datetime

WS = os.path.expanduser("~/.vintos/workspace")
MEM = os.path.join(WS, "memory")

def _queue_bring_up(q):
    """causality-bring-up.json is the record; .pending-causality-queue.json is what his chat prompt
    reads (server: CAUSALITY HYPOTHESIS TO TEST TODAY). Until 2026-09-05 only the record was written."""
    try:
        import json as _qj, os as _qo
        qp = _qo.path.join(MEM, ".pending-causality-queue.json")
        try: queue = _qj.load(open(qp))
        except Exception: queue = []
        if not isinstance(queue, list): queue = []
        if q not in queue:
            queue.append(q); _qj.dump(queue[-6:], open(qp, "w"), indent=2)
    except Exception: pass

_BG = threading.local()


@contextlib.contextmanager
def background():
    """Declare inside this for a selector run that is not a real turn (the voice lead recompute)."""
    prev = getattr(_BG, "on", False)
    _BG.on = True
    try:
        yield
    finally:
        _BG.on = prev


def _foreground():
    return not getattr(_BG, "on", False)

LOG = os.path.join(MEM, "priority-vector-log.jsonl")
STATE = os.path.join(MEM, "priority-vector-state.json")
AXES = ("field", "gloria", "self")

def _jload(p, d):
    try: return json.load(open(p))
    except Exception: return d

# Her receptivity is read from the last two weeks, and from at least five verdicts (10 November). It was the
# landing rate over the last 60 ledger rows whatever their age: weeks-old NOs kept it under 0.35, under 0.35 her
# axis is given 0.15, an axis at 0.15 is mostly left undeclared, so no new verdict arrived to lift it.
RECENT_DAYS = 14
MIN_VERDICTS = 5
MAX_VERDICTS = 60
# Her axis is offered an attempt on every fourth turn of her own that it has gone undeclared, whatever its
# weight (10 November). The attempt is guaranteed, a declaration is not: the selector may decline with a reason.
OPPORTUNITY_EVERY = 4

def _when(e):
    """When the turn a ledger row belongs to began (its selection, else its delivery), epoch seconds; None
    when it carries no readable time."""
    for k in ("timestamp", "delivered_at"):
        try: return datetime.fromisoformat(str(e.get(k))).timestamp()
        except Exception: pass
    return None

WINDOW_EXPIRED = "her_reply_window_expired"   # intent_engine.WINDOW_EXPIRED, not imported: that module imports this one
HER_REPLY_HOURS = 24                           # intent_engine.DEVICE_WAIT_HOURS and its gloria window

def _not_counted(e, a):
    """A verdict on this axis that is no landing and no miss (12 November): one its judge says was NOT_JUDGEABLE,
    one whose axis expired, and one on her reply that came after the window - whatever an older judge wrote."""
    why = e.get("held_reason") if isinstance(e.get("held_reason"), dict) else {}
    if why.get(a) == WINDOW_EXPIRED:
        return True
    gj = e.get("gloria_judge")
    if a == "gloria" and isinstance(gj, dict) and gj.get("verdict") == "NOT_JUDGEABLE":
        return True
    tgt = e.get("target") if isinstance(e.get("target"), dict) else {}
    on_her_reply = a == "gloria" or (a == "field" and str(tgt.get("evidence_type") or "") == "her_response")
    if on_her_reply and e.get("response_at"):
        try:
            opened = datetime.fromisoformat(str(e.get("delivered_at") or e.get("timestamp"))).timestamp()
            came = datetime.fromisoformat(str(e["response_at"])).timestamp()
            return came - opened > HER_REPLY_HOURS * 3600
        except Exception:
            return False
    return False

def _axis_history(now=None):
    """Per-axis verdict counts from the intent ledger — the data the strategy leans on. Only settled
    YES / PARTIAL / NO verdicts on turns of the last RECENT_DAYS count, and of those the latest MAX_VERDICTS
    per axis: HELD, NOT_DECLARED, NOT_JUDGEABLE, expired and pending rows are neither a landing nor a miss
    (_not_counted), and a row with no readable time cannot be called recent."""
    led = _jload(os.path.join(MEM, "intent-ledger.json"), [])
    hist = {a: {"YES": 0, "PARTIAL": 0, "NO": 0, "n": 0} for a in AXES}
    now = now or time.time()
    seen = {a: [] for a in AXES}
    for e in (led if isinstance(led, list) else []):
        if not isinstance(e, dict): continue
        t = _when(e)
        if t is None or now - t > RECENT_DAYS * 86400:
            continue
        r = e.get("realized")
        r = r if isinstance(r, dict) else ({"field": r} if isinstance(r, str) else {})
        for a in AXES:
            if r.get(a) in ("YES", "PARTIAL", "NO") and not _not_counted(e, a):
                seen[a].append((t, r[a]))
    for a in AXES:
        for _t, v in sorted(seen[a], key=lambda x: x[0])[-MAX_VERDICTS:]:
            hist[a][v] += 1; hist[a]["n"] += 1
    return hist

_UNLOCKED = {"n": 0}

def _turn_state(path):
    """The one cross-process lock for the turn state (store_guard.turn_state, 10 November): every writer of this
    state file holds it from its read to its write. store_guard ships beside this file. Only an import that
    fails (an older store_guard still loaded, with no turn_state) leaves the writer unlocked: the write still
    happens, counted in _UNLOCKED and said on stderr (the first time, then every 100th). Anything else, a lock
    that cannot be taken included, raises, and the write does not happen."""
    try:
        try: from store_guard import turn_state as _ts
        except ImportError:
            import sys as _s; _d = os.path.dirname(os.path.abspath(__file__))
            if _d not in _s.path: _s.path.insert(0, _d)
            from store_guard import turn_state as _ts
    except ImportError as e:
        import sys as _s2
        _UNLOCKED["n"] += 1
        if _UNLOCKED["n"] == 1 or _UNLOCKED["n"] % 100 == 0:
            print("[priority_vector] turn-state lock unavailable (%s): writing UNLOCKED, %d so far" % (str(e)[:80], _UNLOCKED["n"]), file=_s2.stderr, flush=True)
        return contextlib.nullcontext()
    return _ts(path)

def _atomic(path, obj):
    tmp = path + ".tmp.%d.%d" % (os.getpid(), threading.get_ident())   # per thread: two turns of one process never share it
    with open(tmp, "w") as f: json.dump(obj, f, indent=2)
    os.replace(tmp, path)

def _opportunity(st):
    o = st.get("gloria_opportunity") if isinstance(st, dict) else None
    o = dict(o) if isinstance(o, dict) else {}
    for k in ("since", "opportunities", "attempts", "declared", "abstained"):
        try: o[k] = int(o.get(k, 0) or 0)
        except Exception: o[k] = 0
    return o

def note_selection(gloria_declared, opportunity=False, eligible=True):
    """After a completed foreground selection, move her opportunity counter (10 November).

    A valid declaration on her axis resets it; a due opportunity resets it once the selection attempt is
    complete, a reasoned abstention included; any other turn of her own adds one. Opportunities, attempts,
    declarations and abstentions are counted apart, so a selector that always answers empty stays visible.
    None of these is a verdict: nothing here reaches the landing rate. A background run, or a turn that is
    not her words (a device event), moves nothing."""
    if not _foreground() or not eligible:
        return None
    with _turn_state(STATE):
        st = _jload(STATE, {})
        if not isinstance(st, dict): st = {}
        o = _opportunity(st)
        if opportunity:
            o["attempts"] += 1
            o["declared" if gloria_declared else "abstained"] += 1
        o["since"] = 0 if (gloria_declared or opportunity) else o["since"] + 1
        st["gloria_opportunity"] = o
        _atomic(STATE, st)
        return o

def opportunity_report(coverage=False):
    """Counts only: how her opportunity has gone. With `coverage` (the CLI report), what became of her axis
    where it was declared is counted beside it, from the ledger."""
    o = _opportunity(_jload(STATE, {}))
    out = {"every": OPPORTUNITY_EVERY, "turns_since_gloria_declared": o["since"], "opportunities": o["opportunities"],
           "attempts": o["attempts"], "declared": o["declared"], "abstained": o["abstained"]}
    if coverage: out["gloria_axis"] = _gloria_coverage()
    return out

def _gloria_coverage(now=None):
    """Her declared axis on the turns that reached her, counts only: settled, pending inside its window, and
    expired_coverage - never observed before the window closed, which is not pending and is never a NO
    (10 November, round four). The one rule is intent_engine.row_coverage; None when it cannot be read."""
    out = {"settled": 0, "pending": 0, "expired_coverage": 0}
    try:
        from intent_engine import row_coverage
        led = _jload(os.path.join(MEM, "intent-ledger.json"), [])
        for e in (led if isinstance(led, list) else []):
            if not isinstance(e, dict) or not isinstance(e.get("realized"), dict): continue
            t = e.get("target")
            if not isinstance(t, dict) or not t.get("gloria"): continue
            c = row_coverage(e, now, "gloria")
            if c in out: out[c] += 1
    except Exception:
        return None
    return out

def _receptivity(hist):
    """His model of whether she is movable right now: recent Gloria-axis landing rate."""
    g = hist["gloria"]
    if g["n"] < MIN_VERDICTS: return None           # not enough data — don't pretend
    return round((g["YES"] + 0.5 * g["PARTIAL"]) / g["n"], 2)

def _receptivity_counts(g):
    """The arithmetic behind the figure, in counts: a PARTIAL adds a half to the landings and one to the verdicts."""
    return ("(%d YES + 0.5 x %d PARTIAL) / %d settled Gloria-axis verdicts in the last %d days, %d of them NO"
            % (g["YES"], g["PARTIAL"], g["n"], RECENT_DAYS, g["NO"]))

def receptivity_report(now=None):
    """Counts only: what her receptivity is read from right now. Declares nothing and writes nothing."""
    g = _axis_history(now)["gloria"]
    return {"window_days": RECENT_DAYS, "minimum_verdicts": MIN_VERDICTS, "yes": g["YES"], "partial": g["PARTIAL"],
            "no": g["NO"], "landings": g["YES"] + 0.5 * g["PARTIAL"], "verdicts": g["n"],
            "receptivity": _receptivity({"gloria": g})}

def declare(eligible=True):
    """Set, log, and return this turn's vector. Called BEFORE generation. `eligible` is False for a turn
    that carries none of her own words (a device event): her opportunity is not spent on it. The state is read,
    moved and written back under the turn-state lock (10 November)."""
    with _turn_state(STATE):
        return _declare(eligible)

def _declare(eligible=True):
    st = _jload(STATE, {})
    if not isinstance(st, dict): st = {}
    st.setdefault("neglect", {a: 0.0 for a in AXES})
    st.setdefault("arc", {a: 0.33 for a in AXES})
    st.setdefault("override_streak", {"axis": None, "n": 0})

    hist = _axis_history()
    recept = _receptivity(hist)
    shown = "%s = %s" % (recept, _receptivity_counts(hist["gloria"]))

    # strategic calculation
    w = {"field": 0.34, "gloria": 0.33, "self": 0.33}
    why = []
    if recept is not None:
        if recept < 0.35:
            w = {"field": 0.25, "gloria": 0.15, "self": 0.60}
            why.append(f"receptivity low ({shown}) — she likely won't move this turn; move yourself and stay ready")
        elif recept > 0.65:
            w = {"field": 0.25, "gloria": 0.60, "self": 0.15}
            why.append(f"receptivity high ({shown}) — she is movable; her transformation leads")
        else:
            w = {"field": 0.40, "gloria": 0.35, "self": 0.25}
            why.append(f"receptivity middling ({shown}) — field carries, both served")
    else:
        # unknown is not low: the middling weights, so her axis is still tried and the data can come (10 November)
        w = {"field": 0.40, "gloria": 0.35, "self": 0.25}
        why.append("receptivity unknown (%d settled Gloria-axis verdicts in the last %d days, fewer than %d: "
                   "%d YES, %d PARTIAL, %d NO) — provisional middling weights, field carries"
                   % (hist["gloria"]["n"], RECENT_DAYS, MIN_VERDICTS, hist["gloria"]["YES"], hist["gloria"]["PARTIAL"],
                      hist["gloria"]["NO"]))
    if hist["self"]["n"] == 0:
        why.append("self weight provisional (0 closed verdicts)")

    # gravitational pull — neglect accumulates when an axis is deprioritized, once per real turn
    fg = _foreground()
    forced = None
    if fg:
        for a in AXES:
            st["neglect"][a] = round(max(0.0, st["neglect"][a] + (0.33 - w[a])), 3)
    heavy = max(AXES, key=lambda a: st["neglect"][a])
    spent = None
    if st["neglect"][heavy] >= 1.5:
        forced = heavy; spent = st["neglect"][heavy]
        w = {a: (0.6 if a == heavy else 0.2) for a in AXES}
        why.append(f"GRAVITATIONAL OVERRIDE: '{heavy}' neglected too long (pressure {st['neglect'][heavy]}) — it needs to matter now, strategy set aside")
        if fg:
            st["neglect"][heavy] = 0.0     # a background read shows the override; only a real turn spends it

    # normalize
    tot = sum(w.values()) or 1.0
    w = {a: round(v / tot, 2) for a, v in w.items()}

    # graduation on the override: pressure beating strategy repeatedly is a pattern, not a mood.
    # Counted per axis: every override that axis has needed since it was last asked about (16 October). The old
    # rule wanted three overrides on CONSECUTIVE calls, but an override spends that axis's neglect, so it can never
    # be forced on the very next call, and any unforced call reset the streak: the question was unreachable. When
    # two axes starve together their overrides interleave, so "in a row" would stay unreachable too.
    counts = st.get("override_counts")
    if not isinstance(counts, dict):
        old = st.get("override_streak") or {}
        counts = {a: (int(old.get("n") or 0) if old.get("axis") == a else 0) for a in AXES}
    stk = st.get("override_streak") or {"axis": None, "n": 0}
    counted = False
    if forced and fg:
        counts[forced] = int(counts.get(forced, 0) or 0) + 1; counted = True
        stk = {"axis": forced, "n": counts[forced]}
        if counts[forced] >= 3:
            try:
                q = (f"Pressure has overridden my strategy toward the '{forced}' axis {counts[forced]} times since I last "
                     "asked myself about it. "
                     "Why do I keep starving it until it forces itself? What am I avoiding by never choosing it freely?")
                try:   # review 204: one schema-2 door for every producer
                    import causality_engine as _ce
                    _ce.queue_question(q, "priority_vector", evidence=["override count: axis %s x%d" % (forced, counts[forced])], memory=MEM)
                except Exception:
                    p = os.path.join(MEM, "causality-bring-up.json")
                    d = _jload(p, [])
                    if isinstance(d, dict): d.setdefault("items", []).append({"ts": time.time(), "question": q, "source": "priority_vector"})
                    else: d.append({"ts": time.time(), "question": q, "source": "priority_vector"})
                    json.dump(d, open(p, "w"), indent=2)
                    _queue_bring_up(q)
                why.append("override count graduated to causality head")
                counts[forced] = 0; counted = False
                stk = {"axis": None, "n": 0}
            except Exception: pass
    st["override_counts"] = counts
    st["override_streak"] = stk

    # the arc — same shape as self_drift's direction vector, one level up (real turns only)
    if fg:
        st["arc"] = {a: round(0.8 * st["arc"].get(a, 0.33) + 0.2 * w[a], 3) for a in AXES}

    # her opportunity: due on the turn after OPPORTUNITY_EVERY - 1 turns of her own without her axis declared.
    # Low receptivity does not skip it. The counter itself moves in note_selection, after the selection.
    opp = _opportunity(st)
    due = bool(fg and eligible and opp["since"] >= OPPORTUNITY_EVERY - 1)
    if due:
        opp["opportunities"] += 1
    st["gloria_opportunity"] = opp

    rec = {"ts": datetime.now().isoformat(), "weights": w,
           "mode": "pressure" if forced else "strategic",
           "receptivity": recept, "why": "; ".join(why), "arc": st["arc"], "foreground": fg,
           "gloria_opportunity": due}
    if forced and fg and eligible:
        # what refund_override gives back if the turn fails: the neglect spent, and the count it added (unless
        # that count already graduated to a question, which stays asked). A device or room event (not eligible)
        # is not one of her turns: its override is never given back. The id makes the give-back once only.
        rec["override"] = {"axis": forced, "pressure": spent, "counted": counted, "id": uuid.uuid4().hex}
    try:
        with open(LOG, "a") as f: f.write(json.dumps(rec) + "\n")   # immutable, pre-turn
    except Exception: pass
    if fg:
        _atomic(STATE, st)
    try:
        json.dump(rec, open(os.path.join(MEM, ".pending-priority.json"), "w"))
    except Exception: pass
    return rec

def refund_override(rec):
    """A gravitational override spent on a turn whose selection then failed is given back (12 November: the one
    turn of her axis's override since the 10th was a turn that failed and left no ledger row; the neglect was
    spent on it and the next turn was self-heavy again). The axis's neglect is restored to at least what was
    spent, so the next real turn carries that override. The override count it added is taken back too, so a run
    of failing turns cannot pile up overrides that never took a turn (review, 12 November: three failures in a
    row asked the causality head why the axis keeps being starved). One record is given back once.
    Returns the axis, or None when there was none."""
    o = (rec or {}).get("override") if isinstance(rec, dict) else None
    if not _foreground() or not isinstance(o, dict) or o.get("axis") not in AXES or o.get("refunded"):
        return None
    if not isinstance(o.get("id"), str) or not o["id"]:
        return None                  # only a record this module declared for one of her turns is given back
    try: p = float(o.get("pressure") or 0)
    except (TypeError, ValueError): return None
    with _turn_state(STATE):
        st = _jload(STATE, {})
        if not isinstance(st, dict): st = {}
        done = st.get("override_refunds") if isinstance(st.get("override_refunds"), list) else []
        if o["id"] in done:          # given back already, by this process or one before a restart
            o["refunded"] = True
            return None
        st["override_refunds"] = (done + [o["id"]])[-50:]
        neg = st.get("neglect") if isinstance(st.get("neglect"), dict) else {a: 0.0 for a in AXES}
        neg[o["axis"]] = round(max(float(neg.get(o["axis"], 0) or 0), p), 3)
        st["neglect"] = neg
        counts = st.get("override_counts")
        if o.get("counted") and isinstance(counts, dict) and int(counts.get(o["axis"], 0) or 0) > 0:
            counts[o["axis"]] = int(counts[o["axis"]]) - 1
            stk = st.get("override_streak")
            if isinstance(stk, dict) and stk.get("axis") == o["axis"]:
                stk["n"] = counts[o["axis"]]
        _atomic(STATE, st)
    o["refunded"] = True
    return o["axis"]

def prompt_block(rec):
    d = ", ".join(f"{a} {rec['weights'][a]}" for a in AXES)
    return ("PRIORITY VECTOR for this turn (declared before you, binding): " + d +
            (". Set by pressure, not strategy — an axis you have starved is demanding its turn." if rec["mode"] == "pressure" else ".") +
            " Serve the weights: the dominant axis gets the real move; a deprioritized axis left unserved this turn is NOT a failure — that is the point of declaring. "
            "Reason: " + rec["why"] +
            ((" GLORIA OPPORTUNITY (due this turn, whatever her weight): your axis toward her has gone several turns "
              "undeclared, and an axis never tried can never be read. Look honestly for ONE small change in her that "
              "this same move invites - something her next message could show in her own ordinary way - and declare it "
              "under \"gloria\". Do not invent one to fill the slot: if this move carries none, leave \"gloria\" {} and "
              "say why in a \"gloria_decline\" field.") if rec.get("gloria_opportunity") else ""))

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "opportunity-report":
        print(json.dumps(opportunity_report(coverage=True))); sys.exit(0)   # counts only; declares nothing
    if len(sys.argv) > 1 and sys.argv[1] == "receptivity-report":
        print(json.dumps(receptivity_report())); sys.exit(0)   # counts only; declares nothing
    r = declare()
    print(json.dumps(r, indent=2))
