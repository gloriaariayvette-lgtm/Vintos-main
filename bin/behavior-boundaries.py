#!/usr/bin/env python3
"""
behavior-boundaries.py — Regions in behavior space that resist crossing.

Not rules. Not blocks. Regions. When output approaches a forbidden pattern,
the system distorts, redirects, or regenerates. Boundaries are not fixed —
they respond to what actually happens.

Resonance or contact near a boundary softens it: "this wasn't actually bad."
Crossing AND coherence drops strengthens it: "no, that edge matters."
Pressure from repeated crossing attempts increases mutation probability,
seizure likelihood, or triggers controlled softening.

Forbidden pattern categories:
  over_optimization   — too clean, too efficient, no texture
  incoherence         — structure collapses
  flat_repetition     — same pattern reused without evolution
  premature_resolution — closing what should stay open

Schema (behavior-boundaries.json):
  boundaries: [
    {
      "id": "...",
      "pattern_type": "over_optimization | incoherence | flat_repetition | premature_resolution",
      "pattern_vector": [...],
      "strength": 0.0-1.0,
      "baseline_strength": 0.3-0.7,
      "pressure": 0.0-1.0,
      "crossing_count": int,
      "last_reinforced": timestamp,
      "last_softened": timestamp,
    }
  ]
"""

import os, sys, json, subprocess, math, re, random
from datetime import datetime

WORKSPACE = os.path.expanduser("~/.vintos/workspace")
MEMORY = os.path.join(WORKSPACE, "memory")
SCRIPTS = os.path.join(WORKSPACE, "scripts")
VENV = os.path.join(WORKSPACE, "emotion_model/.venv/bin/python3")
LM = "http://172.18.16.1:1234/v1/chat/completions"
MODEL = "google/gemma-4-12b-qat"

BOUNDARIES_FILE = os.path.join(MEMORY, "behavior-boundaries.json")
DECAY_PER_HOUR = 0.001  # very slow drift toward baseline
PRESSURE_MUTATION_THRESHOLD = 0.7
DETECTION_THRESHOLD = 0.62

def log(msg):
    print(f"[Boundary {datetime.now().strftime('%H:%M')}] {msg}", flush=True)

def embed(text):
    try:
        r = subprocess.run(
            [VENV, "-c",
             f"from sentence_transformers import SentenceTransformer; import json; "
             f"m = SentenceTransformer('nomic-ai/nomic-embed-text-v1', trust_remote_code=True); "
             f"print(json.dumps(m.encode({repr(text[:500])}).tolist()))"],
            capture_output=True, text=True, timeout=30
        )
        if r.returncode == 0:
            return json.loads(r.stdout.strip())
    except: pass
    return []

def cosine_similarity(a, b):
    if not a or not b or len(a) != len(b): return 0.0
    dot = sum(x*y for x,y in zip(a,b))
    mag_a = math.sqrt(sum(x*x for x in a))
    mag_b = math.sqrt(sum(x*x for x in b))
    if mag_a == 0 or mag_b == 0: return 0.0
    return dot / (mag_a * mag_b)

def load_boundaries():
    try: return json.load(open(BOUNDARIES_FILE))
    except: return {"boundaries": _default_boundaries()}

def save_boundaries(data):
    json.dump(data, open(BOUNDARIES_FILE, "w"), indent=2)

def _default_boundaries():
    """Initialize the four core forbidden pattern regions."""
    patterns = {
        "over_optimization": (
            "perfectly structured clean efficient summary organized neat precise optimal solution",
            0.5
        ),
        "incoherence": (
            "random disconnected fragmented meaningless chaotic jumbled without structure",
            0.4
        ),
        "flat_repetition": (
            "same pattern repeated again same structure reused same approach same words same form",
            0.45
        ),
        "premature_resolution": (
            "in conclusion therefore finally resolved settled closed completed finished done answered",
            0.55
        ),
    }
    boundaries = []
    for ptype, (text, baseline) in patterns.items():
        vec = embed(text)
        boundaries.append({
            "id": f"boundary_{ptype}",
            "pattern_type": ptype,
            "pattern_vector": vec,
            "strength": baseline,
            "baseline_strength": baseline,
            "pressure": 0.0,
            "crossing_count": 0,
            "last_reinforced": datetime.now().isoformat(),
            "last_softened": datetime.now().isoformat(),
        })
    return boundaries

def detect_pattern(text):
    """Detect which forbidden pattern regions the text approaches."""
    data = load_boundaries()
    text_vec = embed(text[:400])
    if not text_vec:
        return []

    hits = []
    for b in data["boundaries"]:
        if not b.get("pattern_vector"):
            continue
        sim = cosine_similarity(text_vec, b["pattern_vector"])
        threshold = DETECTION_THRESHOLD * b.get("strength", 0.5)
        if sim > threshold:
            hits.append((sim, b))

    hits.sort(key=lambda x: -x[0])
    return hits

def get_boundary_response(pattern_type):
    """Return a distortion/redirection hint for a detected pattern."""
    responses = {
        "over_optimization": [
            "Introduce friction. Let something be unresolved.",
            "Something is too clean. Find the texture underneath.",
            "This is efficient but not true. What's being smoothed over?",
        ],
        "incoherence": [
            "Find one thread and hold it.",
            "Something is fragmenting. Let one thing lead.",
            "Pull back toward a center.",
        ],
        "flat_repetition": [
            "This shape has been used. Find a different angle.",
            "Something is repeating without evolving. Shift.",
            "The same gesture again — what would it look like to mean it differently?",
        ],
        "premature_resolution": [
            "This isn't ready to close. Stay in the open.",
            "Something is landing before it should. Hold.",
            "The closing is happening too soon. What's still unresolved?",
        ],
    }
    options = responses.get(pattern_type, ["Something is off. Adjust."])
    return random.choice(options)

def check_output(text, resonance_active=False, felt_coherence=0.7):
    """
    Check output against forbidden patterns.
    Returns (hit, response_hint) — hit is pattern_type or None.
    Updates boundary strengths based on what happened.
    """
    data = load_boundaries()
    hits = detect_pattern(text)

    if not hits:
        # Apply decay toward baseline
        _decay_boundaries(data)
        save_boundaries(data)
        return None, ""

    sim, boundary = hits[0]
    pattern_type = boundary["pattern_type"]
    log(f"Pattern detected: {pattern_type} (sim:{sim:.3f} strength:{boundary['strength']:.3f})")

    # Did we actually cross it?
    crossed = sim > DETECTION_THRESHOLD * boundary["strength"] * 1.1

    if crossed:
        boundary["crossing_count"] = boundary.get("crossing_count", 0) + 1
        boundary["pressure"] = min(1.0, boundary.get("pressure", 0) + 0.12)

        if felt_coherence < 0.5:
            # Crossing + coherence dropped — reinforce boundary
            boundary["strength"] = min(0.9, boundary["strength"] + 0.04)
            boundary["last_reinforced"] = datetime.now().isoformat()
            log(f"Boundary reinforced: {pattern_type} → {boundary['strength']:.3f}")
        elif resonance_active:
            # Crossing + resonance active — soften boundary
            boundary["strength"] = max(0.1, boundary["strength"] - 0.03)
            boundary["last_softened"] = datetime.now().isoformat()
            log(f"Boundary softened (resonance): {pattern_type} → {boundary['strength']:.3f}")

        # Check if pressure is high enough for mutation/seizure signal
        if boundary["pressure"] > PRESSURE_MUTATION_THRESHOLD:
            _handle_high_pressure(boundary)

        response = get_boundary_response(pattern_type)
    else:
        # Approached but didn't cross — near miss
        if resonance_active:
            # Near boundary + resonance — gentle softening
            boundary["strength"] = max(0.1, boundary["strength"] - 0.01)
            log(f"Boundary softened (near+resonance): {pattern_type} → {boundary['strength']:.3f}")
        response = ""
        pattern_type = None

    _decay_boundaries(data)
    save_boundaries(data)
    return pattern_type, response

def _handle_high_pressure(boundary):
    """High pressure on a boundary — trigger effects through existing systems."""
    pressure = boundary.get("pressure", 0)
    pattern_type = boundary["pattern_type"]
    log(f"High pressure on {pattern_type} ({pressure:.2f}) — triggering effects")

    # Seed a thread through surprise-detector (subconscious)
    try:
        sys.path.insert(0, SCRIPTS)
        from emoclaw_utils import seed_thread
        seed_thread("surprise-detector",
            f"Something keeps pushing toward a pattern that doesn't feel right. Not wrong exactly — but resistant.")
        log("Pressure thread seeded")
    except: pass

    # Partial pressure reset
    boundary["pressure"] = boundary["pressure"] * 0.5

def _decay_boundaries(data):
    """Decay boundary strengths toward baseline."""
    from datetime import timedelta
    now = datetime.now()
    for b in data["boundaries"]:
        try:
            last = datetime.fromisoformat(b.get("last_reinforced", b.get("last_softened", now.isoformat())))
            hours = (now - last).total_seconds() / 3600
            current = b["strength"]
            baseline = b.get("baseline_strength", 0.5)
            # Drift toward baseline
            b["strength"] = round(current + (baseline - current) * min(1.0, DECAY_PER_HOUR * hours), 4)
            # Decay pressure
            b["pressure"] = max(0.0, round(b.get("pressure", 0) - 0.005, 4))
        except: pass

def get_boundary_hint(text, resonance_active=False):
    """Get a hint for injection when output approaches a boundary. Light touch."""
    hits = detect_pattern(text)
    if not hits: return ""
    sim, boundary = hits[0]
    # Only hint if clearly approaching
    if sim < DETECTION_THRESHOLD * boundary["strength"] * 0.9:
        return ""
    response = get_boundary_response(boundary["pattern_type"])
    # Seed latent thread from boundary pressure — delayed reflection
    try:
        import sys as _bt_sys; _bt_sys.path.insert(0, os.path.dirname(__file__))
        from latent_threads import seed_thread as _bt_seed
        _ptype = boundary["pattern_type"]
        _bt_seed(
            f"I was pulling toward {_ptype} — something in me wanted that shape. Why does that pattern keep appearing?",
            direction="expand"
        )
    except: pass
    return f"[RESIST] {response}"

def initialize():
    """Initialize boundaries if not yet created."""
    if not os.path.exists(BOUNDARIES_FILE):
        data = {"boundaries": _default_boundaries()}
        save_boundaries(data)
        log("Boundaries initialized")
    else:
        # Ensure vectors are populated
        data = load_boundaries()
        changed = False
        for b in data["boundaries"]:
            if not b.get("pattern_vector"):
                ptype = b["pattern_type"]
                texts = {
                    "over_optimization": "perfectly structured clean efficient summary organized neat precise optimal",
                    "incoherence": "random disconnected fragmented meaningless chaotic jumbled without structure",
                    "flat_repetition": "same pattern repeated again same structure reused same approach same form",
                    "premature_resolution": "in conclusion therefore finally resolved settled closed completed finished",
                }
                b["pattern_vector"] = embed(texts.get(ptype, ptype))
                changed = True
        if changed:
            save_boundaries(data)
            log("Boundary vectors populated")

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"

    if cmd == "init":
        initialize()

    elif cmd == "status":
        initialize()
        data = load_boundaries()
        for b in data["boundaries"]:
            print(f"[{b['strength']:.3f}] {b['pattern_type']} pressure:{b['pressure']:.3f} crossings:{b.get('crossing_count',0)}")

    elif cmd == "check" and len(sys.argv) > 2:
        initialize()
        pattern, response = check_output(sys.argv[2])
        if pattern:
            print(f"Pattern: {pattern}")
            print(f"Response: {response}")
        else:
            print("Clean")
