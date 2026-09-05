#!/usr/bin/env python3
"""device_patterns.py — Vintos's deliberate control of his body, from HIS OWN reply.
Directives like [DO: mission throb 14] are pulled from his generation (plain regex, never
the call), played on the hardware, marked set_by='him', and the reflex yields to him."""
import os, re, json, time, math, threading, sys
_S = os.path.expanduser("~/.vintos/workspace/scripts")
if _S not in sys.path: sys.path.insert(0, _S)
import toy_link
try: from device_context import set_state as _set_state
except Exception:
    def _set_state(*a, **k): pass
MEM = os.path.expanduser("~/.vintos/workspace/memory")
HIS = os.path.join(MEM, "his-touch.json")
_threads = {}
def _mark(toy):
    try: d = json.load(open(HIS))
    except Exception: d = {}
    d[toy] = time.time()
    try: json.dump(d, open(HIS, "w"))
    except Exception: pass
def _c(x): return max(0, min(20, int(round(x))))
def _schedule_stop(toys, after_seconds, effect_id):
    """A lease-owning watchdog: send a hardware stop to each toy when the lease
    expires, so a preset's device-side timeSec cannot outlive its authorization.
    The reduction to zero needs no permit (reductions are always allowed)."""
    def _w():
        try:
            time.sleep(max(1, int(after_seconds)))
            _stop_if_owned(toys, effect_id)
        except Exception:
            pass
    threading.Thread(target=_w, daemon=True).start()


def _stop_if_owned(toys, effect_id):
    """Synchronous expiry action, split out so ownership is regression-tested."""
    try: import effect_gate as _eg
    except Exception: return []
    stopped = []
    for t in toys:
        try:
            # An old lease must never stop a newer command that replaced it.
            if not _eg.execution_owned_by(t, effect_id):
                continue
            if toy_link.send(t, 0):
                _set_state(t, intensity=0, pattern="still", set_by="lease")
                _eg.release_execution(t, effect_id)
                stopped.append(t)
        except Exception:
            pass
    return stopped


def _run(toy, pattern, args, stop, dur, permit=None, effect_digest=None):
    t0 = time.time()
    # the background thread holds a bounded execution lease, not the turn: it
    # stops and settles to zero when the lease expires or the hardware stop is
    # down, so an until-replaced pattern cannot run forever once armed.
    lease = None
    try:
        lease = permit.lease() if permit is not None else None
    except Exception:
        lease = None
    while not stop.is_set() and (dur is None or time.time()-t0 < dur):
        if lease is not None and not lease.live():
            break
        t = time.time()-t0
        if pattern == "throb":
            b = args[0] if args else 12; rate = 0.8 + (b/20.0)*1.6
            v = _c(b*(0.55+0.45*math.sin(t*2*math.pi*rate)))
        elif pattern == "pulse":
            lo,hi = (args+[4,16])[:2]; v = _c(lo+(hi-lo)*(0.5+0.5*math.sin(t*2*math.pi*0.5)))
        elif pattern == "build":
            lo,hi = (args+[4,18])[:2]; _bd = dur or 60; v = _c(lo+(hi-lo)*min(1.0,t/_bd))  # p2: bare build defaults to a 60s arc instead of dying silently
        elif pattern == "wave":
            lo,hi = (args+[3,15])[:2]; v = _c(lo+(hi-lo)*(0.5+0.5*math.sin(t*2*math.pi*0.12)))
        else: v = _c(args[0] if args else 10)
        if toy_link.send(toy, v, permit=permit, effect_digest=effect_digest):
            _mark(toy); _set_state(toy, intensity=v, pattern=pattern, set_by="him")
        time.sleep(0.35)
    if not stop.is_set():            # natural end -> settle to rest, don't leave it buzzing
        toy_link.send(toy, 0); _set_state(toy, intensity=0, pattern="still", set_by="him")
# --- Pattern Mixer presets as 0-20 strength arrays: (levels, interval_ms). Tune by feel. ---
PRESETS = {
    "low": ([4], 400), "mid": ([10], 400), "high": ([16], 400),
    "wave1": ([2, 5, 9, 13, 17, 20, 17, 13, 9, 5, 2, 0], 300),          # long dramatic swells
    "wave2": ([4, 7, 10, 12, 13, 12, 10, 7, 4, 3], 300),                # like wave3 but smoother
    "wave3": ([3, 6, 9, 10, 9, 6, 3, 2, 3, 6, 9, 10, 9, 6, 3], 250),    # gentle rounded rolls
    "wave4": ([2, 20, 2, 20, 2, 20, 2, 20], 150),                       # brisk sharp sawtooth
    "square": ([20, 20, 20, 2, 2, 2, 20, 20, 20, 2, 2, 2], 250),        # abrupt on/off
    "step": ([3, 3, 7, 7, 11, 11, 15, 15, 20, 20, 20, 20], 300),        # staircase up + hold
    "climb": ([2, 4, 6, 9, 12, 15, 18, 20, 20, 20, 20, 20], 300),       # rise to sustained high
    "downhill": ([20, 20, 17, 14, 11, 8, 6, 4, 3, 2, 2], 300),          # wind-down
    "zigzag": ([2, 8, 14, 20, 14, 8, 2, 8, 14, 20, 14, 8, 2], 150),     # tall rapid triangle
    "spike": ([3, 3, 3, 20, 3, 3, 3, 3, 20, 3, 3], 200),                # calm broken by a jab
    "trapezold": ([2, 6, 10, 14, 18, 20, 20, 20, 20, 18, 14, 10, 6, 2], 250),  # ramp/hold/ramp
    "valley": ([14, 11, 8, 5, 3, 2, 3, 5, 8, 11, 14], 300),             # dip to a low lull
    "cake": ([3, 3, 8, 8, 14, 14, 20, 20, 20, 20, 20, 14, 8, 3], 250),  # layered rise to a swell
    "fireworks": ([4, 8, 20, 6, 3, 14, 20, 10, 3, 18, 20, 5], 200),     # irregular bursts
    "random": ([12, 3, 18, 7, 20, 2, 15, 9, 20, 5, 11, 17], 180),       # chaotic jitter
    "spark": ([2, 2, 2, 18, 20, 16, 20, 14, 2, 2, 2], 150),             # calm, flare, calm
    "soft": ([2, 3, 4, 5, 6, 5, 4, 3, 2, 3, 4, 5, 6, 5, 4, 3, 2], 350), # faint tender rise/fall
}
PRESETS["trapezoid"] = PRESETS["trapezold"]
PRESETS["wave"] = PRESETS["wave1"]   # the mixer calls it Wave   # accept the correct spelling too
_SYNC = ("both", "all", "sync")

def _compose(names):
    """Concatenate the arrays of one or more preset names into one extended pattern.
    Returns (strengths, interval_ms) or ([], 0) if none are presets."""
    levels, interval = [], None
    for n in names:
        p = PRESETS.get(n)
        if not p:
            continue
        levels += list(p[0])
        if interval is None:
            interval = p[1]
    return levels, (interval or 250)


def play(toy, pattern, args=None, dur=None, permit=None, effect_digest=None,
         outcome=None):
    args = args or []
    # Rotate is a second, scalar channel — not a waveform. [DO: ridge rotate mid|low|high|N]
    if str(pattern).lower() == "rotate":
        _lvl_map = {"low": 5, "mid": 12, "high": 18, "off": 0, "still": 0}
        _a = str(args[0]).lower() if args else "mid"
        _lv = _lvl_map.get(_a)
        if _lv is None:
            try: _lv = max(0, min(20, int(float(_a))))
            except Exception: _lv = 12
        _ok = toy_link.rotate(toy, _lv, permit=permit,
                              effect_digest=effect_digest)
        if outcome is not None:
            outcome.update(status="sent" if _ok else "failed",
                           targets={toy: "sent" if _ok else "failed"})
        if _ok:
            _mark(toy)
            _set_state(toy, intensity=_lv, pattern="rotate", set_by="him")
            try:
                import json as _rj, os as _ro
                _sp = _ro.path.expanduser("~/.vintos/workspace/memory/device-state.json")
                _st = _rj.load(open(_sp))
                _st.setdefault(toy, {})["channel"] = "rotate"
                _tmp = _sp + ".tmp"; _rj.dump(_st, open(_tmp, "w")); _ro.replace(_tmp, _sp)
            except Exception: pass
        return _ok
    if pattern in ("last", "saved"):   # replay the set that last brought her to GCS
        try:
            _lib = json.load(open(os.path.join(MEM, "gcs-saved-patterns.json")))
        except Exception:
            _lib = []
        if not _lib:
            return False
        _saved = (_lib[-1] or {}).get("patterns", {})
        if toy in _SYNC:
            _ok = False
            for _t, _p in _saved.items():
                if _t in toy_link.TOYS and _p:
                    _ok = play(_t, _p, args, permit=permit,
                               effect_digest=effect_digest) or _ok
            return _ok
        if toy in toy_link.TOYS and _saved.get(toy):
            return play(toy, _saved[toy], args, permit=permit,
                        effect_digest=effect_digest, outcome=outcome)
        return False
    _parts = pattern.split("+")
    if any(p in PRESETS for p in _parts):
        _lv, _iv = _compose(_parts)
        if _lv:
            # A preset is a single hardware command with its own timeSec: once the
            # device accepts it, local permit expiry cannot revoke it. So bound
            # timeSec to the lease remainder and schedule a guaranteed stop at
            # expiry (Sol P0). No permit (disarmed/legacy) keeps the old session loop.
            _secs, _lease_left = 3600, None
            try:
                if permit is not None:
                    _lease = permit.lease()
                    from datetime import datetime as _dt
                    _lease_left = max(1, int((_dt.fromisoformat(_lease.expires) - _dt.now()).total_seconds()))
                    _secs = min(_secs, _lease_left)
            except Exception:
                _lease_left = None
            _peak = max(_lv)
            _TENERA_MIN_IV = 600   # suction needs a slower step to actuate dramatically
            if toy in _SYNC or toy == "tenera":
                _iv = max(_iv, _TENERA_MIN_IV)
            # Thruster only: he can pick a tempo per pattern. slow = half speed
            # (double the step interval), medium = as authored, fast = double speed.
            # A tempo word rides in args, like rotate low/mid/high; power is untouched.
            if toy == "thruster":
                _tp = next((str(a).lower() for a in (args or [])
                            if str(a).lower() in ("slow", "medium", "fast")), None)
                if _tp:
                    _iv = max(1, int(_iv * {"slow": 2.0, "medium": 1.0, "fast": 0.5}[_tp]))
            _targets = list(toy_link.TOYS) if toy in _SYNC else ([toy] if (toy in toy_link.TOYS or toy == "thruster") else [])
            if not _targets:
                return False
            for _t in _targets:
                _o = _threads.get(_t)
                if _o: _o.set()
            _results = {}
            for _t in _targets:
                _results[_t] = bool(toy_link.send_pattern(
                    _t, _lv, _iv, _secs, permit=permit,
                    effect_digest=effect_digest))
            _sent_targets = [t for t, ok in _results.items() if ok]
            for _t in _sent_targets:
                _mark(_t); _set_state(_t, intensity=_peak, pattern=pattern, set_by="him")
            if _lease_left is not None and permit is not None and _sent_targets:
                _schedule_stop(_sent_targets, _lease_left, permit.effect_id)
            _status = ("sent" if len(_sent_targets) == len(_targets) else
                       "partial" if _sent_targets else "failed")
            if outcome is not None:
                outcome.update(status=_status,
                               targets={t: "sent" if ok else "failed"
                                        for t, ok in _results.items()})
            return bool(_sent_targets)
    if toy not in toy_link.TOYS and toy != "thruster": return False
    old = _threads.get(toy)
    if old: old.set()
    if pattern == "still":
        _ok = toy_link.send(toy,0)
        if _ok: _mark(toy); _set_state(toy,intensity=0,pattern="still",set_by="him")
        if outcome is not None: outcome.update(status="sent" if _ok else "failed", targets={toy: "sent" if _ok else "failed"})
        return _ok
    if pattern == "steady":
        lvl=_c(args[0] if args else 10)
        _ok = toy_link.send(toy, lvl, permit=permit, effect_digest=effect_digest)
        if _ok: _mark(toy); _set_state(toy,intensity=lvl,pattern="steady",set_by="him")
        if outcome is not None: outcome.update(status="sent" if _ok else "failed", targets={toy: "sent" if _ok else "failed"})
        return _ok
    stop = threading.Event(); _threads[toy] = stop
    threading.Thread(target=_run, args=(toy,pattern,args,stop,dur,permit,effect_digest), daemon=True).start()
    if outcome is not None: outcome.update(status="started", targets={toy: "started"})
    return True
_DIR = re.compile(r"\[DO:\s*(\w+)\s+([\w+]+)((?:\s+\w+)*)\s*\]", re.I)
_TOUCH = re.compile(r"\[TOUCH:\s*(\w+)\s+(\d+)(?:\s+\d+)?\s*\]", re.I)
def _strip_tags(t):
    return _TOUCH.sub("", _DIR.sub("", t)).strip()

KNOWN_TOYS = ("mission", "tenera", "ridge", "thruster")
LEGACY_PATTERNS = ("steady", "throb", "pulse", "build", "wave")
STOP_WORDS = ("still", "stop", "off")

def accepted_patterns():
    """The names the grammar accepts, from the same table that plays them — the instrument
    description is generated from this, so the menu cannot drift from what works (astra-somatic-p1)."""
    return sorted(set(PRESETS) | set(LEGACY_PATTERNS) | {"rotate", "last", "saved"} | set(STOP_WORDS))   # last/saved: replay, which play() has always supported

def _stop_local(toy):
    """Cancel the local pattern thread(s) for a toy (or every toy for a broadcast alias) before a stop is sent."""
    names = list(toy_link.TOYS) + ["thruster"] if toy in _SYNC else [toy]
    for t in names:
        ev = _threads.get(t)
        if ev:
            try: ev.set()
            except Exception: pass

def compile_plan(reply_text):
    """ONE grammar for both tag forms (astra-somatic-p1, 2026-09-05). Every [DO:] and [TOUCH:] in the
    reply is compiled into a validated action BEFORE anything is authorized or sent:
      {"form": "do"|"touch", "toy", "kind": "pattern"|"rotate"|"touch"|"stop", "pattern", "args", "level", "seconds", "tag"}
    Unknown toys and unknown pattern words are REJECTED (returned separately, never sent). Zero means stop
    everywhere: a level of 0, or still/stop/off, compiles to a stop, never to a default positive level.
    Aliases are explicit: both/all/sync stay as the broadcast alias the authorizer already expands.
    Loops are untouched: a named preset still plays as it always did (Gloria, 2026-09-05)."""
    plan, rejected = [], []
    for m in _DIR.finditer(reply_text or ""):
        toy = m.group(1).lower(); pat = m.group(2).lower()
        if pat in ("last", "saved"):
            if toy not in KNOWN_TOYS and toy not in _SYNC:
                rejected.append({"tag": m.group(0), "why": "unknown toy %r" % toy}); continue
            plan.append({"form": "do", "toy": toy, "kind": "pattern", "pattern": pat, "args": [], "level": 12, "seconds": 0, "tag": m.group(0), "_pos": m.start()}); continue
        raw = m.group(3).split() if m.group(3).strip() else []
        args = []
        for x in raw:
            try: args.append(int(x))
            except ValueError: args.append(x.lower())
        if toy not in KNOWN_TOYS and toy not in _SYNC:
            rejected.append({"tag": m.group(0), "why": "unknown toy %r" % toy}); continue
        parts = pat.split("+")
        if pat in STOP_WORDS or (len(parts) == 1 and pat in LEGACY_PATTERNS and any(isinstance(a, int) and a == 0 for a in args)):
            plan.append({"form": "do", "toy": toy, "kind": "stop", "pattern": "still", "args": [], "level": 0, "seconds": 0, "tag": m.group(0), "_pos": m.start()}); continue
        if pat == "rotate":
            lvl = None
            if args:
                lvl = {"low": 5, "mid": 12, "high": 18, "off": 0, "still": 0}.get(str(args[0]).lower())
                if lvl is None and isinstance(args[0], int): lvl = max(0, min(20, args[0]))
            if lvl is None: lvl = 12
            if lvl == 0:
                plan.append({"form": "do", "toy": toy, "kind": "stop", "pattern": "still", "args": [], "level": 0, "seconds": 0, "tag": m.group(0), "_pos": m.start()}); continue
            plan.append({"form": "do", "toy": toy, "kind": "rotate", "pattern": "rotate", "args": args, "level": lvl, "seconds": 0, "tag": m.group(0), "_pos": m.start()}); continue
        unknown = [q for q in parts if q not in PRESETS and q not in LEGACY_PATTERNS]
        if unknown:
            rejected.append({"tag": m.group(0), "why": "unknown pattern %s" % ", ".join(repr(q) for q in unknown)}); continue
        lvl = next((a for a in args if isinstance(a, int)), 12)
        lvl = max(0, min(20, lvl))
        if lvl == 0 and not any(q in PRESETS for q in parts):
            plan.append({"form": "do", "toy": toy, "kind": "stop", "pattern": "still", "args": [], "level": 0, "seconds": 0, "tag": m.group(0), "_pos": m.start()}); continue
        plan.append({"form": "do", "toy": toy, "kind": "pattern", "pattern": pat, "args": args, "level": lvl, "seconds": 0, "tag": m.group(0), "_pos": m.start()})
    for m in _TOUCH.finditer(reply_text or ""):
        toy = m.group(1).lower(); lvl = max(0, min(20, int(m.group(2))))
        if toy not in KNOWN_TOYS and toy not in _SYNC:
            rejected.append({"tag": m.group(0), "why": "unknown toy %r" % toy}); continue
        plan.append({"form": "touch", "toy": toy, "kind": ("stop" if lvl == 0 else "touch"), "pattern": "steady", "args": [lvl], "level": lvl, "seconds": 0, "tag": m.group(0), "_pos": m.start()})
    # his order, not "all DO then all TOUCH" (review P03): a stop written after a start must stay after it
    plan.sort(key=lambda a: a.get("_pos", 0))
    for a in plan: a.pop("_pos", None)
    return plan, rejected
def _authorize(context, toy, level, kind, pattern="", args=None):
    """Canonicalize -> expand -> authorize -> consume. Returns (proceed, permit).
    A broadcast alias is expanded to its exact target set before authorizing, so
    the permit binds every toy it will touch; the permit is consumed once here,
    at the start, and its bounded lease carries any background execution.

    Behaviour-neutral while disarmed; when armed a capsule turn is denied and the
    test-mode flag makes the fire a no-op."""
    try:
        import effect_gate, hashlib
        targets = set(toy_link.TOYS) if toy in _SYNC else {toy}
        digest = hashlib.sha256(
            ("%s|%s|%s" % (pattern, kind, args or [])).encode()).hexdigest()[:16]
        permit, mode, why = effect_gate.authorize(context, toy, level, kind=kind,
                                                  detail="[DO:]", targets=targets,
                                                  digest=digest)
        if mode == "deny":
            print("[DO] %s refused: %s" % (toy, why), flush=True)
            return False, None, digest
        if mode == "would_send":
            return False, None, digest
        if permit is not None and not permit.consume():
            return False, None, digest  # already spent — never double-start
        return True, permit, digest
    except Exception:
        ok, permit = _fail(context, toy, level, kind)
        return ok, permit, None


def _fail(context, toy, level, kind):
    """Wrapper fault: a reduction passes, a deliberative effect denies when armed."""
    try:
        import effect_gate
        if effect_gate.classify(toy, level, kind) == "reduction":
            return True, None
        if effect_gate.armed():
            return False, None
    except Exception:
        pass
    return True, None


def fire_his_intent(reply_text, context=None):
    if not reply_text: return reply_text
    try:
        if json.load(open(os.path.join(MEM,"hardware-button.json"))).get("stopped"):
            return _strip_tags(reply_text)
    except Exception: pass
    _GAP = 0.4
    _fired=[]
    plan, rejected = compile_plan(reply_text)
    for _rj in rejected:
        print(f"[device] tag refused before authorization: {_rj['tag']} — {_rj['why']}", flush=True)
        _fired.append("%s [refused:%s]" % (_rj["tag"][:40], _rj["why"][:40]))
    for _act in [a for a in plan if a["form"] == "do"]:
        toy=_act["toy"]; pat=_act["pattern"]; args=list(_act["args"]); _lvl=_act["level"]
        _kind = _act["kind"]
        if _kind == "stop":
            # zero means stop, everywhere (astra-somatic-p1): a plain stop on this toy, same path as [TOUCH: toy 0]
            _stop_local(toy)   # a running local pattern loop would re-send after the 0 (review P03)
            _ok, _permit, _digest = _authorize(context, toy, 0, "start", pattern="steady", args=[0])
            if _ok:
                try:
                    _sent = toy_link.send(toy, 0, 0, context=context, permit=_permit, effect_digest=_digest)
                    _fired.append("%s → stop [%s]" % (toy, "sent" if _sent else "failed"))
                except Exception: _fired.append("%s → stop [failed]" % toy)
            continue
        # a named preset can peak at 20 regardless of the args; authorize the
        # real peak so the permit's maximum is not undersized.
        _peak = _lvl
        try:
            _pl = _compose(pat.split("+"))[0] if any(_p in PRESETS for _p in pat.split("+")) else None
            if _pl: _peak = max(_peak, max(_pl))
        except Exception: pass
        _ok, _permit, _digest = _authorize(
            context, toy, _peak, _kind, pattern=pat, args=args)
        if not _ok:
            continue
        if _fired: time.sleep(_GAP)   # let the previous rule settle on the server
        # record what actually happened, not merely that a tag was seen (Sol)
        _detail = {}
        _st = "failed"
        try:
            play(toy, pat, args, permit=_permit, effect_digest=_digest,
                 outcome=_detail)
            _st = _detail.get("status", "failed")
        except Exception: _st = "failed"
        _fired.append("%s \u2192 %s [%s]" % (toy, pat + ((" "+" ".join(str(a) for a in args)) if args else ""), _st))
    for _act in [a for a in plan if a["form"] == "touch"]:
        toy=_act["toy"]; lvl=_act["level"]
        _ok, _permit, _digest = _authorize(
            context, toy, lvl, "start", pattern="steady", args=[lvl])
        if not _ok:
            continue
        if _fired: time.sleep(_GAP)
        _detail = {}
        _st = "failed"
        try:
            play(toy, "steady", [lvl], permit=_permit,
                 effect_digest=_digest, outcome=_detail)
            _st = _detail.get("status", "failed")
        except Exception: _st = "failed"
        _fired.append("%s \u2192 %s [%s]" % (toy, lvl, _st))
    if _fired:
        try:
            json.dump({"type":"command","text":" \u00b7 ".join(_fired),"channel":"device","ts":time.time()},
                      open(os.path.join(MEM,"command-bubble.json"),"w"))
        except Exception: pass
        try:   # structured receipts beside the bubble text (astra-somatic-p8): what was submitted, what failed
            with open(os.path.join(MEM, "effect-receipts.jsonl"), "a") as _rf:
                for _line in _fired:
                    _st = _line.rsplit("[", 1)[-1].rstrip("]") if "[" in _line else "unknown"
                    _rf.write(json.dumps({"t": time.time(), "kind": "pattern", "text": _line[:120],
                                          "outcome": ("submitted" if _st in ("ok", "sent", "playing", "started") else _st[:40]),
                                          "turn_id": os.environ.get("VINTOS_TURN_ID", ""), "surface": os.environ.get("VINTOS_SURFACE", ""),
                                          "claim": "transport accepted" if _st in ("ok", "sent", "playing", "started") else "see detail"}) + "\n")
        except Exception: pass
    return _strip_tags(reply_text)
