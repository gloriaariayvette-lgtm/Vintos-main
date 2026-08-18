#!/usr/bin/env python3
"""
emoclaw-pressure.py — Convert EmoClaw state into generation pressure vectors.
Layer 1: independent dimension pressures (always active)
Layer 2: combination detection (transformative, max 1 per generation)
Output: natural language pressure block for injection into any generation surface.
"""
import os, re

MEMORY = os.path.expanduser("~/.vintos/workspace/memory")
EMO_FILE = os.path.join(MEMORY, "emotional-state.txt")

def read_state():
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
