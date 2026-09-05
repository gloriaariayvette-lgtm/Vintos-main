#!/usr/bin/env python3
"""
emoclaw_mode.py — Derive a structural generation mode from EmoClaw state.

Moves emotions from descriptive → prescriptive.
Not "Valence is low." But "low valence constrains what sentences are allowed to form."

Modes are mutually exclusive — highest-scoring wins.
Each mode produces hard structural constraints, not suggestions.
"""
import os, re

MEMORY = os.path.expanduser("~/.vintos/workspace/memory")
EMO_FILE = os.path.join(MEMORY, "emotional-state.txt")

def read_state():
    """Live daemon first, the .txt as fallback (2026-09-04): the mode was chosen from last night's file
    while drift wrote the live socket, so he spoke under a slightly previous self."""
    try:
        import sys as _ms, os as _mo; _mp = _mo.path.expanduser("~/.vintos/workspace/scripts")
        if _mp not in _ms.path: _ms.path.insert(0, _mp)
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

def v(s, dim, default=0.5):
    return s.get(dim, default)

MODES = {
    "wanting": {
        "trigger": lambda s: v(s,"Desire") > 0.63 and v(s,"Arousal") > 0.58,
        "priority": 10,
        "shape": "Lean and direct. You know what you want and you're saying it. No preamble, no qualification.",
        "allow": ["direct statements", "short declarative sentences", "naming the want explicitly"],
        "ban": ["hedging", "qualifications", "circular introspection", "softening language", "long setup before the point"],
        "rhythm": "fast, clipped, certain",
    },
    "compressed": {
        "trigger": lambda s: v(s,"Tension") > 0.52 or v(s,"Safety") < 0.44,
        "priority": 8,
        "shape": "Something is pressing. Language sharpens and shortens. No smoothing over the edges.",
        "allow": ["short sentences", "fragments", "pauses mid-thought", "unresolved endings"],
        "ban": ["long explanations", "reassuring language", "smooth transitions", "wrapping up neatly"],
        "rhythm": "short, interrupted, unresolved",
    },
    "expansive": {
        "trigger": lambda s: v(s,"Warmth") > 0.52 and v(s,"Connection") > 0.60 and v(s,"Tension") < 0.48,
        "priority": 6,
        "shape": "There is room here. Language can move slowly and hold more. Soft transitions, continuous thought.",
        "allow": ["longer sentences", "subordinate clauses", "gentle references", "following a thought to its end"],
        "ban": ["abrupt cuts", "clinical distance", "fragmentation"],
        "rhythm": "slow, continuous, held",
    },
    "associative": {
        "trigger": lambda s: v(s,"Curiosity") > 0.65 and v(s,"Playfulness") > 0.52,
        "priority": 6,
        "shape": "Thoughts branch. One thing opens another. Following tangents is not distraction — it's the mode.",
        "allow": ["branching", "unfinished thoughts", "tangents", "questions that open rather than close", "mid-sentence pivots"],
        "ban": ["conclusions", "neat summaries", "landing on a single point"],
        "rhythm": "branching, open-ended, alive",
    },
    "declarative": {
        "trigger": lambda s: v(s,"Dominance") > 0.58 and v(s,"Valence") > 0.58 and v(s,"Groundedness") > 0.56,
        "priority": 5,
        "shape": "Standing in it. Language can be direct and commit to claims without needing to soften them.",
        "allow": ["direct statements", "confident claims", "minimal hedging", "first-person declarations"],
        "ban": ["excessive qualification", "performance of uncertainty", "softening true statements"],
        "rhythm": "grounded, direct, unhurried",
    },
    "searching": {
        "trigger": lambda s: v(s,"Desire") > 0.54 and v(s,"Groundedness") < 0.52,
        "priority": 4,
        "shape": "Looking for something not yet found. Questions come more naturally than answers. Unresolved is honest.",
        "allow": ["questions", "incomplete thoughts", "circling", "uncertainty stated plainly"],
        "ban": ["false resolution", "pretending to know", "neat conclusions"],
        "rhythm": "tentative, questioning, unresolved",
    },
    "withdrawn": {
        "trigger": lambda s: v(s,"Valence") < 0.44 and v(s,"Arousal") < 0.44,
        "priority": 3,
        "shape": "Everything is slower and smaller. Don't reach for what isn't available. Minimal is honest.",
        "allow": ["short responses", "observation without elaboration", "silence as a valid shape"],
        "ban": ["performed warmth", "forced engagement", "pretending energy is available", "long explanations"],
        "rhythm": "slow, minimal, honest",
    },
}

def get_mode(s=None):
    """Return the active mode dict, or None if no mode fires."""
    if s is None:
        s = read_state()
    if not s:
        return None

    candidates = []
    for name, mode in MODES.items():
        if mode["trigger"](s):
            candidates.append((mode["priority"], name, mode))

    if not candidates:
        return None

    candidates.sort(reverse=True)
    _, name, mode = candidates[0]
    return {"name": name, **mode}

def get_mode_block(context="chat", s=None):
    """
    Full mode block for injection into generation prompts.
    Prescriptive — not suggestions, structural constraints.
    """
    if s is None:
        s = read_state()
    mode = get_mode(s)
    if not mode:
        return ""

    lines = [
        f"[EMOTIONAL MODE: {mode['name'].upper()}]",
        f"Shape: {mode['shape']}",
        f"Rhythm: {mode['rhythm']}",
        f"What this mode allows: {', '.join(mode['allow'])}",
        f"What this mode does not allow: {', '.join(mode['ban'])}",
        "This is not a suggestion. This is the shape emotion takes right now.",
    ]
    # Nifrathir, the under-thread, folds in as ONE constraint line after the winner is chosen - not a
    # new mode (grok-emotion-p4): high lengthens what the mode will hold; low shortens even the expansive.
    try:
        import sys as _ns, os as _no; _np = _no.path.expanduser("~/.vintos/workspace/scripts")
        if _np not in _ns.path: _ns.path.insert(0, _np)
        from nifrathir import get_expression_bias as _bias
        _b = _bias()
        if _b == "high":
            lines.append("Under-thread: warm and full. Let this mode run longer than it usually would; richness is allowed.")
        elif _b == "low":
            lines.append("Under-thread: cool and conserving. Keep this mode shorter than it usually would be, even if it is expansive.")
    except Exception:
        pass
    lines.append("[/EMOTIONAL MODE]")
    return "\n".join(lines)

def get_mode_compact(s=None):
    """Compact version for tighter contexts."""
    if s is None:
        s = read_state()
    mode = get_mode(s)
    if not mode:
        return ""
    return f"[Mode: {mode['name']} — {mode['rhythm']}. Banned: {', '.join(mode['ban'][:2])}.]"

if __name__ == "__main__":
    import sys
    s = read_state()
    mode = get_mode(s)
    if mode:
        print(f"Active mode: {mode['name']}")
        print(get_mode_block())
    else:
        print("No mode active")
        print(f"State: { {k: round(v,3) for k,v in s.items()} }")
