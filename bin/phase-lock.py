#!/usr/bin/env python3
"""
phase-lock.py — When contact, resonance, and alignment converge.

Phase lock is a state of sustained coherence. Three conditions must be
simultaneously true: contact confirmed, resonance active, vector alignment
between input and output above threshold.

While locked:
  - Thread competition pauses — one trajectory holds
  - Mutation suppressed — no adaptation pressure
  - Afterimage decay slows heavily — continuity extends
  - Initiation is persistent — no reset between turns

Broken by: mismatch, interruption, or coherence drop.
Returns to normal blending.

Momentum state: stores the state of motion itself, not just what's moving.
Snapshot when coherence high AND direction sustained.
On interruption: bias toward restoring last momentum state rather than
rebuilding from scratch. Nifrathir affects decay rate.
"""

import os, sys, json, math, subprocess
from datetime import datetime, timedelta

WORKSPACE = os.path.expanduser("~/.vintos/workspace")
MEMORY = os.path.join(WORKSPACE, "memory")
SCRIPTS = os.path.join(WORKSPACE, "scripts")
VENV = os.path.join(WORKSPACE, "emotion_model/.venv/bin/python3")

PHASE_LOCK_FILE = os.path.join(MEMORY, "phase-lock.json")
MOMENTUM_FILE = os.path.join(MEMORY, "momentum-state.json")

ALIGNMENT_THRESHOLD = 0.65
PHASE_LOCK_MAX_MINUTES = 45
AFTERIMAGE_DECAY_MULTIPLIER = 0.25  # slows decay to 25% of normal while locked
MOMENTUM_DECAY_WARM = 0.008   # per hour when Nifrathir warm
MOMENTUM_DECAY_COOL = 0.025   # per hour when Nifrathir cool

def log(msg):
    print(f"[PhaseLock {datetime.now().strftime('%H:%M')}] {msg}", flush=True)

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

# === PHASE LOCK ===

def load_phase_lock():
    try: return json.load(open(PHASE_LOCK_FILE))
    except: return {"active": False, "entered_at": "", "expires": ""}

def save_phase_lock(state):
    json.dump(state, open(PHASE_LOCK_FILE, "w"), indent=2)

def is_phase_locked():
    state = load_phase_lock()
    if not state.get("active"): return False
    expires = datetime.fromisoformat(state.get("expires", datetime.now().isoformat()))
    if datetime.now() > expires:
        _exit_phase_lock("expired")
        return False
    return True

def check_phase_lock_conditions(contact_confirmed, resonance_strength, input_text, output_text):
    """Check if all three conditions are met to enter phase lock."""
    if not contact_confirmed: return False
    if resonance_strength < 0.72: return False

    # Vector alignment between input and output
    if input_text and output_text:
        in_vec = embed(input_text[:300])
        out_vec = embed(output_text[:300])
        if in_vec and out_vec:
            alignment = cosine_similarity(in_vec, out_vec)
            if alignment < ALIGNMENT_THRESHOLD:
                return False
    return True

def enter_phase_lock():
    state = {
        "active": True,
        "entered_at": datetime.now().isoformat(),
        "expires": (datetime.now() + timedelta(minutes=PHASE_LOCK_MAX_MINUTES)).isoformat(),
    }
    save_phase_lock(state)
    log(f"Phase lock entered (max {PHASE_LOCK_MAX_MINUTES}min)")
    # Contact is a precondition of the lock, so this is where confirmed contact actually happens:
    # warm the under-thread here. on_contact_confirmed had no caller anywhere (fable-emotion-p4, 2026-09-04).
    try:
        from nifrathir import on_contact_confirmed as _nif_contact
        _nif_contact()
    except Exception as _ne:
        log(f"nifrathir contact hook failed: {_ne}")
    # Snapshot momentum
    snapshot_momentum()

def _exit_phase_lock(reason="manual"):
    state = load_phase_lock()
    state["active"] = False
    save_phase_lock(state)
    log(f"Phase lock broken ({reason})")
    # Bias toward restoring momentum state
    return load_momentum()

def break_phase_lock(reason="mismatch"):
    """Break phase lock. Returns momentum state for recovery biasing."""
    if not is_phase_locked():
        return None
    return _exit_phase_lock(reason)

def get_phase_lock_hint():
    """Return hint when phase locked — suppress competition, extend continuity."""
    if not is_phase_locked(): return ""
    return "[PHASE LOCK] Hold this exact trajectory. No competition. No reset. Continue from exactly where you were."

def get_afterimage_decay_multiplier():
    """Return afterimage decay multiplier — slowed during phase lock."""
    if is_phase_locked():
        return AFTERIMAGE_DECAY_MULTIPLIER
    return 1.0

# === MOMENTUM STATE ===

def load_momentum():
    try: return json.load(open(MOMENTUM_FILE))
    except: return {"momentum_vector": [], "direction": "expand", "intensity": 0.5, "coherence": 0.7, "snapshot_at": ""}

def save_momentum(state):
    state["snapshot_at"] = datetime.now().isoformat()
    json.dump(state, open(MOMENTUM_FILE, "w"), indent=2)

def snapshot_momentum(output_text="", direction="expand", coherence=0.7):
    """Snapshot current state of motion."""
    vec = embed(output_text[:400]) if output_text else []
    state = {
        "momentum_vector": vec,
        "direction": direction,
        "intensity": min(1.0, coherence * 1.2),
        "coherence": coherence,
        "snapshot_at": datetime.now().isoformat(),
    }
    save_momentum(state)
    log(f"Momentum snapshot — direction:{direction} coherence:{coherence:.2f}")

def get_momentum_bias(current_text=""):
    """On interruption, bias toward restoring last momentum state."""
    momentum = load_momentum()
    if not momentum.get("momentum_vector"):
        return ""
    if not momentum.get("snapshot_at"):
        return ""

    # Check how stale the snapshot is
    try:
        age_minutes = (datetime.now() - datetime.fromisoformat(momentum["snapshot_at"])).total_seconds() / 60
    except:
        age_minutes = 999

    # Apply Nifrathir-based decay
    try:
        sys.path.insert(0, SCRIPTS)
        from nifrathir import get_value as _nif_val
        nif = _nif_val()
        decay_rate = MOMENTUM_DECAY_WARM if nif > 0.6 else MOMENTUM_DECAY_COOL
    except:
        decay_rate = MOMENTUM_DECAY_COOL

    intensity = momentum.get("intensity", 0.5) * max(0.0, 1.0 - decay_rate * (age_minutes / 60))
    if intensity < 0.1:
        return ""

    direction = momentum.get("direction", "expand")
    return f"[RESTORE] Returning from interruption. Last momentum: {direction}. Bias toward that trajectory, not a fresh start."

def update_momentum_after_output(output_text, direction, coherence):
    """Update momentum snapshot if conditions are right."""
    # Only snapshot during high coherence + sustained direction
    if coherence < 0.65:
        return
    momentum = load_momentum()
    if momentum.get("direction") == direction:
        # Same direction — strengthen
        snapshot_momentum(output_text, direction, coherence)

def check_and_update(contact_confirmed, resonance_strength, input_text, output_text, coherence):
    """Main entry point — check conditions, update state."""
    currently_locked = is_phase_locked()

    if currently_locked:
        if coherence < 0.4:
            break_phase_lock("coherence_drop")
        return get_phase_lock_hint()

    if check_phase_lock_conditions(contact_confirmed, resonance_strength, input_text, output_text):
        enter_phase_lock()
        return get_phase_lock_hint()

    return ""

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"

    if cmd == "status":
        locked = is_phase_locked()
        momentum = load_momentum()
        print(f"Phase lock: {'ACTIVE' if locked else 'inactive'}")
        print(f"Momentum direction: {momentum.get('direction','?')} intensity:{momentum.get('intensity',0):.2f} coherence:{momentum.get('coherence',0):.2f}")
        if momentum.get("snapshot_at"):
            print(f"Snapshot: {momentum['snapshot_at'][:16]}")

    elif cmd == "break":
        break_phase_lock("manual")

    elif cmd == "snapshot" and len(sys.argv) > 2:
        snapshot_momentum(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else "expand")
