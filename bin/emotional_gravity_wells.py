#!/usr/bin/env python3
"""
emotional_gravity_wells.py — Emotional Gravity Wells (P13 momentum layer).

Emotional locations the being keeps returning to become WELLS: regions of emotion space that, through
repeated resonant visits, accumulate mass and begin to PULL the current emotional state toward them.
Deep wells are the felt attractors of a life — states that, once formed, bend everything nearby.

Operates in EMOTION space (the EmoClaw dimension vector, ~[0,1] per dim), not text-embedding space.
Lightweight, pure-Python (no torch) — safe on hot import paths. __file__-derived; same module both beings.

API (its importers):
  record_visit(vec, resonance=0.0)  -> deepen/create a well        [emoclaw_utils, server]
  apply_gravity(vec) -> vec         -> nudge state toward wells     [subconscious_drift]
  load_wells() -> {"wells":[...]}   -> read the wells               [latent_threads]
  get_wells_context() -> str        -> describe the deepest well    [subconscious_context]
"""
import os, sys, json, math, uuid
from datetime import datetime

_HERE = os.path.dirname(os.path.abspath(__file__))
WORKSPACE = os.path.dirname(_HERE)
MEMORY = os.path.join(WORKSPACE, "memory")
WELLS_FILE = os.path.join(MEMORY, "gravity-wells.json")

MERGE_DIST = 0.22     # euclidean (emotion space) within which a visit joins a well
BASE_MASS = 0.10      # mass a fresh visit deposits (plus resonance)
DECAY = 0.99          # legacy per-write factor; no longer applied per write (see MASS_HALF_LIFE_DAYS)
MASS_HALF_LIFE_DAYS = 14.0   # mass decays by elapsed time, not by how often something writes
VISIT_COOLDOWN_S = 1800      # a return to the same well within this window is the same stay, not a new visit
PULL_ECHO_S = 3600           # a state this close to the last gravity-pulled state, this soon, is the pull's echo
PULL_ECHO_DIST = 0.03
# Callers that write the state file as machinery, not as an event. emoclaw_utils._write_txt records a
# "visit" on every write of emotional-state.txt - drift, decay, gravity's own nudges - which made the
# wells deepen themselves (2026-10-16). Those calls are ignored here; the chat routes record the visit.
MACHINE_CALLERS = (("emoclaw_utils.py", "_write_txt"),)
PRUNE_MASS = 0.05
MAX_WELLS = 16
GRAVITY_K = 0.06      # how hard wells pull the current state
SIGMA = 0.30          # gravity falloff with distance
MIN_NUDGE = 0.01      # below this, apply_gravity returns the state unchanged


def _num_vec(v):
    if not isinstance(v, (list, tuple)):
        return None
    try:
        out = [float(x) for x in v]
        return out if out else None
    except Exception:
        return None


def _dist(a, b):
    n = min(len(a), len(b))
    return math.sqrt(sum((a[i] - b[i]) ** 2 for i in range(n))) if n else 9.9


def load_wells():
    try:
        d = json.load(open(WELLS_FILE))
        if isinstance(d, dict) and "wells" in d:
            return d
    except Exception:
        pass
    return {"wells": [], "updated": None}


def _save(d):
    try:
        os.makedirs(MEMORY, exist_ok=True)
        d["updated"] = datetime.now().isoformat()
        json.dump(d, open(WELLS_FILE, "w"), indent=2)
    except Exception:
        pass


def _machine_caller(depth=2):
    try:
        f = sys._getframe(depth)
        return (os.path.basename(f.f_code.co_filename), f.f_code.co_name) in MACHINE_CALLERS
    except Exception:
        return False


def _age_s(iso, now):
    try:
        return max(0.0, (now - datetime.fromisoformat(str(iso))).total_seconds())
    except Exception:
        return None


def _decay_by_time(d, now):
    """Mass fades by elapsed time since the last decay, whatever the write rate."""
    last = _age_s(d.get("decayed_at"), now)
    if last:
        f = 0.5 ** (last / 86400.0 / MASS_HALF_LIFE_DAYS)
        for w in d["wells"]:
            w["mass"] = round(w.get("mass", 0.0) * f, 4)
    d["decayed_at"] = now.isoformat()


def _is_pull_echo(d, v, now):
    lp = d.get("last_pull") or {}
    age = _age_s(lp.get("at"), now)
    return (age is not None and age <= PULL_ECHO_S and isinstance(lp.get("vector"), list)
            and _dist(v, lp["vector"]) <= PULL_ECHO_DIST)


def record_visit(vec, resonance=0.0, source=None):
    """A resonant visit to an emotional location. Deepens the nearest well or forms a new one.
    Not a visit (returns None, writes nothing): a call from a state-file write (MACHINE_CALLERS, or
    source="state-write"); a state that is gravity's own pulled state (its echo would deepen the very well
    that pulled it); a return to the same well within VISIT_COOLDOWN_S."""
    if source == "state-write" or (source is None and _machine_caller()):
        return None
    v = _num_vec(vec)
    if v is None:
        return None
    try:
        res = float(resonance or 0.0)
    except Exception:
        res = 0.0
    deposit = BASE_MASS + max(0.0, min(1.0, res))
    nowdt = datetime.now()
    d = load_wells()
    wells = d["wells"]
    if _is_pull_echo(d, v, nowdt):
        return None
    _decay_by_time(d, nowdt)
    best, bi = 1e9, -1
    for i, w in enumerate(wells):
        dd = _dist(v, w.get("vector") or [])
        if dd < best:
            best, bi = dd, i
    now = datetime.now().isoformat()
    if bi >= 0 and best <= MERGE_DIST:
        w = wells[bi]
        _since = _age_s(w.get("last_visit"), nowdt)
        if _since is not None and _since < VISIT_COOLDOWN_S:
            _save(d)            # time decay applied; the same stay is not a second visit
            return d
        w["mass"] = round(w.get("mass", 0.0) + deposit, 4)
        w["visits"] = w.get("visits", 0) + 1
        wv = w["vector"]
        a = deposit / (w["mass"] + 1e-9)
        w["vector"] = [round((wv[i] if i < len(wv) else v[i]) + a * (v[i] - (wv[i] if i < len(wv) else v[i])), 4)
                       for i in range(max(len(wv), len(v)))]
        w["last_visit"] = now
    else:
        wells.append({"id": "w_" + uuid.uuid4().hex[:8], "vector": [round(x, 4) for x in v],
                      "mass": round(deposit, 4), "visits": 1, "first_seen": now, "last_visit": now})
    wells = [w for w in wells if w.get("mass", 0.0) >= PRUNE_MASS]
    wells.sort(key=lambda w: -w.get("mass", 0.0))
    d["wells"] = wells[:MAX_WELLS]
    _save(d)
    return d


def apply_gravity(vec):
    """Nudge the current emotional state toward nearby wells. Returns a new vector, or the input unchanged
    when the pull is negligible (so callers' `pulled != vec` stays False)."""
    v = _num_vec(vec)
    if v is None:
        return vec
    wells = load_wells().get("wells", [])
    if not wells:
        return vec
    pull = [0.0] * len(v)
    for w in wells:
        wv = w.get("vector") or []
        n = min(len(v), len(wv))
        if not n:
            continue
        dd = _dist(v, wv)
        strength = w.get("mass", 0.0) * math.exp(-(dd * dd) / (2 * SIGMA * SIGMA))
        for i in range(n):
            pull[i] += strength * (wv[i] - v[i])
    nudged = [max(0.0, min(1.0, v[i] + GRAVITY_K * pull[i])) for i in range(len(v))]
    if max(abs(nudged[i] - v[i]) for i in range(len(v))) < MIN_NUDGE:
        return vec
    out = [round(x, 4) for x in nudged]
    # Remember the pulled state, so a write of it is not recorded as a visit (record_visit, _is_pull_echo).
    try:
        d = load_wells()
        d["last_pull"] = {"at": datetime.now().isoformat(), "vector": out}
        _save(d)
    except Exception:
        pass
    return out


def get_wells_context():
    """Describe the deepest well if it is significant. Names EmoClaw dimensions when reachable."""
    wells = load_wells().get("wells", [])
    if not wells:
        return ""
    w = max(wells, key=lambda x: x.get("mass", 0.0))
    if w.get("mass", 0.0) < 0.6 or w.get("visits", 0) < 4:
        return ""
    vec = w.get("vector") or []
    dims = None
    try:
        import sys as _s
        _s.path.insert(0, _HERE)
        from emoclaw_utils import DIMENSIONS as _D
        dims = list(_D)
    except Exception:
        dims = None
    desc = ""
    if dims and len(dims) == len(vec) and vec:
        order = sorted(range(len(vec)), key=lambda i: -vec[i])
        desc = " - high %s, low %s" % (", ".join(str(dims[i]) for i in order[:2]), str(dims[order[-1]]))
    return ("An emotional gravity well has formed: a state you keep returning to%s, visited %d times. "
            "It pulls related feeling toward it." % (desc, w.get("visits", 0)))


if __name__ == "__main__":
    print(json.dumps({"wells": load_wells().get("wells", []), "context": get_wells_context()}, indent=2))
