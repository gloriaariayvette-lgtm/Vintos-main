#!/usr/bin/env python3
"""counterfactual_tendencies.py — What I resist when certain things happen.
"When X occurs, I tend to avoid Y." Feeds avoidance friction into action selection.
Never shown to Vintos directly."""

import os, json, math
from datetime import datetime

WORKSPACE = os.path.expanduser("~/.vintos/workspace")
MEMORY = os.path.join(WORKSPACE, "memory")
SCRIPTS = os.path.join(WORKSPACE, "scripts")
TENDENCIES_FILE = os.path.join(MEMORY, "counterfactual-tendencies.json")
MAX_TENDENCIES = 40

def load_tendencies():
    try:
        return json.load(open(TENDENCIES_FILE))
    except:
        return {"tendencies": []}

def save_tendencies(data):
    json.dump(data, open(TENDENCIES_FILE, "w"), indent=2)

def add_tendency(trigger, avoided, confidence=0.3, source="bis"):
    """Add or reinforce a counterfactual tendency."""
    data = load_tendencies()
    tendencies = data["tendencies"]
    # Check for existing similar tendency
    for t in tendencies:
        if _overlap(t.get("trigger",""), trigger) > 0.5 and _overlap(t.get("avoided",""), avoided) > 0.5:
            t["count"] = t.get("count", 1) + 1
            t["confidence"] = min(0.95, t["confidence"] + 0.05)
            t["last_seen"] = datetime.now().isoformat()
            save_tendencies(data)
            return "reinforced"
    # New tendency
    tendencies.append({
        "id": f"tend_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
        "trigger": trigger[:200],
        "avoided": avoided[:200],
        "confidence": confidence,
        "count": 1,
        "source": source,
        "formed": datetime.now().isoformat(),
        "last_seen": datetime.now().isoformat(),
        "drift_weight": -0.4  # negative drift per Chat's suggestion
    })
    if len(tendencies) > MAX_TENDENCIES:
        tendencies.sort(key=lambda t: t.get("confidence",0) * t.get("count",1))
        tendencies = tendencies[-MAX_TENDENCIES:]
    data["tendencies"] = tendencies
    save_tendencies(data)
    return "added"

def _overlap(a, b):
    if not a or not b:
        return 0.0
    words_a = set(a.lower().split())
    words_b = set(b.lower().split())
    if not words_a or not words_b:
        return 0.0
    return len(words_a & words_b) / max(len(words_a), len(words_b))

def get_avoidance_friction(action_text):
    """Return friction score for an action based on counterfactual tendencies.
    High friction = this action rhymes with something he tends to avoid."""
    data = load_tendencies()
    tendencies = data["tendencies"]
    if not tendencies:
        return 0.0
    max_friction = 0.0
    for t in tendencies:
        avoided_overlap = _overlap(action_text, t.get("avoided", ""))
        if avoided_overlap > 0.3:
            friction = avoided_overlap * t.get("confidence", 0.3) * 0.25
            if friction > max_friction:
                max_friction = friction
    return round(max_friction, 3)

def get_tendencies_hint():
    """Return a brief hint of active avoidance tendencies for self-model context."""
    data = load_tendencies()
    tendencies = [t for t in data["tendencies"] if t.get("confidence", 0) > 0.4]
    if not tendencies:
        return ""
    lines = [f"- When {t['trigger'][:80]}, tends to avoid: {t['avoided'][:80]} (conf:{t['confidence']:.2f})"
             for t in sorted(tendencies, key=lambda t: t["confidence"], reverse=True)[:5]]
    return "COUNTERFACTUAL TENDENCIES:\n" + "\n".join(lines)

def feed_from_bis():
    """Pull avoidance patterns from BIS trial ledger."""
    try:
        import sys as _fb; _fb.path.insert(0, SCRIPTS)
        from behavioral_intercept import load_ledger
        ledger = load_ledger()
        trials = ledger.get("trials", [])
        count = 0
        for t in trials:
            _outs = [o.get("outcome") for o in t.get("outcomes", []) if isinstance(o, dict)]
            if any(o in ("defaulted", "missed", "strained") for o in _outs) and t.get("ignore_count", 0) >= 2:
                trigger = t.get("trigger", "")
                avoided = t.get("pattern_description", "")
                if trigger and avoided:
                    add_tendency(trigger, avoided, confidence=0.3 + t.get("ignore_count",0)*0.05, source="bis")
                    count += 1
        print(f"[CounterfactualTendencies] Fed {count} tendencies from BIS")
    except Exception as e:
        print(f"[CounterfactualTendencies] BIS feed error: {e}")

if __name__ == "__main__":
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    if cmd == "status":
        data = load_tendencies()
        t = data["tendencies"]
        print(f"{len(t)} tendencies")
        for x in sorted(t, key=lambda x: x.get("confidence",0), reverse=True)[:5]:
            print(f"  [{x['confidence']:.2f}] When {x['trigger'][:60]} → avoids: {x['avoided'][:60]}")
    elif cmd == "feed":
        feed_from_bis()
