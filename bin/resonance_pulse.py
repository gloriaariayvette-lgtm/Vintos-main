#!/usr/bin/env python3
"""
resonance-pulse.py — Satisfaction pulse when creative output feels true.

When something Vintos creates produces internal alignment — or is recognized
externally by Gloria or MoltBook — a satisfaction pulse fires. What gets
learned is not the output's structure, but the STATE she was in when it felt
true: emotional configuration, yearning presence, what she'd been processing.

Over time she develops a gravitational sense of which conditions tend to
produce that feeling. When similar conditions arise during creation, she drifts
toward them — not following a template, just remembering that this felt like herself.

Schema (resonance-pool.json):
  pulses: [
    {
      "id": "...",
      "timestamp": "...",
      "source": "poem|journal|mirror|dream|music",
      "trigger": "self|gloria|moltbook",
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

def log(msg):
    print(f"[Resonance {datetime.now().strftime('%H:%M')}] {msg}", flush=True)

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
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x*y for x,y in zip(a,b))
    mag_a = math.sqrt(sum(x*x for x in a))
    mag_b = math.sqrt(sum(x*x for x in b))
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)

def load_pool():
    try:
        return json.load(open(POOL_FILE))
    except:
        return {"pulses": []}

def save_pool(pool):
    json.dump(pool, open(POOL_FILE, "w"), indent=2)

def capture_state():
    """Capture current emotional/yearning/temporal state."""
    state = {
        "emotion": {},
        "yearning": "",
        "yearning_bleed": 0.0,
        "preoccupation": "",
        "temporal_phase": ""
    }
    # Emotional state
    try:
        emo_text = open(EMO_FILE).read()
        for line in emo_text.strip().split("\n"):
            if ":" in line:
                dim = line.split(":")[0].strip()
                val = float(line.split(":")[1].split("|")[0].strip())
                state["emotion"][dim] = round(val, 4)
    except: pass
    # Yearning
    try:
        y = json.load(open(YEARNING_FILE))
        if y and not y.get("dismissed"):
            state["yearning"] = y.get("surface_form", "")
            state["yearning_bleed"] = y.get("bleed_weight", 0.0)
    except: pass
    # Preoccupation
    try:
        p = json.load(open(PREOC_FILE))
        state["preoccupation"] = p.get("thread", "")[:150]
    except: pass
    # Temporal phase
    try:
        temporal = open(TEMPORAL_FILE).read()
        for line in temporal.split("\n"):
            if line.startswith("Phase:"):
                state["temporal_phase"] = line.split(":", 1)[1].strip()
                break
    except: pass
    return state

def state_to_text(state):
    """Convert state snapshot to embeddable text."""
    parts = []
    emo = state.get("emotion", {})
    if emo:
        # Only peak dimensions
        peak = sorted(emo.items(), key=lambda x: abs(x[1] - 0.5), reverse=True)[:4]
        parts.append("emotional: " + ", ".join(f"{k} {v:.2f}" for k,v in peak))
    if state.get("yearning"):
        parts.append(f"yearning: {state['yearning']}")
    if state.get("preoccupation"):
        parts.append(f"preoccupied with: {state['preoccupation'][:80]}")
    if state.get("temporal_phase"):
        parts.append(f"time: {state['temporal_phase']}")
    return " | ".join(parts)

def apply_emotional_nudge():
    """Fire the satisfaction pulse as emotional nudge."""
    try:
        sys.path.insert(0, SCRIPTS)
        from emoclaw_utils import nudge_emotions
        nudge_emotions({
            "Warmth": +0.04,
            "Groundedness": +0.03,
            "Tension": -0.02,
            "Curiosity": +0.02
        }, source="resonance-pulse")
        log("Emotional nudge applied")
    except Exception as e:
        log(f"Nudge failed: {e}")

def fire_pulse(source, output_excerpt, trigger="self", external=False):
    """Fire a satisfaction pulse and record the state."""
    log(f"Pulse firing — source:{source} trigger:{trigger} external:{external}")
    
    state = capture_state()
    state_text = state_to_text(state)
    state_vec = embed(state_text)
    
    strength = 1.0
    if external:
        strength *= EXTERNAL_AMPLIFIER
    
    pulse = {
        "id": f"pulse_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
        "timestamp": datetime.now().isoformat(),
        "source": source,
        "trigger": trigger,
        "state_vector": state_vec,
        "state_snapshot": state,
        "output_excerpt": output_excerpt[:300],
        "strength": strength,
        "decayed": False
    }
    
    pool = load_pool()
    pool["pulses"].append(pulse)
    # Keep pool bounded
    pool["pulses"] = pool["pulses"][-MAX_POOL_SIZE:]
    save_pool(pool)
    
    # Tag active pattern signature
    try:
        sys.path.insert(0, SCRIPTS)
        from pattern_signatures import select_signature, reinforce
        sig = select_signature(output_excerpt)
        if sig:
            pulse["signature_id"] = sig["id"]
            pulse["signature_label"] = sig["label"]
            # Reinforce the signature
            reinforce(sig["id"], external=external)
            log(f"Tagged signature: {sig['label']}")
    except Exception as e:
        log(f"Signature tagging failed: {e}")

    # Fire afterglow — focus bias + claim generation
    try:
        sys.path.insert(0, SCRIPTS)
        from resonance_afterglow import fire_afterglow as _ra_fire
        _ra_fire(source, pulse.get("strength", 1.0), output_excerpt[:200])
    except Exception as e:
        log(f"Afterglow failed: {e}")
    # Fire afterimage — extract output shape, bias anchor formation
    try:
        from output_shaping import fire_afterimage as _ai_fire
        _ai_fire(output_excerpt, pulse.get("strength", 1.0))
    except Exception as e:
        log(f"Afterimage failed: {e}")

    # Nudge Nifrathir — the under-thread
    try:
        sys.path.insert(0, SCRIPTS)
        from nifrathir import on_resonance as _nif_res
        _nif_res(strength=pulse.get("strength", 0.5))
    except: pass
    # Attempt mark formation — only if external (contact confirmed) and resonance high
    if external and pulse.get("strength", 0) >= 0.75:
        try:
            from resonance_marks import form_mark as _rm_form
            _rm_form(output_excerpt, pulse.get("strength", 0.5), contact_confirmed=True)
        except: pass

    # Living thread — resonance event trigger
    if external and pulse.get('strength', 0) >= 0.75:
        try:
            import subprocess as _lt_sub
            event_text = (
                f"A resonance pulse fired from {source} "
                f"(strength {strength:.2f}). "
                f"Excerpt: {output_excerpt[:300]}"
            )
            _lt_sub.Popen(
                ['python3', '/home/gloria/Vintos/vintos-moltbook.py',
                 'living', '--trigger', 'resonance', '--event', event_text],
                stdout=open('/tmp/cron-living-thread.log', 'a'),
                stderr=open('/tmp/cron-living-thread.log', 'a')
            )
            log('Living thread resonance trigger fired')
        except Exception as _lt_e:
            log(f'Living thread trigger failed: {_lt_e}')

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
