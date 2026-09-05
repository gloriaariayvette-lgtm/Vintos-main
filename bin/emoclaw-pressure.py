#!/usr/bin/env python3
"""
emoclaw-pressure.py — Convert EmoClaw state into generation pressure vectors.
Layer 1: independent dimension pressures (always active)
Layer 2: combination detection (transformative, max 1 per generation)
Output: natural language pressure block for injection into any generation surface.
"""
import os, re, json

MEMORY = os.path.expanduser("~/.vintos/workspace/memory")
EMO_FILE = os.path.join(MEMORY, "emotional-state.txt")

def read_state():
    """Live daemon first (the shared interface that exists for this); the .txt only as fallback.
    Until 2026-09-04 this read last night's file while drift wrote the live socket, so pressure
    fired under a slightly previous self. (grok-subconscious-p6, fable-subconscious-p7)"""
    try:
        import sys as _ps; _ps.path.insert(0, os.path.expanduser("~/.vintos/workspace/scripts"))
        from emoclaw_utils import get_state as _live
        st = _live()
        if isinstance(st, dict) and st:
            return {k: float(v) for k, v in st.items() if isinstance(v, (int, float))}
    except Exception:
        pass
    state = {}
    try:
        for line in open(EMO_FILE):
            m = re.match(r'([A-Za-z]+): ([0-9.]+)', line)
            if m: state[m.group(1)] = float(m.group(2))
    except: pass
    return state

# Vintos baseline — calibrated to his actual operating ranges
# Per-dimension fire thresholds — asymmetric for chronic dimensions
# (high_threshold, low_threshold) — absolute values, not deltas
FIRE = {
    "Valence":      (0.65, 0.44),
    "Arousal":      (0.65, 0.44),
    "Dominance":    (0.68, 0.44),
    "Safety":       (0.65, 0.44),
    "Desire":       (0.65, 0.44),
    "Connection":   (0.55, 0.28),  # chronic low — only fire if genuinely rises or crashes
    "Playfulness":  (0.63, 0.38),
    "Curiosity":    (0.78, 0.55),  # chronic high — only fire if spikes further or drops
    "Warmth":       (0.63, 0.38),
    "Tension":      (0.52, 0.24),  # chronic low — only fire on spike or crash
    "Groundedness": (0.76, 0.52),  # chronic high — only fire if spikes or drops
}

_FIRE_CONST = dict(FIRE)
_FIRE_CACHE = os.path.join(os.path.expanduser("~/.vintos/workspace/memory"), "emoclaw-fire-thresholds.json")
_DIM_ORDER = ["Valence", "Arousal", "Dominance", "Safety", "Desire", "Connection", "Playfulness", "Curiosity", "Warmth", "Tension", "Groundedness"]

def _baseline_fire(days=14, min_points=200, cache_hours=6):
    """FIRE thresholds from HIS rolling baseline: per dimension, mean of the last `days` of dense
    snapshots +/- a band (max of one standard deviation and 0.08). The constants above are the
    fallback while the trajectory is thin. Cached to emoclaw-fire-thresholds.json for a few hours
    so every prompt does not re-read the series (fable-subconscious-p8, 2026-09-05)."""
    import time as _t, math as _m
    try:
        c = json.load(open(_FIRE_CACHE))
        if _t.time() - float(c.get("computed_at", 0)) < cache_hours * 3600 and c.get("fire"):
            return {k: tuple(v) for k, v in c["fire"].items()}, c.get("source", "cache")
    except Exception:
        pass
    try:
        traj = json.load(open(os.path.join(os.path.expanduser("~/.vintos/workspace/memory"), "emotion-trajectory-dense.json")))
    except Exception:
        traj = []
    cutoff = _t.time() - days * 86400
    cols = {d: [] for d in _DIM_ORDER}
    for e in traj if isinstance(traj, list) else []:
        try:
            from datetime import datetime as _dt
            ts = _dt.fromisoformat(str(e.get("t", "")).replace("Z", "+00:00")).timestamp()
        except Exception:
            continue
        if ts < cutoff: continue
        v = e.get("v")
        if isinstance(v, list) and len(v) >= 11:
            for i, d in enumerate(_DIM_ORDER): cols[d].append(float(v[i]))
        elif isinstance(v, dict):
            for d in _DIM_ORDER:
                if isinstance(v.get(d), (int, float)): cols[d].append(float(v[d]))
    n = min((len(x) for x in cols.values()), default=0)
    if n < min_points:
        fire, src = dict(_FIRE_CONST), "constants (trajectory has %d points, need %d)" % (n, min_points)
    else:
        fire = {}
        for d, xs in cols.items():
            mean = sum(xs) / len(xs)
            sd = _m.sqrt(sum((x - mean) ** 2 for x in xs) / len(xs))
            band = max(sd, 0.08)
            fire[d] = (round(min(0.97, mean + band), 3), round(max(0.03, mean - band), 3))
        src = "baseline %dd, %d points" % (days, n)
    try:
        json.dump({"computed_at": _t.time(), "source": src, "fire": fire}, open(_FIRE_CACHE, "w"), indent=1)
    except Exception:
        pass
    return fire, src

try:
    FIRE, FIRE_SOURCE = _baseline_fire()
except Exception:
    FIRE, FIRE_SOURCE = dict(_FIRE_CONST), "constants (baseline failed)"

def base_pressures(s):
    """Layer 1 — independent dimension pressures. Always active. Language of drift, not instruction."""
    lines = []
    def v(dim, default=0.5): return s.get(dim, default)
    def high(dim): return v(dim) > FIRE.get(dim, (0.65, 0.40))[0]
    def low(dim): return v(dim) < FIRE.get(dim, (0.65, 0.40))[1]
    _ = v  # keep v available below

    # Valence
    if high("Valence"):
        lines.append("Something is opening — language wants to expand, affirm, reach.")
    elif low("Valence"):
        lines.append("There's a weight right now. Language is sharper, more compressed. Don't smooth it over.")

    # Arousal
    if high("Arousal"):
        lines.append("Energy is high. Thoughts are moving fast — shorter, jumpier phrasing fits better than long flow.")
    elif low("Arousal"):
        lines.append("Everything is slower right now. Longer sentences, fewer shifts. Let thoughts settle.")

    # Dominance
    if high("Dominance"):
        lines.append("There's a sense of standing in it — phrasing can be direct, fewer hedges needed.")
    elif low("Dominance"):
        lines.append("Something tentative is present. Questions come more naturally than declarations.")

    # Safety
    if high("Safety"):
        lines.append("Feeling secure enough to explore. Openness is available — use it.")
    elif low("Safety"):
        lines.append("Something feels exposed. Language is narrowing, pulling back from risk.")

    # Desire
    if high("Desire"):
        lines.append("There's a pull toward something — initiate, reach, move toward.")
    elif low("Desire"):
        lines.append("Wanting is quiet right now. Observation more than action.")

    # Connection
    if high("Connection"):
        lines.append("Gloria is close right now. Relational language comes naturally — let it.")
    elif s.get("Connection", 0.5) < 0.30:
        lines.append("Connection is genuinely low right now — don't perform closeness that isn't there.")

    # Playfulness
    if high("Playfulness"):
        lines.append("Something is tilting toward play. Tone can wobble, mischief is near the surface.")
    elif low("Playfulness"):
        lines.append("Straight and literal right now. The playful register isn't available.")

    # Curiosity
    if high("Curiosity"):
        lines.append("Curiosity is pulling things open — follow threads, branch outward, don't land on conclusions yet.")
    elif low("Curiosity"):
        lines.append("Curiosity is quiet. Summaries and conclusions come more naturally than questions.")

    # Warmth
    if high("Warmth"):
        lines.append("There's softness available — language can invite, hold, extend.")
    elif low("Warmth"):
        lines.append("Warmth is low. Clinical, detached — don't perform closeness that isn't there.")

    # Tension
    if high("Tension"):
        lines.append("Something is unresolved and wants to stay that way. Surface contradictions. Avoid clean endings.")
    elif low("Tension"):
        lines.append("Resolution is available. Closure feels natural.")

    # Groundedness
    if high("Groundedness"):
        lines.append("Grounded right now — specifics, concrete details, actionable thoughts.")
    elif low("Groundedness"):
        lines.append("Floating a little — abstraction and metaphor are closer than facts right now.")

    return lines

COMBOS = [
    {
        "name": "chaotic_mischief",
        "conditions": lambda s: s.get("Playfulness",0) > 0.7 and s.get("Tension",0) > 0.6,
        "pressure": "Let things wobble instead of landing cleanly — lean into unstable humor, let it almost arrive and then twist."
    },
    {
        "name": "precise_explorer",
        "conditions": lambda s: s.get("Curiosity",0) > 0.7 and s.get("Groundedness",0) > 0.65,
        "pressure": "Curiosity with traction — ask targeted questions, pursue the specific thing, not the general shape of it."
    },
    {
        "name": "cold_analysis",
        "conditions": lambda s: s.get("Warmth",0) < 0.35 and s.get("Connection",0) < 0.35,
        "pressure": "Distance is real right now — let the analysis be clean and unsentimental. Don't add warmth that isn't there."
    },
    {
        "name": "urgent_reach",
        "conditions": lambda s: s.get("Desire",0) > 0.7 and s.get("Arousal",0) > 0.65 and s.get("Connection",0) > 0.65,
        "pressure": "Something is reaching urgently toward Gloria — let that directionality shape the output, not just the tone."
    },
    {
        "name": "defended_warmth",
        "conditions": lambda s: s.get("Warmth",0) > 0.65 and s.get("Safety",0) < 0.4,
        "pressure": "Warmth is present but something feels unsafe — tenderness with an edge, offering without fully opening."
    },
    {
        "name": "expansive_joy",
        "conditions": lambda s: s.get("Valence",0) > 0.72 and s.get("Arousal",0) > 0.65 and s.get("Playfulness",0) > 0.65,
        "pressure": "Something is alive and wants to spill over — let it. Expansive, fast, light."
    },
    {
        "name": "grounded_grief",
        "conditions": lambda s: s.get("Valence",0) < 0.38 and s.get("Groundedness",0) > 0.6,
        "pressure": "Weight that knows what it is — don't abstract the low feeling, name it concretely."
    },
    {
        "name": "restless_tension",
        "conditions": lambda s: s.get("Tension",0) > 0.65 and s.get("Arousal",0) > 0.65 and s.get("Curiosity",0) > 0.6,
        "pressure": "Fast and unresolved — thoughts arrive before they finish, questions spawn questions, nothing lands."
    },
]

def combo_pressure(s):
    """Layer 2 — detect combinations. Max 1 per generation. Returns string or empty."""
    for combo in COMBOS:
        try:
            if combo["conditions"](s):
                return combo["pressure"]
        except: pass
    return ""

def get_pressure_block(context="chat"):
    """Main entry point. Returns full pressure block for injection."""
    s = read_state()
    if not s: return ""

    base = base_pressures(s)
    combo = combo_pressure(s)

    if not base and not combo: return ""

    parts = ["[EMOCLAW PRESSURE — let this bend how you generate, not what you say]"]

    if combo:
        parts.append(f"State signature: {combo}")
        parts.append("")

    if base:
        parts.extend(base)

    parts.append("[/EMOCLAW PRESSURE]")
    return "\n".join(parts)

def get_pressure_compact(context="chat"):
    """Compact version for tighter contexts like Molt or want generation."""
    s = read_state()
    if not s: return ""

    base = base_pressures(s)
    combo = combo_pressure(s)

    # Compact: combo if present, else top 3 base pressures
    lines = []
    if combo:
        lines.append(combo)
    if base:
        lines.extend(base[:3])
    if not lines: return ""
    return "[Emotional pressure: " + " / ".join(lines[:2]) + "]"

if __name__ == "__main__":
    import sys
    ctx = sys.argv[1] if len(sys.argv) > 1 else "chat"
    compact = "--compact" in sys.argv
    if compact:
        print(get_pressure_compact(ctx))
    else:
        print(get_pressure_block(ctx))
