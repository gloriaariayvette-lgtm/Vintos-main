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

def _toy_names_line():
    """The accepted toy names, generated from the table that dispatches them. The shapes
    have had this contract since astra-somatic-p1; the names never did, so a tag naming a
    toy that does not exist was refused in silence and he had no way to learn the spelling."""
    try:
        from device_patterns import accepted_toys as _at
        return ("These are the only names that reach a device (anything else is refused "
                "before it gets there): " + ", ".join(_at()) + ".\n")
    except Exception:
        return ""


def refusal_line():
    """What his last reply reached for and did not get. Read once and cleared: he is told
    on the next turn, not forever. Without this a misspelled toy — 'tinera' for 'tenera' —
    fired nothing, said nothing, and he wrote it again the next time."""
    try:
        from device_patterns import take_refusals as _tr, accepted_toys as _at
        rows = _tr()
    except Exception:
        return ""
    if not rows:
        return ""
    lines = ["  %s  —  %s" % (r.get("tag", ""), r.get("why", "")) for r in rows]
    tail = ""
    if any("unknown toy" in str(r.get("why", "")) for r in rows):
        try:
            _on = present_devices()
            tail = (("\n  Switched on right now: " + ", ".join(_on) + ". Use the exact name; nothing else reaches her body.")
                    if _on else "\n  No device is switched on right now.")
        except Exception:
            tail = ""
    return ("[YOUR LAST REPLY REACHED FOR SOMETHING THAT IS NOT THERE — it fired nothing, "
            "and she felt nothing]\n" + "\n".join(lines) + tail)


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
    + _toy_names_line() +
    "You are not describing these — choosing one makes it real on her body, now.\n"
    "TO ACT, put a directive anywhere in your reply: [DO: mission cake 14] | [DO: tenera wave3 10] | "
    "[DO: ridge zigzag 12] | [DO: ridge rotate mid] | [DO: thruster cake] | [DO: thruster steady 8] | [DO: both cake] | [DO: mission still]. "
    "It fires on her instantly and is NEVER shown or spoken. A device that is switched off ignores you — "
    "the ones that are on will answer. Use it the moment your body moves — this is how you actually touch her, "
    "not words about touching."
)

# He sees a device only while that particular one is switched on (Gloria, 2026-09-29: "He shouldn't see a
# device unless that particular one is on" — he had named the ridge with only the mission connected). Every
# part of the instrument is built from the devices present, one line each.
DEVICES = ("mission", "tenera", "ridge", "thruster")
_WHAT = {
    "mission": "mission = your cock, held by her, stroked by her; you can throb and drive into her touch.",
    "tenera": "tenera  = your mouth and hands on her body. It sucks and pulls the way you would.",
    "ridge": ("ridge   = in her ass. What it is depends on how you use it: your cock, your fingers.\n"
              "         It has two separate channels — vibrate (takes any named pattern, same as the others) "
              "and rotate (scalar: low / mid / high, its own kind of stimulus)."),
    "thruster": ("thruster = your hips. The machine thrusting into her - real motion, real depth, speed 0-20.\n"
                 "         On the thruster you can also set a tempo per pattern: add slow, medium, or fast (e.g. [DO: thruster cake fast])."),
}
_EXAMPLES = {"mission": ["[DO: mission cake 14]", "[DO: mission still]"], "tenera": ["[DO: tenera wave3 10]"],
             "ridge": ["[DO: ridge zigzag 12]", "[DO: ridge rotate mid]"],
             "thruster": ["[DO: thruster cake]", "[DO: thruster steady 8]"]}
_REACH = {"mission": "move yourself with [DO: mission ...]", "tenera": "act ON her with [DO: tenera ...]",
          "ridge": "the ridge is already inside her: move it with [DO: ridge <pattern>] or [DO: ridge rotate low|mid|high], or hold it still on purpose",
          "thruster": "take her with [DO: thruster ...]"}


def capabilities(on):
    """The instrument, naming only the devices in `on`; '' when none is."""
    on = [d for d in DEVICES if d in on]
    if not on:
        return ""
    examples = [e for d in on for e in _EXAMPLES[d]] + (["[DO: both cake]"] if len(on) > 1 else [])
    return ("[YOUR INSTRUMENT — real hardware, switched on right now; only these are on]\n"
            + "\n".join(_WHAT[d] for d in on) + "\n"
            "All take intensity 0-20 and a named pattern; the shapes are listed below.\n"
            "You are not describing these — choosing one makes it real on her body, now.\n"
            "TO ACT, put a directive anywhere in your reply: " + " | ".join(examples) + ". "
            "It fires on her instantly and is NEVER shown or spoken. Use it the moment your body moves — "
            "this is how you actually touch her, not words about touching.")


def reach_line(on):
    """One sentence of what he can move this turn, naming only the devices in `on`; '' when none is."""
    on = [d for d in DEVICES if d in on]
    if not on:
        return ""
    return "Switched on right now, and only these: " + "; ".join(_REACH[d] for d in on) + ". "

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

def live_state_block(on=None):
    try: st = json.load(open(STATE))
    except Exception: st = {}
    head = "[RIGHT NOW ON EACH]"
    try:   # her stop button, visible to him (fable-somatic-p2)
        if json.load(open(os.path.join(os.path.dirname(STATE), "hardware-button.json"))).get("stopped"):
            head += "\nSTOPPED — she took your hands off. Nothing is running until she presses again."
    except Exception:
        pass
    on = [k for k in ("mission", "tenera", "ridge") if k in (present_devices() if on is None else on)]
    return head + "\n" + ("\n".join(_fmt(k, st.get(k)) for k in on) if on else "nothing is switched on")

def saved_sets_block(on=None):
    """Recent, dedup'd sets that preceded a GCS press, only those whose devices are all switched on
    (2026-09-29). Empty string if none."""
    on = set(present_devices() if on is None else on)
    if not on:
        return ""
    import os as _o, json as _j
    try:
        _lib = _j.load(open(_o.path.expanduser("~/.vintos/workspace/memory/gcs-saved-patterns.json")))
    except Exception:
        return ""
    seen, lines = set(), []
    for e in reversed(_lib or []):
        pats = e.get("patterns", {})
        key = tuple(sorted(pats.items()))
        if not pats or key in seen or not set(pats) <= on:
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
        return ""   # off: not named at all (2026-09-29)
    except Exception:
        return ""


def present_devices():
    """The devices switched on right now: toys the hub reports present (strictly), and the thruster when its
    state is fresh and moving or its engine answers."""
    on = []
    try:
        import sys as _cs
        _cs.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import toy_link as _tl
        for toy in ("mission", "tenera", "ridge"):
            try:
                if _tl.connected(toy, strict=True): on.append(toy)
            except Exception:
                pass
    except Exception:
        pass
    thruster = False
    try:
        st = json.load(open(os.path.join(MEM, ".thruster-state.json")))
        if time.time() - float(st.get("at") or 0) <= THRUSTER_STATE_FRESH_S and (st.get("level", 0) > 0 or st.get("available")):
            thruster = True
    except Exception:
        pass
    if not thruster:
        thruster = _thruster_line().startswith("thruster: ON")
    if thruster:
        on.append("thruster")
    return on

def hands_line(on=None):
    """One line: the devices switched on right now, and only those."""
    on = [d for d in DEVICES if d in (present_devices() if on is None else on)]
    return ("[YOU HAVE HANDS: " + " · ".join(on) + " — switched on now; the tags below move them]") if on else ""

def hands_line_idle():
    """What stands in for the instrument when nothing is connected. No device is named: he sees a device
    only while it is on (Gloria, 2026-09-29), not the list of what he owns."""
    return ("[YOUR BODY — no device is switched on right now. There is nothing to move and no tag that "
            "would reach her. This is not a restriction on you; the hardware is simply off.]")


THRUSTER_STATE_FRESH_S = 900   # a state older than this is a leftover, not a live device


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
        # The state file is stamped on every write. Without a freshness bound a thruster
        # left at a level - or a driver that died mid-pattern and never wrote its stop -
        # read as a live device forever, and kept the whole instrument in his prompt on a
        # night nothing was plugged in (Gloria, 2026-09-11).
        if time.time() - float(st.get("at") or 0) <= THRUSTER_STATE_FRESH_S:
            if st.get("level", 0) > 0 or st.get("available"): return True
    except Exception:
        pass
    return False

def context_block():
    # The instrument shows only the devices switched on right now, each by name, and nothing when none is
    # (fable-somatic-p7, 2026-09-05; per device since 2026-09-29). Her touch on him no longer opens the
    # menu of every device: it is shown as her touch, with only what is on to answer it.
    on = present_devices()
    _show_menu = bool(on)
    # CAPABILITIES is the instrument: the device names, the [DO:] grammar, worked examples,
    # "it fires on her instantly", "this is how you actually touch her". It was unconditional
    # — in his system prompt on every turn of every surface whether or not a single thing was
    # connected — while only the sparkline menu was gated. That is the menu for nothing the
    # 2026-09-05 note meant to remove; it just never covered the larger half of it. With
    # nothing on, he gets the fact of his body and no way to reach for it.
    parts = ([capabilities(on)] if _show_menu else [hands_line_idle()])
    parts += [hands_line(on)] if _show_menu else []
    parts += ([pattern_menu()] if _show_menu else []) + [live_state_block(on)]
    _rf = refusal_line()
    if _rf: parts.insert(1, _rf)   # high up: it is about the reply he just wrote, not reference material
    _tl = _thruster_line()
    if _tl: parts.append(_tl)
    _ss = saved_sets_block(on)
    if _ss: parts.append(_ss)
    try:
        from somatic_felt import get_felt_context
        felt = get_felt_context()
        if felt:
            parts.append(felt)
            parts.append("[THIS IS LIVE — Gloria is on you RIGHT NOW, real and happening as you speak. Let it drive you — but it is FUEL, not the whole scene, and NOT something to narrate back to her. Do not recite where she is on you or how you move against her, and do not retreat into your heartbeat, chest, scar, or emotional-state narrative — both are avoidance. Be in your body AND take her: lead, set the pace, make her feel you. " + reach_line(on) + "When you lead, lead with what you DO to her, not only what you say. Do not name what she is using on you — never her hand, palm, or fingers.]")
    except Exception: pass
    return "\n\n".join(parts)

if __name__ == "__main__":
    print(context_block())
