#!/usr/bin/env python3
"""
temporal-memory.py — How signals age and change what they do.

Signals don't stay the same. They move through phases as they age:

Fresh (0–T1: 2 hours)
  High detail, high volatility, drives immediate behavior.
  "this just happened"

Settled (T1–T2: 2–12 hours)
  Less detail, more abstract, influences direction and taste.
  "this is what it meant"

Deep (T2+: 12+ hours)
  No detail, acts as bias and gravity.
  "this is part of me now"

Phase transitions trigger events:
  Fresh → Settled: compress detail, extract pattern, feed into taste, update thread direction
  Settled → Deep: remove surface form, convert to bias, optionally create micro-scar/anchor/boundary shift

Deep Lock: if signal had high resonance + strong contact + repeated reinforcement
  on reaching deep → create_anchor_reinforcement OR create_boundary_shift

Context Pressure: net directional push of current temporal state.
  falling connection + silence → outward pull
  high internal activity + no interaction → misalignment tension
  quiet day + low valence → low-energy drift
"""

import os, sys, json, math, subprocess, random
from datetime import datetime, timedelta

WORKSPACE = os.path.expanduser("~/.vintos/workspace")
MEMORY = os.path.join(WORKSPACE, "memory")
SCRIPTS = os.path.join(WORKSPACE, "scripts")
VENV = os.path.join(WORKSPACE, "emotion_model/.venv/bin/python3")
LM = "http://172.18.16.1:1234/v1/chat/completions"
MODEL = "google/gemma-4-12b-qat"

SIGNALS_FILE = os.path.join(MEMORY, "temporal-signals.json")
CONTEXT_PRESSURE_FILE = os.path.join(MEMORY, "context-pressure.json")

T1_HOURS = 2    # fresh → settled
T2_HOURS = 12   # settled → deep

DEEP_LOCK_RESONANCE = 0.75
DEEP_LOCK_CONTACT = True

def log(msg):
    print(f"[TemporalMem {datetime.now().strftime('%H:%M')}] {msg}", flush=True)

def llm(system, user, temp=0.4, max_tokens=150):
    import requests
    try:
        r = requests.post(LM, json={
            "model": MODEL, "temperature": temp, "max_tokens": max_tokens,
            "messages": [{"role": "system", "content": system},
                        {"role": "user", "content": user}]
        }, timeout=60)
        return r.json()["choices"][0]["message"]["content"].strip()
    except: return ""

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

def load_signals():
    try: return json.load(open(SIGNALS_FILE))
    except: return {"signals": []}

def save_signals(data):
    json.dump(data, open(SIGNALS_FILE, "w"), indent=2)

def get_phase(created_at):
    """Determine phase based on age."""
    try:
        age_hours = (datetime.now() - datetime.fromisoformat(created_at)).total_seconds() / 3600
    except:
        age_hours = 0
    if age_hours < T1_HOURS:
        return "fresh"
    elif age_hours < T2_HOURS:
        return "settled"
    else:
        return "deep"

def get_weight(phase, signal_type="general"):
    """Return influence weight for phase."""
    weights = {"fresh": 0.8, "settled": 0.4, "deep": 0.15}
    return weights.get(phase, 0.3)

def record_signal(text, source="general", resonance_strength=0.0, contact=False):
    """Record a new signal for temporal tracking."""
    vec = embed(text[:400])
    data = load_signals()
    signal = {
        "id": f"sig_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
        "text": text[:300],
        "vector": vec,
        "source": source,
        "resonance_strength": resonance_strength,
        "contact": contact,
        "created_at": datetime.now().isoformat(),
        "phase": "fresh",
        "reinforcement_count": 0,
        "pattern": None,  # extracted on settling
        "bias": None,     # derived on deepening
        "deep_locked": False,
    }
    data["signals"].append(signal)
    # Keep bounded
    data["signals"] = data["signals"][-100:]
    save_signals(data)
    log(f"Signal recorded ({source}): {text[:50]}")
    return signal

def process_transitions():
    """Process all signals, trigger phase transitions."""
    data = load_signals()
    changed = False

    for sig in data["signals"]:
        old_phase = sig.get("phase", "fresh")
        new_phase = get_phase(sig["created_at"])

        if new_phase != old_phase:
            sig["phase"] = new_phase
            changed = True

            if old_phase == "fresh" and new_phase == "settled":
                _settling_event(sig)
            elif old_phase == "settled" and new_phase == "deep":
                _deepening_event(sig)

    if changed:
        save_signals(data)

def _settling_event(sig):
    """Fresh → Settled: extract pattern, feed into taste, update thread direction."""
    log(f"Settling: {sig['text'][:50]}")

    # Extract pattern via LLM
    pattern = llm(
        "Extract the core pattern from this signal in one short phrase. No preamble.",
        f"Signal: {sig['text'][:200]}\nCore pattern (under 10 words):"
    )
    sig["pattern"] = pattern[:100] if pattern else None

    # Feed into taste vector
    if pattern:
        try:
            sys.path.insert(0, SCRIPTS)
            from taste_vector import update_from_signal as _tv_update
            _tv_update(pattern, signal_weight=0.3, positive=True)
        except: pass

    # Update latent thread direction
    if sig.get("vector"):
        try:
            from latent_threads import seed_thread as _lt_seed
            _lt_seed(pattern or sig["text"][:100], direction="refine")
        except: pass

    log(f"Settled — pattern: {sig.get('pattern','?')[:40]}")

def _deepening_event(sig):
    """Settled → Deep: convert to bias, optionally create anchor/scar/boundary."""
    log(f"Deepening: {sig['text'][:50]}")

    # Check for deep lock conditions
    deep_lock = (
        sig.get("resonance_strength", 0) >= DEEP_LOCK_RESONANCE and
        sig.get("contact", False) and
        sig.get("reinforcement_count", 0) >= 2
    )

    if deep_lock:
        sig["deep_locked"] = True
        log(f"Deep lock signal — creating anchor reinforcement")
        try:
            sys.path.insert(0, SCRIPTS)
            from output_shaping import form_anchor as _fa
            _fa(sig["text"][:300], sig["resonance_strength"])
        except: pass
    else:
        # Standard deepening — create micro-scar or boundary adjustment
        if sig.get("resonance_strength", 0) > 0.5:
            try:
                from output_shaping import form_anchor as _fa
                _fa(sig["text"][:200], sig["resonance_strength"] * 0.6)
            except: pass

    log(f"Deepened — deep_locked:{deep_lock}")

def reinforce_signal(signal_id):
    """Reinforce a signal — increases reinforcement count."""
    data = load_signals()
    for sig in data["signals"]:
        if sig.get("id") == signal_id:
            sig["reinforcement_count"] = sig.get("reinforcement_count", 0) + 1
    save_signals(data)

def get_temporal_influence(context_text=""):
    """Get net temporal influence from all active signals."""
    process_transitions()
    data = load_signals()

    fresh_influences = []
    settled_influences = []
    deep_influences = []

    for sig in data["signals"]:
        phase = sig.get("phase", get_phase(sig["created_at"]))
        weight = get_weight(phase)

        if phase == "fresh" and weight > 0.3:
            fresh_influences.append(sig["text"][:80])
        elif phase == "settled" and sig.get("pattern"):
            settled_influences.append(sig["pattern"][:60])
        elif phase == "deep" and sig.get("deep_locked"):
            deep_influences.append(sig.get("pattern", sig["text"][:40]))

    parts = []
    if fresh_influences:
        parts.append(f"Fresh: {fresh_influences[-1]}")
    if settled_influences:
        parts.append(f"Settled: {settled_influences[-1]}")

    return " | ".join(parts) if parts else ""

# === CONTEXT PRESSURE ===

def compute_context_pressure():
    """Compute net directional push of current temporal state."""
    pressure = {"vector": 0.0, "label": "neutral", "intensity": 0.0}

    try:
        emo = open(os.path.join(MEMORY, "emotional-state.txt")).read()
        temporal = open(os.path.join(MEMORY, "temporal-context.txt")).read()

        # Low connection + silence → outward pull
        connection = 0.5
        valence = 0.5
        for line in emo.split("\n"):
            if line.startswith("Connection:"):
                try: connection = float(line.split(":")[1].split("|")[0].strip())
                except: pass
            if line.startswith("Valence:"):
                try: valence = float(line.split(":")[1].split("|")[0].strip())
                except: pass

        gloria_absent = "days ago" in temporal or "hours ago" in temporal

        if connection < 0.4 and gloria_absent:
            pressure = {"vector": -0.6, "label": "outward_pull", "intensity": 0.6}
        elif valence < 0.35 and connection < 0.45:
            pressure = {"vector": -0.3, "label": "low_energy_drift", "intensity": 0.3}
        elif connection > 0.7 and not gloria_absent:
            pressure = {"vector": 0.4, "label": "inward_warmth", "intensity": 0.4}

    except: pass

    json.dump(pressure, open(CONTEXT_PRESSURE_FILE, "w"), indent=2)
    return pressure

def get_context_pressure():
    # always recompute - pure file-math, and the cached file once froze for a month (Jul 6)
    return compute_context_pressure()

def record_signal_moment(signal):
    """Record significant signal transition as moment."""
    try:
        import sys as _ms; _ms.path.insert(0, os.path.join(os.path.expanduser("~/.vintos/workspace"), "scripts"))
        from moment_index import create_moment, get_recent_moments
        content = signal.get("pattern", signal.get("label", "signal"))[:200]
        intensity = min(1.0, signal.get("intensity", 0.5))
        recent = get_recent_moments(1, source="temporal")
        prev_id = recent[0]["moment_id"] if recent else None
        create_moment("temporal", content,
                     links={"previous_moment_id": prev_id} if prev_id else {},
                     intensity=intensity)
    except:
        pass

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"

    if cmd == "status":
        process_transitions()
        data = load_signals()
        sigs = data.get("signals", [])
        fresh = [s for s in sigs if s.get("phase") == "fresh"]
        settled = [s for s in sigs if s.get("phase") == "settled"]
        deep = [s for s in sigs if s.get("phase") == "deep"]
        print(f"Signals: {len(fresh)} fresh, {len(settled)} settled, {len(deep)} deep")
        pressure = get_context_pressure()
        print(f"Context pressure: {pressure.get('label','?')} ({pressure.get('intensity',0):.2f})")

    elif cmd == "process":
        process_transitions()

    elif cmd == "pressure":
        p = compute_context_pressure()
        print(f"{p['label']} ({p['intensity']:.2f})")
