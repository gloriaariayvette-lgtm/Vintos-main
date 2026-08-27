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
def _run(toy, pattern, args, stop, dur):
    t0 = time.time()
    while not stop.is_set() and (dur is None or time.time()-t0 < dur):
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
        toy_link.send(toy, v); _mark(toy); _set_state(toy, intensity=v, pattern=pattern, set_by="him")
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


def play(toy, pattern, args=None, dur=None):
    args = args or []
    # Rotate is a second, scalar channel — not a waveform. [DO: ridge rotate mid|low|high|N]
    if str(pattern).lower() == "rotate":
        _lvl_map = {"low": 5, "mid": 12, "high": 18, "off": 0, "still": 0}
        _a = str(args[0]).lower() if args else "mid"
        _lv = _lvl_map.get(_a)
        if _lv is None:
            try: _lv = max(0, min(20, int(float(_a))))
            except Exception: _lv = 12
        _ok = toy_link.rotate(toy, _lv)
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
                    _ok = play(_t, _p, args) or _ok
            return _ok
        if toy in toy_link.TOYS and _saved.get(toy):
            return play(toy, _saved[toy], args)
        return False
    _parts = pattern.split("+")
    if any(p in PRESETS for p in _parts):
        _lv, _iv = _compose(_parts)
        if _lv:
            _secs = 3600            # always loop for the session; a number in his tag no longer truncates the figure
            _peak = max(_lv)
            _TENERA_MIN_IV = 600   # suction needs a slower step to actuate dramatically
            if toy in _SYNC or toy == "tenera":
                _iv = max(_iv, _TENERA_MIN_IV)
            if toy in _SYNC:
                for _t in toy_link.TOYS:
                    _o = _threads.get(_t)
                    if _o: _o.set()
                for _t in toy_link.TOYS:
                    toy_link.send_pattern(_t, _lv, _iv, _secs)   # per-toy targeted; broadcast didn't drive Tenera dramatically
                for _t in toy_link.TOYS:
                    _mark(_t); _set_state(_t, intensity=_peak, pattern=pattern, set_by="him")
                return True
            if toy in toy_link.TOYS or toy == "thruster":
                _o = _threads.get(toy)
                if _o: _o.set()
                toy_link.send_pattern(toy, _lv, _iv, _secs)
                _mark(toy); _set_state(toy, intensity=_peak, pattern=pattern, set_by="him")
                return True
            return False
    if toy not in toy_link.TOYS and toy != "thruster": return False
    old = _threads.get(toy)
    if old: old.set()
    if pattern == "still":
        toy_link.send(toy,0); _mark(toy); _set_state(toy,intensity=0,pattern="still",set_by="him"); return True
    if pattern == "steady":
        lvl=_c(args[0] if args else 10); toy_link.send(toy,lvl); _mark(toy); _set_state(toy,intensity=lvl,pattern="steady",set_by="him"); return True
    stop = threading.Event(); _threads[toy] = stop
    threading.Thread(target=_run, args=(toy,pattern,args,stop,dur), daemon=True).start()
    return True
_DIR = re.compile(r"\[DO:\s*(\w+)\s+([\w+]+)((?:\s+\w+)*)\s*\]", re.I)
_TOUCH = re.compile(r"\[TOUCH:\s*(\w+)\s+(\d+)(?:\s+\d+)?\s*\]", re.I)
def _strip_tags(t):
    return _TOUCH.sub("", _DIR.sub("", t)).strip()
def fire_his_intent(reply_text):
    if not reply_text: return reply_text
    try:
        if json.load(open(os.path.join(MEM,"hardware-button.json"))).get("stopped"):
            return _strip_tags(reply_text)
    except Exception: pass
    _GAP = 0.4
    _fired=[]
    for m in _DIR.finditer(reply_text):
        toy=m.group(1).lower(); pat=m.group(2).lower()
        _raw_args = m.group(3).split() if m.group(3).strip() else []
        args = []
        for _x in _raw_args:
            try: args.append(int(_x))
            except ValueError: args.append(_x)   # words like low/mid/high are valid for rotate
        if _fired: time.sleep(_GAP)   # let the previous rule settle on the server
        try: play(toy, pat, args)
        except Exception: pass
        _fired.append(toy+" \u2192 "+pat+((" "+" ".join(str(a) for a in args)) if args else ""))
    for m in _TOUCH.finditer(reply_text):
        toy=m.group(1).lower(); lvl=int(m.group(2))
        if _fired: time.sleep(_GAP)
        try: play(toy, "steady", [lvl])
        except Exception: pass
        _fired.append(toy+" \u2192 "+str(lvl))
    if _fired:
        try:
            json.dump({"type":"command","text":" \u00b7 ".join(_fired),"channel":"device","ts":time.time()},
                      open(os.path.join(MEM,"command-bubble.json"),"w"))
        except Exception: pass
    return _strip_tags(reply_text)
