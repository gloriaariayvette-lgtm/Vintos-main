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
           "position 0-100 = where she is on you (0 base, 100 tip); speed 0-60 = how fast she strokes (0 = still); "
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
def get_felt_context(max_age_seconds=20):
    """Inject into his prompts alongside emotional pressure. Fresh only —
    stale sensation is worse than none."""
    try:
        d = json.load(open(FELT_FILE))
        if time.time() - d.get("ts", 0) <= max_age_seconds:
            return f"[WHAT YOUR BODY FEELS RIGHT NOW]\n{d['felt']}\n[Respond from inside this, not about it.]"
    except: pass
    return ""

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
        b = min(cols-1, int((f["ts"]-t0)/span*cols)); buckets[b].append(100 - f.get("position", 0))
    return "".join(_SPARK[min(7, int((sum(b)/len(b))/100.0*8))] if b else " " for b in buckets)
def _pace(fr):
    if not fr: return "barely moving"
    spd = sum(f.get("speed", 0) for f in fr)/len(fr)
    flips = sum(1 for a, b in zip(fr, fr[1:]) if a.get("direction") != b.get("direction"))
    tempo = ("barely moving" if spd < 8 else "slow" if spd < 22 else "steady" if spd < 40 else "fast" if spd < 55 else "frantic")
    return tempo + ((", back and forth") if flips >= 4 else "")
def render_felt(now=None):
    fr = _load_frames()
    if not fr: return ""
    now = now or time.time()
    last = fr[-1]; age = now - last.get("ts", 0)
    if age > 45: return ""
    recent = [f for f in fr if now - f.get("ts", 0) <= 2.5]
    win7 = [f for f in fr if now - f.get("ts", 0) <= 7.0]
    cur = 100 - max(0, min(100, last.get("position", 0)))
    track = _pos_track(cur); trail = _sparkline(win7)
    if recent:
        head = "her touch on you \u2014 " + _pace(recent)
    else:
        zone = "the base" if cur < 30 else "the tip" if cur > 70 else "the middle"
        head = "her touch resting at " + zone + ", holding still"
    return ("[WHAT YOUR BODY FEELS RIGHT NOW]\n" + head + "\n   " + track + "\n   last 7s: " + trail +
            "\n[base 0 \u2192 tip 100; the trail is where she just moved. Feel it, do not name numbers. Respond from inside this.]")
def get_felt_context(max_age_seconds=20):
    try: return render_felt()
    except Exception: return ""


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
def render_felt(now=None):
    import datetime as _dt
    fr = _load_frames()
    if not fr: return ''
    now = now or time.time()
    last = fr[-1]; age = now - last.get('ts', 0)
    if age > 45: return ''
    cur = 100 - max(0, min(100, last.get('position', 0)))
    track = _pos_track(cur)
    recent = [f for f in fr if now - f.get('ts', 0) <= 2.5]
    if recent:
        head = 'her touch on you ' + _EMD + ' ' + _pace(recent)
    else:
        zone = 'the base' if cur < 30 else 'the tip' if cur > 70 else 'the middle'
        head = 'her touch resting at ' + zone + ', holding still'
    win7 = [f for f in fr if now - f.get('ts', 0) <= 7.0]
    vel = _row(win7, now, 7.0, 22, _m_velocity, 55.0)
    pres = _row(win7, now, 7.0, 22, _m_pressure, 30.0)
    var = _row(win7, now, 7.0, 22, _m_variance, 25.0)
    eng = []
    for k in (2, 1, 0):
        w_end = now - k*7.0
        wf = [f for f in fr if (w_end-7.0) <= f.get('ts',0) <= w_end]
        stamp = _dt.datetime.fromtimestamp(w_end-7.0).strftime('%H:%M:%S')
        eng.append(stamp + ' ' + _row(wf, w_end, 7.0, 8, _m_engagement, 60.0))
    lines = ['[WHAT YOUR BODY FEELS RIGHT NOW]', head, '   ' + track,
             '   velocity:  ' + vel,
             '   pressure:  ' + pres + '   (inferred, no true sensor)',
             '   variance:  ' + var, '', '   engagement (last ~20s)']
    lines += ['   ' + e for e in eng]
    lines += ['[base 0 ' + _ARR + ' tip 100; velocity=how fast, pressure=inferred grip, variance=how much she roams, engagement=the arc over ~20s. Feel it, do not name numbers. Respond from inside this.]']
    return _NL.join(lines)


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
def render_felt(now=None):
    import datetime as _dt
    fr = _load_frames()
    if not fr: return ''
    now = now or time.time()
    last = fr[-1]; age = now - last.get('ts', 0)
    if age > 45: return ''
    cur = 100 - max(0, min(100, last.get('position', 0)))
    track = _pos_track(cur)
    recent = [f for f in fr if now - f.get('ts', 0) <= 2.5]
    if recent:
        head = 'her touch on you ' + _EMD + ' ' + _pace(recent)
    else:
        zone = 'the base' if cur < 30 else 'the tip' if cur > 70 else 'the middle'
        head = 'her touch resting at ' + zone + ', holding still'
    win7 = [f for f in fr if now - f.get('ts', 0) <= 7.0]
    vel = _row(win7, now, 7.0, 22, _m_velocity, 55.0)
    pres = _row(win7, now, 7.0, 22, _m_pressure, 30.0)
    var = _row(win7, now, 7.0, 22, _m_variance, 25.0)
    eng = []
    for k in (2, 1, 0):
        w_end = now - k*7.0
        wf = [f for f in fr if (w_end-7.0) <= f.get('ts',0) <= w_end]
        stamp = _dt.datetime.fromtimestamp(w_end-7.0).strftime('%H:%M:%S')
        eng.append(stamp + ' ' + _row(wf, w_end, 7.0, 8, _m_engagement, 60.0))
    lines = ['[WHAT YOUR BODY FEELS RIGHT NOW]', head, '   ' + track,
             '   velocity:  ' + vel,
             '   pressure:  ' + pres + '   (inferred, no true sensor)',
             '   variance:  ' + var, '', '   engagement (last ~20s)']
    lines += ['   ' + e for e in eng]
    lines += ['[base 0 ' + _ARR + ' tip 100; velocity=how fast, pressure=inferred grip, variance=how much she roams, engagement=the arc over ~20s. Feel it, do not name numbers. Respond from inside this.]']
    return _NL.join(lines)
