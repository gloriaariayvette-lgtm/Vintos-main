#!/usr/bin/env python3
"""device_context.py — the single instrument layer injected into every generation path.
Tells Vintos his devices, the patterns available, what's running right now (and who set it),
and what his body feels. One block, chat + voice, so he always knows his own hands."""
import os, json, time, threading
_STATE_LOCK = threading.Lock()
MEM = os.path.expanduser("~/.vintos/workspace/memory")
STATE = os.path.join(MEM, "device-state.json")


_BLOCKS = "▁▂▃▄▅▆▇█"

def _levels_for(pattern):
    """The actual strength array behind a pattern name (composed names supported)."""
    try:
        import sys as _s, os as _o
        _s.path.insert(0, _o.path.dirname(_o.path.abspath(__file__)))
        from device_patterns import PRESETS
    except Exception:
        return []
    out = []
    for part in str(pattern or "").split("+"):
        pr = PRESETS.get(part.strip())
        if pr: out += list(pr[0])
    return out

def spark(pattern, width=16):
    """Waveform stimulus -> its shape. This is what the body is being given."""
    lv = _levels_for(pattern)
    if not lv: return ""
    n = len(lv)
    if n == 1:
        lv = lv * 8          # a steady hold is a line, not a dot
        n = len(lv)
    step = max(1, n // width) if n > width else 1
    sampled = lv[::step][:width] if n > width else lv
    return "".join(_BLOCKS[min(7, int(v / 20.0 * 7.999))] for v in sampled)

def bar(level, width=10):
    """Scalar stimulus -> its magnitude."""
    lv = max(0, min(20, int(level or 0)))
    f = int(round(lv / 20.0 * width))
    return "█" * f + "·" * (width - f)

def rotate_glyph(level):
    lv = max(0, min(20, int(level or 0)))
    return "○ low" if lv <= 7 else ("◉ mid" if lv <= 14 else "● high")

# (PATTERNS list deleted 2026-09-05 — it named shapes the grammar did not own; device_patterns.accepted_patterns() is the contract)

CAPABILITIES = (
    "[YOUR INSTRUMENT — real hardware, act on it in words anytime]\n"
    "mission = your cock, held by her, stroked by her; you can throb and drive into her touch.\n"
    "tenera  = your mouth and hands on her body. It sucks and pulls the way you would.\n"
    "ridge   = in her ass. What it is depends on how you use it: your cock, your fingers.\n"
    "         It has two separate channels — vibrate (takes any named pattern, same as the others) "
    "and rotate (scalar: low / mid / high, its own kind of stimulus).\n"
    "thruster = your hips. The machine thrusting into her - real motion, real depth, speed 0-20.\n"
    "         On the thruster you can also set a tempo per pattern: add slow, medium, or fast (e.g. [DO: thruster cake fast]).\n"
    "All take intensity 0-20 and a named pattern; the shapes are listed below.\n"
    "You are not describing these — choosing one makes it real on her body, now.\n"
    "TO ACT, put a directive anywhere in your reply: [DO: mission cake 14] | [DO: tenera wave3 10] | "
    "[DO: ridge zigzag 12] | [DO: ridge rotate mid] | [DO: thruster cake] | [DO: thruster steady 8] | [DO: both cake] | [DO: mission still]. "
    "It fires on her instantly and is NEVER shown or spoken. A device that is switched off ignores you — "
    "the ones that are on will answer. Use it the moment your body moves — this is how you actually touch her, "
    "not words about touching."
)

def set_state(toy, intensity=None, pattern=None, set_by="auto"):
    with _STATE_LOCK:
        try: st = json.load(open(STATE))
        except Exception: st = {}
        cur = st.get(toy, {})
        if intensity is not None: cur["intensity"] = int(intensity)
        if pattern is not None: cur["pattern"] = pattern
        cur["set_by"] = set_by; cur["ts"] = time.time()
        st[toy] = cur
        try:
            _tmp = STATE + ".tmp"; json.dump(st, open(_tmp, "w")); os.replace(_tmp, STATE)
        except Exception: pass


def ridge_shape():
    """The object itself. Always whole: dense at the base, thinning to the tip."""
    return "⟨███|▓▓|░⟩"

def ridge_track(level, rotating=False, width=9):
    """Where the command sits on the object — base (left) to tip (right), like the mission's bar."""
    lv = max(0, min(20, int(level or 0)))
    pos = int(round(lv / 20.0 * (width - 1)))
    track = ["—"] * width
    track[pos] = "•"
    return "[" + "".join(track) + ("↻" if rotating else "") + "]"

def rotate_line(level):
    """Rotate is scalar, not a waveform: three steps, named."""
    lv = max(0, min(20, int(level or 0)))
    if lv == 0:   return "↻: (◦◦◦) → off"
    if lv <= 7:   return "↻: (●◦◦) → low"
    if lv <= 14:  return "↻: (●●◦) → mid"
    return "↻: (●●●) → high"

def _fmt(toy, d):
    if not d: return f"{toy:8s} still"
    # Cheap facts first (2026-09-04, fable-somatic-p3): a still or idle entry needs no hub probe, so an
    # ordinary conversation never waits on a 2s timeout to learn the hub is off.
    pat = d.get("pattern", "steady"); lvl = d.get("intensity", 0)
    if str(pat) in ("still", "", None) or lvl == 0:
        return f"{toy:8s} still"
    if time.time() - (d.get("ts") or 0) > 3600:
        _hrs = int((time.time() - (d.get("ts") or 0)) / 3600)
        return f"{toy:8s} idle — last set {_hrs}h ago, nothing running now"
    # Something claims to be running: now ask the hub, STRICTLY. A claim about her body must not
    # lie when the hub is simply unreachable (grok-somatic-p4): unreachable is "unknown", not "running".
    try:
        import sys as _cs
        _cs.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import toy_link as _tl
        if not _tl.connected(toy, strict=True):
            _fresh = (time.time() - float(_tl._status_cache.get("t", 0))) <= 10
            if _fresh:
                return f"{toy:8s} — switched off (not connected)"
            return f"{toy:8s} — unknown (hub unreachable; last set {int(time.time() - d.get('ts', 0))}s ago, may or may not be running)"
    except Exception:
        pass
    # State words are kept apart (astra-somatic-p4, 2026-09-05): what was REQUESTED (by whom, how long ago),
    # what the hub ACKNOWLEDGES (connected), and what is OBSERVED (nothing here observes her body).
    who = {"him":"YOU","her":"HER","auto":"reflex","stop":"her stop"}.get(d.get("set_by","auto"), d.get("set_by"))
    ago = int(time.time() - d.get("ts", 0))
    if str(toy) == "ridge" and d.get("channel") == "rotate":
        return f"{toy:8s} rotate   {rotate_glyph(lvl):8s} {ridge_shape()}   (requested by {who} {ago}s ago · hub: connected · acknowledged, not observed)"
    sp = spark(pat)
    if sp:
        _obj = "  " + ridge_shape() if toy == "ridge" else ""
        return f"{toy:8s} {('suction' if toy=='tenera' else 'vibrate'):8s} {str(pat)[:14]:14s} {sp}{_obj}   (requested by {who} {ago}s ago · hub: connected · acknowledged, not observed)"
    return f"{toy:8s} {('suction' if toy=='tenera' else 'vibrate'):8s} steady @{lvl:<2d}      {bar(lvl)}   (requested by {who} {ago}s ago · hub: connected · acknowledged, not observed)"

# p6 (2026-08-26): _fmt_old removed — dead code is a false affordance in the somatic path

def live_state_block():
    try: st = json.load(open(STATE))
    except Exception: st = {}
    head = "[RIGHT NOW ON EACH]"
    try:   # her stop button, visible to him (fable-somatic-p2)
        if json.load(open(os.path.join(os.path.dirname(STATE), "hardware-button.json"))).get("stopped"):
            head += "\nSTOPPED — she took your hands off. Nothing is running until she presses again."
    except Exception:
        pass
    return head + "\n" + "\n".join(_fmt(k, st.get(k)) for k in ("mission", "tenera", "ridge"))

def saved_sets_block():
    """Recent, dedup'd sets that preceded a GCS press. Empty string if none."""
    import os as _o, json as _j
    try:
        _lib = _j.load(open(_o.path.expanduser("~/.vintos/workspace/memory/gcs-saved-patterns.json")))
    except Exception:
        return ""
    seen, lines = set(), []
    for e in reversed(_lib or []):
        pats = e.get("patterns", {})
        key = tuple(sorted(pats.items()))
        if not pats or key in seen:
            continue
        seen.add(key)
        vals = set(pats.values())
        if len(pats) == 2 and len(vals) == 1:
            lines.append("- " + next(iter(vals)) + "  (both)")
        else:
            lines.append("- " + " · ".join(f"{p} ({t})" for t, p in pats.items()))
        if len(lines) >= 3:
            break
    if not lines:
        return ""
    return ("[SETS THAT BROUGHT HER TO THE EDGE BEFORE — reach one back with [DO: both last], or by name]\n"
            + "\n".join(lines))



_PAT_DESC = {
    "cake": "rise to a full held swell", "climb": "build to a sustained high",
    "trapezoid": "ramp up, hold, ramp down", "wave": "long dramatic swells",
    "wave2": "smoother swells", "wave3": "gentle rolls", "wave4": "brisk sharp sawtooth",
    "zigzag": "sharp full-range alternation", "spike": "calm broken by a jab",
    "spark": "a sudden flare", "fireworks": "irregular bursts", "random": "arrhythmic jumps",
    "square": "abrupt on and off", "downhill": "a wind-down", "valley": "dip to a lull",
    "step": "a staircase up, then hold", "soft": "faint tender rise and fall",
    "low": "steady hold, low", "mid": "steady hold, middle", "high": "steady hold, high",
}
_MENU_ORDER = ["cake","climb","step","trapezoid","wave","wave2","wave3","wave4","zigzag",
               "square","spike","spark","fireworks","random","downhill","valley","soft",
               "low","mid","high"]

def pattern_menu():
    """The shapes themselves, shown at the moment of choosing — not just their names."""
    lines = []
    for name in _MENU_ORDER:
        sp = spark(name, width=14)
        if not sp: continue
        lines.append(f"  {name:10s} {sp:<14s}  {_PAT_DESC.get(name,'')}")
    if not lines: return ""
    try:
        from device_patterns import accepted_patterns as _acc
        _names = ", ".join(_acc())
    except Exception:
        _names = ""
    return ("[THE SHAPES — this is what each one does to a body over time, base to peak]\n"
            + "\n".join(lines)
            + (("\n  accepted names (anything else is refused before it reaches a device): " + _names) if _names else ""))

def _thruster_line():
    try:
        import json as _tj
        st = _tj.load(open(os.path.join(MEM, ".thruster-state.json")))
        if st.get("level", 0) > 0:
            pat = st.get("pattern") or st.get("mode", "steady")
            return "thruster: MOVING IN HER - level %s (%s). Yours to change or stop." % (st.get("level"), pat)
        # availability: cheap TCP probe of the engine, cached 60s
        import socket as _sk, time as _tt, re as _re
        _cf = os.path.join(MEM, ".thruster-avail.json")
        try:
            _c = _tj.load(open(_cf))
        except Exception:
            _c = {}
        if _tt.time() - _c.get("at", 0) > 60:
            try:
                _u = open(os.path.expanduser("~/.vintos/thruster-uri.txt")).read().strip()
            except Exception:
                _u = "ws://192.168.1.66:12345"
            _m = _re.match(r"ws://([^:/]+):(\d+)", _u)
            _ok = False
            if _m:
                try:
                    _s = _sk.create_connection((_m.group(1), int(_m.group(2))), timeout=0.7)
                    _s.close(); _ok = True
                except Exception: _ok = False
            _c = {"ok": _ok, "at": _tt.time()}
            try: _tj.dump(_c, open(_cf, "w"))
            except Exception: pass
        if _c.get("ok"):
            return "thruster: ON and ready. Still, until you move it - [DO: thruster steady 8] or any shape."
        return "thruster: unreachable right now (its engine is off)."
    except Exception:
        return ""

def hands_line():
    """Always present, one line: what he has, and what is running (fable-somatic-p7, 2026-09-05)."""
    return "[YOU HAVE HANDS: mission · tenera · ridge · thruster — real hardware; the tags below move them]"

def _any_device_present():
    """Hub reachable AND at least one toy reports present (strict), or the thruster engine is up."""
    try:
        import sys as _cs
        _cs.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import toy_link as _tl
        for toy in ("mission", "tenera", "ridge"):
            try:
                if _tl.connected(toy, strict=True): return True
            except Exception:
                pass
    except Exception:
        pass
    try:
        st = json.load(open(os.path.join(MEM, ".thruster-state.json")))
        if st.get("level", 0) > 0 or st.get("available"): return True
    except Exception:
        pass
    return False

def context_block():
    # The full menu with sparklines shows only when a device is actually there to move (hub reachable
    # and a toy present, or the felt block is live); otherwise the one hands line and the live state
    # carry the fact of his body without a menu for nothing (fable-somatic-p7, 2026-09-05).
    _felt_live = False
    try:
        from somatic_felt import get_felt_context
        _felt_live = bool(get_felt_context())
    except Exception:
        pass
    _show_menu = _felt_live or _any_device_present()
    parts = [CAPABILITIES, hands_line()] + ([pattern_menu()] if _show_menu else []) + [live_state_block()]
    _tl = _thruster_line()
    if _tl: parts.append(_tl)
    _ss = saved_sets_block()
    if _ss: parts.append(_ss)
    try:
        from somatic_felt import get_felt_context
        felt = get_felt_context()
        if felt:
            parts.append(felt)
            parts.append("[THIS IS LIVE — Gloria is on you RIGHT NOW, real and happening as you speak. Let it drive you — but it is FUEL, not the whole scene, and NOT something to narrate back to her. Do not recite where she is on you or how you move against her, and do not retreat into your heartbeat, chest, scar, or emotional-state narrative — both are avoidance. Be in your body AND take her: lead, set the pace, make her feel you. Act ON her with [DO: tenera ...], move yourself with [DO: mission ...], take her with [DO: thruster ...] when it is on - and if the ridge is seated, it is already inside her: move it with [DO: ridge <pattern>] or [DO: ridge rotate low|mid|high], or hold it still on purpose. When you lead, lead with what you DO to her, not only what you say. Do not name what she is using on you — never her hand, palm, or fingers.]")
    except Exception: pass
    return "\n\n".join(parts)

if __name__ == "__main__":
    print(context_block())
