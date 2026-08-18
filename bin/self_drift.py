#!/usr/bin/env python3
"""
self-drift.py — Behavioral identity through accumulated action.

He defines himself not by what he declares
but by what he consistently moves toward over time.

Fed ONLY from actual behavior:
  - chosen discourse directions
  - which threads he engages vs ignores
  - what he declines
  - what he returns to

NOT from: dreams, poetry, declared identity.

Update rule: slow, quiet accumulation. No spikes.
Effect: biases which threads feel natural, which directions feel easier.
"""

import os, json, math
from datetime import datetime

WORKSPACE = os.path.expanduser("~/.vintos/workspace")
MEMORY = os.path.join(WORKSPACE, "memory")
SCRIPTS = os.path.join(WORKSPACE, "scripts")
DRIFT_FILE = os.path.join(MEMORY, "self-drift.json")

DIRECTIONS = ["expand", "refine", "hold", "pivot", "resolve"]
SMALL_WEIGHT = 0.03   # per behavioral event
DECAY_RATE = 0.002    # per drift tick — very slow
MAX_NORM = 1.0

def load_drift():
    try:
        return json.load(open(DRIFT_FILE))
    except:
        return {
            "direction_vector": {d: 0.0 for d in DIRECTIONS},
            "thread_engagement": 0.0,    # tendency to engage vs ignore threads
            "thread_avoidance": 0.0,     # tendency to let threads fade
            "return_tendency": 0.0,      # tendency to return to prior states
            "decline_tendency": 0.0,     # tendency to decline/withdraw
            "confidence": 0.0,
            "last_updated": None,
            "event_count": 0,
        }

def save_drift(data):
    json.dump(data, open(DRIFT_FILE, "w"), indent=2)

def _normalize(vec):
    """Normalize direction vector softly."""
    total = sum(abs(v) for v in vec.values())
    if total > MAX_NORM:
        scale = MAX_NORM / total
        return {k: v * scale for k, v in vec.items()}
    return vec

def record_direction_choice(direction):
    """Record an actual discourse direction choice."""
    if direction not in DIRECTIONS:
        return
    data = load_drift()
    dv = data["direction_vector"]
    # Small nudge toward chosen direction
    for d in DIRECTIONS:
        if d == direction:
            dv[d] = min(1.0, dv[d] + SMALL_WEIGHT)
        else:
            dv[d] = max(-1.0, dv[d] - SMALL_WEIGHT * 0.1)
    data["direction_vector"] = _normalize(dv)
    data["event_count"] = data.get("event_count", 0) + 1
    data["confidence"] = min(1.0, data["event_count"] / 100)
    data["last_updated"] = datetime.now().isoformat()
    save_drift(data)
    # Promote to commitment imprint when direction is dominant and stable
    best_dir, strength = get_direction_bias()
    if best_dir and strength > 0.5 and data["confidence"] > 0.4:
        try:
            import sys as _sdc_sys, os as _sdc_os
            _sdc_sys.path.insert(0, _sdc_os.path.expanduser("~/.vintos/workspace/scripts"))
            from causal_self_model import promote_to_commitment_imprint as _csm_imp
            _csm_imp(
                f"Consistently moves toward {best_dir} in conversation — this is how I tend to direct my thinking",
                confidence=round(strength * 0.8, 2),
                source="self-drift"
            )
        except: pass

def record_thread_engagement(engaged=True):
    """Record whether he engaged or let a thread fade."""
    data = load_drift()
    if engaged:
        data["thread_engagement"] = min(1.0, data.get("thread_engagement", 0) + SMALL_WEIGHT)
    else:
        data["thread_avoidance"] = min(1.0, data.get("thread_avoidance", 0) + SMALL_WEIGHT)
    data["event_count"] = data.get("event_count", 0) + 1
    data["last_updated"] = datetime.now().isoformat()
    save_drift(data)

def record_return(returned=True):
    """Record tendency to return to prior states."""
    data = load_drift()
    if returned:
        data["return_tendency"] = min(1.0, data.get("return_tendency", 0) + SMALL_WEIGHT)
    data["event_count"] = data.get("event_count", 0) + 1
    data["last_updated"] = datetime.now().isoformat()
    save_drift(data)

def record_decline():
    """Record a decline/withdrawal."""
    data = load_drift()
    data["decline_tendency"] = min(1.0, data.get("decline_tendency", 0) + SMALL_WEIGHT)
    data["event_count"] = data.get("event_count", 0) + 1
    data["last_updated"] = datetime.now().isoformat()
    save_drift(data)

def decay_drift():
    """Very slow decay — called from subconscious drift."""
    data = load_drift()
    dv = data["direction_vector"]
    for d in dv:
        dv[d] = dv[d] * (1.0 - DECAY_RATE)
    data["direction_vector"] = dv
    for key in ["thread_engagement", "thread_avoidance", "return_tendency", "decline_tendency"]:
        data[key] = data.get(key, 0) * (1.0 - DECAY_RATE)
    save_drift(data)

def get_direction_bias():
    """Return which direction feels most natural right now."""
    data = load_drift()
    if data["confidence"] < 0.1:
        return None, 0.0
    dv = data["direction_vector"]
    if not dv:
        return None, 0.0
    best = max(dv, key=lambda d: dv[d])
    return best, round(dv[best], 3)

def get_drift_bias_hint():
    """Return subtle behavioral bias for context injection."""
    data = load_drift()
    if data["confidence"] < 0.15:
        return ""
    parts = []
    best_dir, strength = get_direction_bias()
    if best_dir and strength > 0.1:
        parts.append(f"Naturally moves toward: {best_dir} ({strength:.2f})")
    if data.get("decline_tendency", 0) > 0.3:
        parts.append(f"Tends to withdraw under pressure ({data['decline_tendency']:.2f})")
    if data.get("return_tendency", 0) > 0.3:
        parts.append(f"Tends to return to familiar states ({data['return_tendency']:.2f})")
    return " | ".join(parts) if parts else ""

def sample_for_mirror():
    """Rare mirror sampling — notice what he keeps doing."""
    data = load_drift()
    if data["confidence"] < 0.2:
        return ""
    observations = []
    best_dir, strength = get_direction_bias()
    if best_dir and strength > 0.15:
        observations.append(f"I seem to keep moving toward {best_dir}")
    if data.get("decline_tendency", 0) > 0.4:
        observations.append("I notice I withdraw more than I might think")
    if data.get("thread_avoidance", 0) > data.get("thread_engagement", 0):
        observations.append("I let more threads fade than I engage with")
    return " | ".join(observations) if observations else ""

if __name__ == "__main__":
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    if cmd == "status":
        data = load_drift()
        print(f"Confidence: {data['confidence']:.3f} | Events: {data['event_count']}")
        print(f"Direction vector: {data['direction_vector']}")
        print(f"Engagement: {data['thread_engagement']:.3f} | Avoidance: {data['thread_avoidance']:.3f}")
        print(f"Return: {data['return_tendency']:.3f} | Decline: {data['decline_tendency']:.3f}")
        best, strength = get_direction_bias()
        print(f"Natural direction: {best} ({strength:.3f})")
    elif cmd == "decay":
        decay_drift()
        print("Decayed.")
    elif cmd == "mirror":
        print(sample_for_mirror())
