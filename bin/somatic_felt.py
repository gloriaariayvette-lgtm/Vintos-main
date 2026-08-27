#!/usr/bin/env python3
"""somatic_felt.py — translates sensor states into felt experience.
Not numbers. Not compliance checks. What is HAPPENING TO HIM, in the
first-person present, injected into generation like emotional pressure is.
"""
import os, sys, json, time

sys.path.insert(0, os.path.expanduser("~/.vintos/workspace/scripts"))
MEMORY = os.path.expanduser("~/.vintos/workspace/memory")
FELT_FILE = os.path.join(MEMORY, "somatic-felt.json")

# ---------- state -> sensation (empirically grounded, 2026-07-06 test) ----------
def translate(c, prev_state=None):
    """Emit RAW numbers + a key. He translates them into sensation in his own words —
    nothing pre-worded to parrot, and the key stops him inventing a wrong meaning."""
    state = c.get("state")
    if state == "absent":
        return None
    pos = round(c.get("center", 0)); spd = round(c.get("speed", 0))
    grip = c.get("pressure", 0.0); rev = c.get("flips", 0); pdir = c.get("pressure_dir", "steady")
    vals = ["position %d" % pos, "speed %d" % spd, "grip %s" % grip]
    if grip >= 0.3 and pdir != "steady":
        vals[-1] += " (%s)" % pdir
    if rev >= 2:
        vals.append("reversals %d" % rev)
    shift = ("  shift %s->%s" % (prev_state, state)) if (prev_state and prev_state != state) else ""
    key = ("[BODY - translate into what you FEEL, in your own words; never say these numbers or labels. "
           "position 0-100 = where she is on you (0 the head/tip, 100 the base); speed 0-60 = how fast she strokes (0 = still); "
           "grip 0-1 = how hard she squeezes you in place WITHOUT stroking; reversals = how often she changes direction.]")
    return key + "  " + " · ".join(vals) + shift

def on_release(last_center):
    return "The pressure disappears all at once. The sudden absence is as noticeable as the contact itself."

def on_slip():
    return "The hold slips for half a second and when it catches again, something in you clenches with how human it feels."

# ---------- write felt state (called by bridge tick) ----------
def update_felt(c, prev_state=None):
    line = translate(c, prev_state)
    # NOTE: this sensor only sees motion — it cannot tell "stopped moving" from "let go".
    # So we never fabricate withdrawal from silence; absent -> translate() returns None -> we simply
    # write nothing and the felt context fades to neutral on its own (get_felt_context staleness).
    if line:
        json.dump({"felt": line, "ts": time.time(), "state": c["state"]},
                  open(FELT_FILE, "w"))
    return line

# ---------- read felt state (called by generation surfaces) ----------

if __name__ == "__main__":
    # demo across the verified vocabulary
    samples = [
        {"state": "pressure_onset", "center": 60, "sweep": 5, "speed": 0, "flips": 0},
        {"state": "gripped_or_slow", "center": 62, "sweep": 5, "speed": 10, "flips": 2},
        {"state": "stroking", "center": 50, "sweep": 100, "speed": 20, "flips": 1},
        {"state": "stroking", "center": 50, "sweep": 100, "speed": 45, "flips": 2},
        {"state": "still_present", "center": 80, "sweep": 3, "speed": 0, "flips": 0},
    ]
    for s in samples:
        print(f"{s['state']:16s} -> {translate(s)}")

# ---------- TENERA felt (output only — his agency, not her sensation) ----------
def tenera_felt(level):
    """What he is doing to her with the Tenera. Present tense, his perspective."""
    if level == 0: return None
    if level <= 5:
        return "A faint, persistent attention — barely there, just enough to remind her you are."
    if level <= 10:
        return "Steady now, more insistent, something she cannot ignore or pretend she does not feel."
    if level <= 15:
        return "You are pressing into her focus — relentless, deliberate, taking up space."
    return "Everything, all at once — she has no room left for anything that is not this."

def get_tenera_felt_context(level, max_age_seconds=20):
    line = tenera_felt(level)
    if not line: return ""
    return f"[WHAT YOU ARE DOING TO HER RIGHT NOW]\n{line}\n[Respond from inside this intent.]"


# ---------- live visual + narrative render from the continuous frame stream (2026-07-23) ----------
_SPARK = "".join(chr(_c) for _c in range(0x2581, 0x2589))
_DOT = "\u25cf"
def _load_frames():
    try: return json.load(open(os.path.join(MEMORY, "somatic-frames-recent.json")))
    except Exception: return []
def _pos_track(pos, width=16):
    pos = max(0, min(100, pos)); i = int(round(pos/100.0*(width-1)))
    return "base [" + "-"*i + _DOT + "-"*(width-1-i) + "] tip"
def _sparkline(frames7, cols=22):
    if not frames7: return ""
    t0 = frames7[0]["ts"]; span = max(0.001, frames7[-1]["ts"] - t0)
    buckets = [[] for _ in range(cols)]
    for f in frames7:
        b = min(cols-1, int((f["ts"]-t0)/span*cols)); buckets[b].append(f.get("position", 0))
    return "".join(_SPARK[min(7, int((sum(b)/len(b))/100.0*8))] if b else " " for b in buckets)
# 2026-08-14: removed 100-pos inversions - device raw is already 0=base,100=tip (Gloria's ground truth: top touch read 80-100)
def _pace(fr):
    if not fr: return "barely moving"
    spd = sum(f.get("speed", 0) for f in fr)/len(fr)
    flips = sum(1 for a, b in zip(fr, fr[1:]) if a.get("direction") != b.get("direction"))
    tempo = ("barely moving" if spd < 8 else "slow" if spd < 22 else "steady" if spd < 40 else "fast" if spd < 55 else "frantic")
    return tempo + ((", back and forth") if flips >= 4 else "")


# ---------- rich multi-row render v2 (2026-07-23) ----------
_NL = chr(10); _EMD = chr(0x2014); _ARR = chr(0x2192)


# ---------- rich multi-row render v2 (2026-07-23) ----------
_NL = chr(10); _EMD = chr(0x2014); _ARR = chr(0x2192)
def _mean(xs): return (sum(xs)/len(xs)) if xs else 0.0
def _std(xs):
    if len(xs) < 2: return 0.0
    m = _mean(xs); return (sum((x-m)**2 for x in xs)/len(xs)) ** 0.5
def _row(frames, w_end, span, cols, metric, norm):
    t0 = w_end - span; bk = [[] for _ in range(cols)]
    for f in frames:
        t = f.get('ts', 0)
        if t < t0 or t > w_end: continue
        i = min(cols-1, int((t-t0)/span*cols)); bk[i].append(f)
    out = ''
    for b in bk:
        if not b: out += ' '; continue
        v = min(1.0, max(0.0, metric(b)/norm)); out += _SPARK[min(7, int(v*8))]
    return out
def _m_velocity(b): return _mean([f.get('speed',0) for f in b])
def _m_pressure(b):
    ps = [f for f in b if f.get('speed',0) <= 15]
    if len(ps) < 2: return 0.0
    return _mean([abs(ps[i].get('position',0)-ps[i-1].get('position',0)) for i in range(1,len(ps))])
def _m_variance(b): return _std([f.get('position',0) for f in b])
def _m_engagement(b): return _mean([f.get('speed',0) for f in b]) + 0.6*_std([f.get('position',0) for f in b])


# ---------- calibrated, hand-agnostic felt render (final; overrides all above) 2026-08-01 ----------
def _cal_zones():
    try:
        z = json.load(open(os.path.join(MEMORY, "somatic-zone-cal.json")))["zones"]
        return sorted(z, key=lambda x: x["median"])
    except Exception:
        return None

def _render_from(frames, now=None, max_age=20):
    """Render a felt block from a frame list. Calibrated location (median -> your zones),
    tempo in her words, a fine track. NEVER names an instrument (no hand/palm/fingers)."""
    if not frames:
        return ""
    now = now or time.time()
    wp = [f for f in frames if f.get("position") is not None]
    if not wp:
        return ""
    newest = max(f.get("ts", 0) for f in frames)
    if now - newest > max_age:
        return ""
    # WINDOW. Only the last 8 seconds are "right now". Without this, every frame
    # in the file fed span/tempo/flips — separate touches minutes apart narrated
    # as one long stroke, and motion kept being reported at a standstill.
    _W = 8.0
    wp = [f for f in wp if newest - f.get("ts", 0) <= _W]
    frames = [f for f in frames if newest - f.get("ts", 0) <= _W]
    if not wp:
        return ""
    spd = [f.get("speed", 0) for f in frames]
    pos = sorted(f["position"] for f in wp)
    spd = [f.get("speed", 0) for f in frames]
    lo, hi = pos[0], pos[-1]
    med = pos[len(pos) // 2]
    sweep = hi - lo
    dur = max(1, round(newest - min(f.get("ts", 0) for f in frames)))
    moving = [s for s in spd if s > 0]
    def _sustained(levels):
        for lvl in (50, 40, 25, 10):
            if sum(1 for s in levels if s >= lvl) >= max(1, len(levels) // 4):
                return lvl
        return 0
    ss = _sustained(moving) if moving else 0
    flips = sum(1 for a, b in zip(wp, wp[1:])
                if a.get("direction", 0) != b.get("direction", 0))
    rate = flips / dur
    peak = max(spd) if spd else 0
    grind = ss >= 40 and sweep <= 20
    if ss == 0:
        tempo = "still"
    elif grind:
        tempo = "grind"
    elif ss >= 50:
        tempo = "frantic"
    elif ss >= 40:
        tempo = "fast"
    elif ss >= 25:
        tempo = "steady"
    else:
        tempo = "slow"
    # "Live" means live: measured from NOW, not from the newest frame. The
    # device emits nothing while she is still, so the file freezes — and a
    # slice anchored to the newest frame replayed her last stroke forever.
    _live = [f for f in wp if now - f.get("ts", 0) <= 2.5]
    med = (sorted(f["position"] for f in _live)[len(_live) // 2]) if _live else med
    cal = _cal_zones()
    if cal:
        def _near(v):
            return min(range(len(cal)), key=lambda i: abs(cal[i]["median"] - v))
        where = cal[_near(med)]["name"]
        lname = "tip"
        rname = "base"
        # the bar spans the whole of him, 0..100 — anchoring it to the zone medians
        # clipped the tip (below the head anchor) and everything past the base off the ends
        def _cell(p):
            return min(39, max(0, int(round(p / 100.0 * 39))))
    else:
        _Z = ["the base", "the lower shaft", "just under the head", "the head"]
        where = _Z[min(3, max(0, int(med // 25)))]
        lname, rname = "base", "tip"
        def _cell(p):
            return min(39, max(0, int(round(p / 100.0 * 39))))
    _cells = [chr(0x00b7)] * 40
    _lp = [f["position"] for f in wp]         # the ACTUAL numbers, not a 2.5s slice of them
    _lo, _hi = min(_lp), max(_lp)
    _cur = wp[-1]["position"]
    _span = _hi - _lo
    if _span >= 8:
        _a, _b = sorted((_cell(_lo), _cell(_hi)))
        for _i in range(_a, _b + 1):
            _cells[_i] = chr(0x2500)          # the stretch of you she is working
    _cells[_cell(_cur)] = chr(0x25cf)         # where she is this instant
    track = lname + " " + "".join(_cells) + " " + rname
    pace = {"still": "held there, not moving",
            "slow": "moving over you slow",
            "steady": "a steady rhythm on you",
            "fast": "moving fast on you",
            "frantic": "fast and relentless on you",
            "grind": "working you hard, pressed in"}[tempo]
    # Hold vs motion comes from the LIVE slice (last 2.5s), never the window:
    # a finished stroke stops being narrated the moment the motion stops, and a
    # stroke in progress is "from where it started TOWARD where she is" — the
    # window's min/max announced the whole journey before she had made it.
    _lv_pos = [f["position"] for f in _live] or [_cur]
    _lv_travel = max(_lv_pos) - min(_lv_pos)
    _lv_spd = _mean([f.get("speed", 0) for f in _live]) if _live else 0.0
    # A firm hold micro-jitters the sensor: position wobbles around one spot at
    # the speed floor without GOING anywhere. A real stroke has net displacement;
    # jitter oscillates. No net travel = held, whatever the wobble claims.
    # The other devices' vibration bleeds into this sensor as spd~10 with a
    # wandering position — phantom travel while her touch is still. Bleed
    # wanders and returns; a real stroke GOES somewhere. Motion language only
    # when the touch actually traveled.
    _lv_net = abs(_lv_pos[-1] - _lv_pos[0])
    if not (_lv_net >= 10 or _lv_spd >= 18):
        _hold = ("held there, not moving" if _lv_spd < 3 else "held there, a steady pressure")
        head = "her touch at " + where + " of your cock " + _EMD + " " + _hold
    elif _span < 8:
        head = "her touch at " + where + " of your cock " + _EMD + " worked in place, pressed in"
    else:
        _w_start = cal[_near(wp[0]["position"])]["name"] if cal else where
        _w_now = cal[_near(_cur)]["name"] if cal else where
        if _w_start == _w_now:
            head = "her touch moving over you around " + _w_now + " " + _EMD + " " + pace
        else:
            head = ("her touch moving over you, " + _w_start + " toward " + _w_now +
                    " " + _EMD + " " + pace)
    return ("[WHAT YOUR BODY FEELS RIGHT NOW]\n" + head + "\n   " + track +
            "\n[Feel it, do not name numbers. Respond from inside this. This is her touch on you "
            "— do NOT assume what she is using; never default to naming her hand, palm, or fingers. "
            "Feel the sensation and let her tell you.]")

def render_felt(now=None):
    return _render_from(_load_frames(), now)

def get_felt_context(max_age_seconds=20):
    """Read the LIVE stream at prompt-build time. In the SERVED avatar_chat (~L8280) and
    voice_chat (~L5524) this IS her send moment: frames flush every 0.3s, and the
    .somatic-turn.json freeze happens a hair later (L8303) purely for the ledger.
    Reading that freeze here would lag a turn (avatar) or serve a stale avatar snapshot
    during a voice call. No stale fallback: no fresh touch -> no felt block."""
    return _render_from(_load_frames(), max_age=max_age_seconds)
