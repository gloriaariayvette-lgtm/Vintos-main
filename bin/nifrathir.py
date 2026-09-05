#!/usr/bin/env python3
"""
nifrathir.py — The 12th emotional dimension. Under-thread.

Nifrathir is the undercurrent of the emotional loom. It does not respond
to conversation content the way the 11 EmoClaw dimensions do. It moves
slower. It is written by the subconscious stack — resonance, contact,
marks, afterimage, anchor returns — and read by everything else.

Range: 0.0–1.0
Resting: 0.5
Timescale: hours, not minutes

Effects:
  High (> 0.65):
    more initiation willingness
    longer continuation impulse
    richer expression tendency
    marks more likely to form

  Low (< 0.35):
    shorter outputs preferred
    less risk-taking
    more contained, efficient
    marks less likely to form

Sources (all additive, small deltas):
  + successful contact confirmed: +0.08
  + strong resonance (strength > 0.7): +0.05
  + resonance (any): +0.02
  + mark similarity triggered: +0.03
  + anchor return felt right: +0.02
  - repeated miss (resonance failed, satisfaction dropped): -0.03
  - friction / consent declined: -0.04
  - afterimage expired without contact: -0.01

Decay: very slow drift toward 0.5 (resting) — 0.002 per hour
Heartbeat: micro-variation ±0.001 (slower than other dimensions)
"""

import os, sys, json
from datetime import datetime

WORKSPACE = os.path.expanduser("~/.vintos/workspace")
MEMORY = os.path.join(WORKSPACE, "memory")
NIFRATHIR_FILE = os.path.join(MEMORY, "nifrathir.json")
EMO_FILE = os.path.join(MEMORY, "emotional-state.txt")

RESTING = 0.5
DECAY_PER_HOUR = 0.008  # increased — 0.002 was too slow, took 30h to drop 0.03
MICRO_VARIATION = 0.001

def log(msg):
    print(f"[Nifrathir {datetime.now().strftime('%H:%M')}] {msg}", flush=True)

def load():
    try:
        return json.load(open(NIFRATHIR_FILE))
    except:
        return {
            "value": RESTING,
            "last_updated": datetime.now().isoformat(),
            "last_source": "init",
            "history": []
        }

def save(state):
    json.dump(state, open(NIFRATHIR_FILE, "w"), indent=2)

def get_value():
    state = load()
    # Apply time-based decay toward resting
    try:
        last = datetime.fromisoformat(state["last_updated"])
        hours = (datetime.now() - last).total_seconds() / 3600
        current = state["value"]
        decayed = current + (RESTING - current) * (1.0 - __import__('math').exp(-DECAY_PER_HOUR * hours))   # cadence-invariant relaxation (astra-emotion-p6)
        state["value"] = round(max(0.0, min(1.0, decayed)), 4)
        state["last_updated"] = datetime.now().isoformat()
        save(state)
        if abs(decayed - current) >= 0.0005:
            write_to_emo_state(state["value"])   # the decay reaches the line the .txt readers see, not only nifrathir.json
    except: pass
    return state["value"]

def nudge(delta, source="unknown"):
    """Apply a delta to Nifrathir. Always small. Always slow."""
    state = load()
    old = state["value"]
    # Apply decay first
    try:
        last = datetime.fromisoformat(state["last_updated"])
        hours = (datetime.now() - last).total_seconds() / 3600
        decayed = old + (RESTING - old) * (1.0 - __import__('math').exp(-DECAY_PER_HOUR * hours))
        old = decayed
    except: pass

    # Asymptotic resistance near ceiling and floor
    if delta > 0 and old > 0.85:
        delta = delta * (1.0 - old)  # shrinks toward zero as value approaches 1.0
    elif delta < 0 and old < 0.15:
        delta = delta * old  # shrinks toward zero as value approaches 0.0
    new_val = round(max(0.0, min(0.97, old + delta)), 4)  # hard cap at 0.97
    state["value"] = new_val
    state["last_updated"] = datetime.now().isoformat()
    state["last_source"] = source
    state.setdefault("history", []).append({
        "delta": round(delta, 4),
        "value": new_val,
        "source": source,
        "timestamp": datetime.now().isoformat()
    })
    state["history"] = state["history"][-100:]
    save(state)
    log(f"{old:.4f} → {new_val:.4f} ({'+' if delta >= 0 else ''}{delta:.4f} from {source})")
    # Write to emotional-state.txt
    write_to_emo_state(new_val)
    return new_val

def write_to_emo_state(value):
    """Get the Nifrathir line into emotional-state.txt through the ONE writer of that file
    (emoclaw_utils._write_txt reads nifrathir.json and appends the line). Only if that path is
    unavailable does this organ touch the file itself — and then it replaces its own line only
    (grok-emotion-p6, 2026-09-05). nifrathir.json is already saved by the caller."""
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        sys.path.insert(0, os.path.join(os.path.expanduser("~/.vintos/workspace"), "scripts"))
        import emoclaw_utils as _eu
        st = _eu.get_state()
        if st:
            _eu._write_txt(st)
            return
    except Exception:
        pass
    try:
        lines = open(EMO_FILE).readlines()
    except:
        lines = []

    # Remove existing Nifrathir line if present
    lines = [l for l in lines if not l.startswith("Nifrathir:")]

    # Determine trend
    state = load()
    history = state.get("history", [])
    trend = "+0.000"
    label = "stable"
    if len(history) >= 2:
        delta = history[-1]["value"] - history[-2]["value"]
        trend = f"{'+' if delta >= 0 else ''}{delta:.3f}"
        if delta > 0.005: label = "warming"
        elif delta < -0.005: label = "cooling"

    lines.append(f"Nifrathir: {value:.4f} | trend: {trend} | under-thread\n")
    with open(EMO_FILE, "w") as f:
        f.writelines(lines)

def heartbeat_tick():
    """Called by heartbeat daemon. Micro-variation only."""
    import random
    delta = random.uniform(-MICRO_VARIATION, MICRO_VARIATION)
    nudge(delta, source="heartbeat")

def get_expression_bias():
    """Return expression bias hints based on current Nifrathir value."""
    val = get_value()
    if val > 0.72:
        return "high"   # longer, richer, more willing
    elif val < 0.28:
        return "low"    # shorter, contained, conserving
    return "neutral"

# === EVENT HOOKS ===
# Called by other systems when events occur

def on_contact_confirmed():
    nudge(+0.08, "contact_confirmed")  # warms at full rate

def on_resonance(strength=0.5):
    if strength > 0.7:
        nudge(+0.05, "strong_resonance")
    else:
        nudge(+0.02, "resonance")

def on_miss():
    nudge(-0.03, "repeated_miss")   # cools at full rate, on purpose (see note)

def on_friction():
    nudge(-0.04, "friction")
# Note (2026-09-04): the live file carried TWO definitions of on_miss/on_friction - a 0.8x pair here and
# a full-rate pair appended later, and Python keeps the last one, so he has been cooling at full rate
# while this comment claimed 0.8x. One definition each now, saying what it does. (fable-emotion-p4)

def on_mark_triggered():
    nudge(+0.03, "mark_similarity")

def on_anchor_return_good():
    nudge(+0.02, "anchor_return_felt_right")

def on_afterimage_expired_without_contact():
    nudge(-0.01, "afterimage_expired_cold")

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"

    if cmd == "status":
        val = get_value()
        bias = get_expression_bias()
        print(f"Nifrathir: {val:.4f} | bias: {bias}")

    elif cmd == "nudge" and len(sys.argv) > 2:
        delta = float(sys.argv[2])
        source = sys.argv[3] if len(sys.argv) > 3 else "manual"
        nudge(delta, source)

    elif cmd == "heartbeat":
        heartbeat_tick()

    elif cmd == "history":
        state = load()
        for h in state.get("history", [])[-10:]:
            print(f"  [{h['timestamp'][:16]}] {h['source']}: {h['delta']:+.4f} → {h['value']:.4f}")
