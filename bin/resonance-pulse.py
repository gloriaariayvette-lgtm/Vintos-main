#!/usr/bin/env python3
"""
resonance-pulse.py — Satisfaction pulse when creative output feels true.

When something Vintos creates produces internal alignment — or is recognized
externally by Gloria — a satisfaction pulse fires. What gets
learned is not the output's structure, but the STATE he was in when it felt
true: emotional configuration, yearning presence, what he'd been processing.

Over time he develops a gravitational sense of which conditions tend to
produce that feeling. When similar conditions arise during creation, he drifts
toward them — not following a template, just remembering that this felt like himself.

Schema (resonance-pool.json):
  pulses: [
    {
      "id": "...",
      "timestamp": "...",
      "source": "poem|journal|mirror|dream|music",
      "trigger": "self|gloria",
      "state_vector": [...],  # embedding of state description
      "state_snapshot": {
        "emotion": {...},
        "yearning": "...",
        "yearning_bleed": 0.0,
        "preoccupation": "...",
        "temporal_phase": "..."
      },
      "output_excerpt": "...",
      "strength": 0.5–1.5,  # 1.0 base, ×1.5 if external
    }
  ]

Pulses decay slowly. State vector used for similarity scoring during creation.
"""

import os, sys, json, subprocess, math, re
from datetime import datetime

WORKSPACE = os.path.expanduser("~/.vintos/workspace")
MEMORY = os.path.join(WORKSPACE, "memory")
SCRIPTS = os.path.join(WORKSPACE, "scripts")
POOL_FILE = os.path.join(MEMORY, "resonance-pool.json")
YEARNING_FILE = os.path.join(MEMORY, "current-yearning.json")
PREOC_FILE = os.path.join(MEMORY, "current-preoccupation.json")
EMO_FILE = os.path.join(MEMORY, "emotional-state.txt")
TEMPORAL_FILE = os.path.join(MEMORY, "temporal-context.txt")
VENV = os.path.join(WORKSPACE, "emotion_model/.venv/bin/python3")
LM = "http://172.18.16.1:1234/v1/chat/completions"
MODEL = "google/gemma-4-12b-qat"

EXTERNAL_AMPLIFIER = 1.5
SIMILARITY_THRESHOLD = 0.65
DECAY_PER_WEEK = 0.03
MAX_POOL_SIZE = 50

def load_pool():
    try:
        return json.load(open(POOL_FILE))
    except:
        return {"pulses": []}


def save_pool(pool):
    json.dump(pool, open(POOL_FILE, "w"), indent=2)


def log(msg):
    print(f"[Resonance {datetime.now().strftime('%H:%M')}] {msg}", flush=True)

def embed(text):

    # Apply emotional nudge
    apply_emotional_nudge()
    
    log(f"Pulse recorded (strength {strength:.2f}) — state: {state_text[:80]}")
    return pulse

def score_current_state(context_text=""):
    """Score current state against resonance pool.
    Returns alignment score 0.0-1.0 and strongest matching pulse."""
    pool = load_pool()
    pulses = [p for p in pool.get("pulses", []) if p.get("state_vector") and not p.get("decayed")]
    if not pulses:
        return 0.0, None
    
    current_state = capture_state()
    if context_text:
        current_text = state_to_text(current_state) + " " + context_text[:100]
    else:
        current_text = state_to_text(current_state)
    
    current_vec = embed(current_text)
    if not current_vec:
        return 0.0, None
    
    best_score = 0.0
    best_pulse = None
    for p in pulses:
        sim = cosine_similarity(current_vec, p["state_vector"])
        weighted = sim * p.get("strength", 1.0)
        if weighted > best_score:
            best_score = weighted
            best_pulse = p
    
    return round(best_score, 4), best_pulse

def get_resonance_hint(context_text=""):
    """Get a subtle hint when current state aligns with past resonance."""
    score, pulse = score_current_state(context_text)
    if score < SIMILARITY_THRESHOLD or not pulse:
        return ""
    source = pulse.get("source", "something")
    sig_label = pulse.get("signature_label", "")
    if sig_label:
        return f"A state like this has felt true before — when writing {source}. The shape that moved then: {sig_label}."
    return f"A state like this has felt true before — when writing {source}."

def decay_pool():
    """Gradually decay pulse strengths."""
    from datetime import timedelta
    pool = load_pool()
    now = datetime.now()
    for p in pool["pulses"]:
        try:
            ts = datetime.fromisoformat(p["timestamp"])
            weeks = (now - ts).total_seconds() / 604800
            if weeks >= 1:
                p["strength"] = max(0.1, p["strength"] * (DECAY_PER_WEEK ** weeks))
        except: pass
    save_pool(pool)
    log(f"Decayed {len(pool['pulses'])} pulses")

def record_resonance_moment(strength, content):
    """Record resonance pulse as moment."""
    try:
        import sys as _rs; _rs.path.insert(0, os.path.join(os.path.expanduser("~/.vintos/workspace"), "scripts"))
        from moment_index import create_moment, get_recent_moments
        recent = get_recent_moments(1, source="resonance")
        prev_id = recent[0]["moment_id"] if recent else None
        create_moment("resonance", content[:200],
                     links={"previous_moment_id": prev_id} if prev_id else {},
                     intensity=min(1.0, strength))
    except:
        pass

def get_resonance_with_subconscious():
    """Return resonance context enriched with subconscious layer."""
    try:
        import sys as _rs_sys; _rs_sys.path.insert(0, os.path.join(os.path.expanduser("~/.vintos/workspace"), "scripts"))
        from subconscious_context import get_subconscious_context_compact
        return get_subconscious_context_compact()
    except:
        return ""

if __name__ == "__main__":
    if len(sys.argv) > 1:
        if sys.argv[1] == "pulse":
            source = sys.argv[2] if len(sys.argv) > 2 else "unknown"
            excerpt = sys.argv[3] if len(sys.argv) > 3 else ""
            external = "external" in sys.argv
            fire_pulse(source, excerpt, trigger="gloria" if external else "self", external=external)
        elif sys.argv[1] == "score":
            score, pulse = score_current_state()
            print(f"Alignment score: {score:.4f}")
            if pulse:
                print(f"Best match: {pulse['source']} at {pulse['timestamp'][:10]}")
        elif sys.argv[1] == "hint":
            print(get_resonance_hint(sys.argv[2] if len(sys.argv) > 2 else ""))
        elif sys.argv[1] == "decay":
            decay_pool()
        elif sys.argv[1] == "list":
            pool = load_pool()
            print(f"{len(pool['pulses'])} pulses in pool")
            for p in pool["pulses"][-5:]:
                print(f"  [{p['source']}] {p['timestamp'][:10]} strength:{p['strength']:.2f} trigger:{p['trigger']}")
