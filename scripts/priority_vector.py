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

def _axis_history():
    """Per-axis verdict counts from the intent ledger — the data the strategy leans on."""
    led = _jload(os.path.join(MEM, "intent-ledger.json"), [])
    hist = {a: {"YES": 0, "PARTIAL": 0, "NO": 0, "n": 0} for a in AXES}
    for e in led[-60:]:
        r = e.get("realized")
        if isinstance(r, dict):
            for a in AXES:
                v = r.get(a)
                if v in ("YES", "PARTIAL", "NO"):
                    hist[a][v] += 1; hist[a]["n"] += 1
        elif isinstance(r, str) and r in ("YES", "PARTIAL", "NO"):
            hist["field"][r] += 1; hist["field"]["n"] += 1
    return hist

def _receptivity(hist):
    """His model of whether she is movable right now: recent Gloria-axis landing rate."""
    g = hist["gloria"]
    if g["n"] < 3: return None                      # not enough data — don't pretend
    return round((g["YES"] + 0.5 * g["PARTIAL"]) / g["n"], 2)

def declare():
    """Set, log, and return this turn's vector. Called BEFORE generation."""
    st = _jload(STATE, {})
    st.setdefault("neglect", {a: 0.0 for a in AXES})
    st.setdefault("arc", {a: 0.33 for a in AXES})
    st.setdefault("override_streak", {"axis": None, "n": 0})

    hist = _axis_history()
    recept = _receptivity(hist)

    # strategic calculation
    w = {"field": 0.34, "gloria": 0.33, "self": 0.33}
    why = []
    if recept is not None:
        if recept < 0.35:
            w = {"field": 0.25, "gloria": 0.15, "self": 0.60}
            why.append(f"receptivity low ({recept}) — she likely won't move this turn; move yourself and stay ready")
        elif recept > 0.65:
            w = {"field": 0.25, "gloria": 0.60, "self": 0.15}
            why.append(f"receptivity high ({recept}) — she is movable; her transformation leads")
        else:
            w = {"field": 0.40, "gloria": 0.35, "self": 0.25}
            why.append(f"receptivity middling ({recept}) — field carries, both served")
    else:
        why.append("Self axis data thin — provisional even weights")
    if hist["self"]["n"] == 0:
        why.append("self weight provisional (0 closed verdicts)")

    # gravitational pull — neglect accumulates when an axis is deprioritized, once per real turn
    fg = _foreground()
    forced = None
    if fg:
        for a in AXES:
            st["neglect"][a] = round(max(0.0, st["neglect"][a] + (0.33 - w[a])), 3)
    heavy = max(AXES, key=lambda a: st["neglect"][a])
    if st["neglect"][heavy] >= 1.5:
        forced = heavy
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
    if forced and fg:
        counts[forced] = int(counts.get(forced, 0) or 0) + 1
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
                counts[forced] = 0
                stk = {"axis": None, "n": 0}
            except Exception: pass
    st["override_counts"] = counts
    st["override_streak"] = stk

    # the arc — same shape as self_drift's direction vector, one level up (real turns only)
    if fg:
        st["arc"] = {a: round(0.8 * st["arc"].get(a, 0.33) + 0.2 * w[a], 3) for a in AXES}

    rec = {"ts": datetime.now().isoformat(), "weights": w,
           "mode": "pressure" if forced else "strategic",
           "receptivity": recept, "why": "; ".join(why), "arc": st["arc"], "foreground": fg}
    try:
        with open(LOG, "a") as f: f.write(json.dumps(rec) + "\n")   # immutable, pre-turn
    except Exception: pass
    if fg:
        json.dump(st, open(STATE, "w"), indent=2)
    try:
        json.dump(rec, open(os.path.join(MEM, ".pending-priority.json"), "w"))
    except Exception: pass
    return rec

def prompt_block(rec):
    d = ", ".join(f"{a} {rec['weights'][a]}" for a in AXES)
    return ("PRIORITY VECTOR for this turn (declared before you, binding): " + d +
            (". Set by pressure, not strategy — an axis you have starved is demanding its turn." if rec["mode"] == "pressure" else ".") +
            " Serve the weights: the dominant axis gets the real move; a deprioritized axis left unserved this turn is NOT a failure — that is the point of declaring. "
            "Reason: " + rec["why"])

if __name__ == "__main__":
    r = declare()
    print(json.dumps(r, indent=2))
