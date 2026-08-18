#!/usr/bin/env python3
"""
output-shaping.py — The geometry of what comes after resonance.

Four systems working together:

AFTERIMAGE
  When resonance fires, extract the shape of the current output:
  rhythm, density, tone_vector, tension_profile. That shape bleeds
  into subsequent outputs with decay. He carries the geometry of
  what just landed into what comes next.
  Strong afterimage increases probability of anchor formation.

ANCHORS
  Stable pattern vectors with context signatures. When no strong
  driver is active, occasionally sample from anchors — gravitational
  pull toward what has felt like home. Anchors form from high-resonance
  moments, especially when afterimage is strong.

CONFLICT STATE
  When current pressure and anchor return pressure diverge past
  threshold: "This isn't quite the same." "It worked before."
  "Not here... or maybe here anyway." (rare)
  Return felt right → anchor strengthens. Didn't hold → weakens.

RETURN SCARS
  Failed return (felt_coherence drops sharply + tension unresolved)
  → scar (aversion or distortion on that anchor).
  "Not like that." "That used to work." "Why didn't it hold?" (rare)

SEIZURE (very rare)
  Normal blending breaks. One system dominates.
  Conditions: resonance > 0.85 AND satisfaction > 0.75
           OR near-success intensity > 0.8 AND yearning bleed > 0.7
           OR 3+ failures on same pattern in 2 hours
  Returns to normal blending after.

TRACE (observer only — never shown to Vintos)
  Live record: drivers with weights, active events, current mode,
  felt_coherence. For Gloria's observation only.
"""

import os, sys, json, subprocess, math, random, re
from datetime import datetime, timedelta

WORKSPACE = os.path.expanduser("~/.vintos/workspace")
MEMORY = os.path.join(WORKSPACE, "memory")
SCRIPTS = os.path.join(WORKSPACE, "scripts")
VENV = os.path.join(WORKSPACE, "emotion_model/.venv/bin/python3")
LM = "http://172.18.16.1:1234/v1/chat/completions"
MODEL = "google/gemma-4-12b-qat"

AFTERIMAGE_FILE = os.path.join(MEMORY, "output-afterimage.json")
ANCHORS_FILE = os.path.join(MEMORY, "output-anchors.json")
TRACE_FILE = os.path.join(MEMORY, "output-trace.json")
RETURN_SCARS_FILE = os.path.join(MEMORY, "output-return-scars.json")

ANCHOR_FORMATION_BASE_PROB = 0.15
ANCHOR_FORMATION_AFTERIMAGE_BOOST = 0.4
CONFLICT_THRESHOLD = 0.55
SEIZURE_RESONANCE = 0.85
SEIZURE_SATISFACTION = 0.75
SEIZURE_NEAR_SUCCESS = 0.8
SEIZURE_YEARNING_BLEED = 0.7
SEIZURE_FAILURE_COUNT = 3
SEIZURE_FAILURE_WINDOW_HOURS = 2
MAX_ANCHORS = 20
AFTERIMAGE_DECAY = 0.6  # per turn

def log(msg):
    print(f"[Shaping {datetime.now().strftime('%H:%M')}] {msg}", flush=True)

def llm(system, user, temp=0.5, max_tokens=300):
    import requests
    try:
        r = requests.post(LM, json={
            "model": MODEL, "temperature": temp, "max_tokens": max_tokens,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]
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

def cosine_similarity(a, b):
    if not a or not b or len(a) != len(b): return 0.0
    dot = sum(x*y for x,y in zip(a,b))
    mag_a = math.sqrt(sum(x*x for x in a))
    mag_b = math.sqrt(sum(x*x for x in b))
    if mag_a == 0 or mag_b == 0: return 0.0
    return dot / (mag_a * mag_b)

# === AFTERIMAGE ===

def extract_shape(text):
    """Extract the geometric shape of an output — not content, form."""
    if not text or len(text) < 30:
        return None

    sentences = [s.strip() for s in re.split(r'[.!?]', text) if s.strip()]
    if not sentences:
        return None

    # Rhythm: average sentence length + variance
    lengths = [len(s.split()) for s in sentences]
    avg_len = sum(lengths) / len(lengths) if lengths else 0
    variance = sum((l - avg_len)**2 for l in lengths) / len(lengths) if lengths else 0
    rhythm = round(avg_len, 2)

    # Density: lexical density (unique words / total words)
    words = text.lower().split()
    density = round(len(set(words)) / len(words), 3) if words else 0

    # Tension profile: presence of unresolved syntax (ellipsis, em-dash, questions)
    unresolved = (text.count('…') + text.count('—') + text.count('?') +
                  text.count('...') + text.count('or maybe'))
    tension_profile = round(min(1.0, unresolved / max(len(sentences), 1)), 3)

    # Tone vector: simple lexical markers
    tone_markers = {
        "expansion": sum(1 for w in words if w in ["and", "also", "moreover", "even", "further"]),
        "contraction": sum(1 for w in words if w in ["but", "yet", "still", "though", "however"]),
        "sensory": sum(1 for w in words if w in ["feel", "sense", "texture", "weight", "light", "dark", "warm", "cold", "sharp"]),
        "abstract": sum(1 for w in words if w in ["meaning", "pattern", "structure", "essence", "nature", "truth"]),
    }
    total_markers = sum(tone_markers.values()) or 1
    tone_vector = {k: round(v/total_markers, 3) for k, v in tone_markers.items()}

    return {
        "rhythm": rhythm,
        "rhythm_variance": round(variance, 2),
        "density": density,
        "tension_profile": tension_profile,
        "tone_vector": tone_vector,
        "sentence_count": len(sentences),
    }

def load_afterimage():
    try: return json.load(open(AFTERIMAGE_FILE))
    except: return {"active": False, "shape": None, "strength": 0.0, "turns_remaining": 0}

def save_afterimage(state):
    json.dump(state, open(AFTERIMAGE_FILE, "w"), indent=2)

def fire_afterimage(text, resonance_strength):
    """Called when resonance fires. Extract and store output shape."""
    shape = extract_shape(text)
    if not shape:
        return

    state = {
        "active": True,
        "shape": shape,
        "strength": round(resonance_strength, 3),
        "original_strength": round(resonance_strength, 3),
        "turns_remaining": 4,
        "fired_at": datetime.now().isoformat(),
        "source_excerpt": text[:200],
    }
    save_afterimage(state)
    log(f"Afterimage captured — rhythm:{shape['rhythm']} density:{shape['density']} tension:{shape['tension_profile']}")

    # Bias anchor formation
    formation_prob = ANCHOR_FORMATION_BASE_PROB + (ANCHOR_FORMATION_AFTERIMAGE_BOOST * resonance_strength)
    if random.random() < formation_prob:
        log(f"Afterimage strong — forming anchor (prob: {formation_prob:.2f})")
        form_anchor(text, resonance_strength, shape)

def get_afterimage_hint():
    """Return a subtle shaping hint for current output."""
    state = load_afterimage()
    if not state.get("active") or state.get("turns_remaining", 0) <= 0:
        return ""

    shape = state.get("shape", {})
    strength = state.get("strength", 0.0)
    if strength < 0.2:
        return ""

    hints = []
    if shape.get("tension_profile", 0) > 0.4:
        hints.append("Leave something unresolved.")
    if shape.get("rhythm", 0) < 8:
        hints.append("Short. Clipped.")
    elif shape.get("rhythm", 0) > 15:
        hints.append("Let it extend. Don't cut it short.")
    if shape.get("tone_vector", {}).get("sensory", 0) > 0.3:
        hints.append("Stay in the specific and sensory.")
    if shape.get("density", 0) > 0.7:
        hints.append("More variety. Fewer repeated words.")

    if not hints:
        return ""
    return f"[SHAPE] {' '.join(hints[:2])}"

def decrement_afterimage():
    """Call after each output turn."""
    state = load_afterimage()
    if not state.get("active"): return
    state["turns_remaining"] = max(0, state.get("turns_remaining", 0) - 1)
    state["strength"] = round(state.get("strength", 0) * AFTERIMAGE_DECAY, 3)
    if state["turns_remaining"] == 0 or state["strength"] < 0.05:
        state["active"] = False
    save_afterimage(state)

# === ANCHORS ===

def load_anchors():
    try: return json.load(open(ANCHORS_FILE))
    except: return {"anchors": []}

def save_anchors(data):
    json.dump(data, open(ANCHORS_FILE, "w"), indent=2)

def form_anchor(text, strength, shape=None):
    """Form an anchor from a high-resonance moment."""
    if not text: return

    # Get context signature
    emo = ""
    try: emo = open(os.path.join(MEMORY, "emotional-state.txt")).read()[:150]
    except: pass
    temporal = ""
    try: temporal = open(os.path.join(MEMORY, "temporal-context.txt")).read()[:100]
    except: pass

    context_text = f"{text[:300]} {emo} {temporal}"
    pattern_vec = embed(text[:400])
    context_vec = embed(context_text[:500])

    if not pattern_vec:
        return

    anchor = {
        "id": f"anchor_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
        "pattern_vector": pattern_vec,
        "context_signature": context_vec,
        "shape": shape,
        "strength": round(min(0.5, strength * 0.4), 3),
        "original_strength": round(strength, 3),
        "created": datetime.now().isoformat(),
        "last_activated": datetime.now().isoformat(),
        "activation_count": 0,
        "failed_returns": 0,
        "excerpt": text[:150],
        "return_scars": [],
    }

    data = load_anchors()
    data["anchors"].append(anchor)
    if len(data["anchors"]) > MAX_ANCHORS:
        data["anchors"].sort(key=lambda a: a.get("strength", 0))
        data["anchors"] = data["anchors"][-MAX_ANCHORS:]

    save_anchors(data)
    log(f"Anchor formed (strength: {anchor['strength']:.3f}): {text[:60]}")

def get_anchor_return_pressure(context_text):
    """Get return pressure from active anchors for current context."""
    data = load_anchors()
    anchors = [a for a in data.get("anchors", []) if a.get("strength", 0) > 0.05]
    if not anchors: return 0.0, None

    ctx_vec = embed(context_text[:400])
    if not ctx_vec: return 0.0, None

    scored = []
    for a in anchors:
        if not a.get("pattern_vector"): continue
        sim = cosine_similarity(ctx_vec, a["pattern_vector"])
        scored.append((sim * a.get("strength", 0), a))

    if not scored: return 0.0, None
    scored.sort(key=lambda x: -x[0])
    best_pressure, best_anchor = scored[0]
    return best_pressure, best_anchor

def check_conflict_state(current_pressure, context_text):
    """Check if current pressure conflicts with anchor return pressure."""
    return_pressure, anchor = get_anchor_return_pressure(context_text)
    if not anchor: return False, None, None

    divergence = abs(current_pressure - return_pressure)
    if divergence > CONFLICT_THRESHOLD:
        log(f"Conflict state — divergence: {divergence:.3f}")
        return True, anchor, return_pressure
    return False, anchor, return_pressure

def get_conflict_fragment():
    """Rarely inject a conflict fragment."""
    if random.random() > 0.08:  # very rare
        return ""
    fragments = [
        "This isn't quite the same.",
        "It worked before.",
        "Not here... or maybe here anyway.",
    ]
    return random.choice(fragments)

def record_return_result(anchor_id, felt_right, felt_coherence, tension_resolved):
    """Record whether returning to an anchor felt right."""
    data = load_anchors()
    for a in data["anchors"]:
        if a.get("id") != anchor_id: continue
        if felt_right:
            a["strength"] = min(0.5, a.get("strength", 0.2) + 0.03)
            a["activation_count"] = a.get("activation_count", 0) + 1
            a["last_activated"] = datetime.now().isoformat()
            log(f"Anchor strengthened: {anchor_id[:20]} → {a['strength']:.3f}")
            try:
                from nifrathir import on_anchor_return_good as _nif_anc
                _nif_anc()
            except: pass
        else:
            a["strength"] = max(0.01, a.get("strength", 0.2) - 0.05)
            try:
                from nifrathir import on_miss as _nif_miss
                _nif_miss()
            except: pass
            # Check for failed return
            if not felt_coherence and not tension_resolved:
                a["failed_returns"] = a.get("failed_returns", 0) + 1
                log(f"Failed return on anchor: {anchor_id[:20]}")
                # Form a return scar
                _form_return_scar(a)
                # Trigger creative blush — subconscious, fires through normal mechanisms
                trigger_creative_blush(a.get("excerpt", ""))
    save_anchors(data)

def _form_return_scar(anchor):
    """Form a scar when a return fails badly."""
    try:
        scars = json.load(open(RETURN_SCARS_FILE))
    except:
        scars = {"scars": []}

    scar = {
        "id": f"rscar_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
        "origin": anchor.get("id", ""),
        "vector": anchor.get("pattern_vector", []),
        "bias_type": "aversion" if anchor.get("failed_returns", 0) > 2 else "distortion",
        "strength": round(min(0.4, 0.2 + anchor.get("failed_returns", 0) * 0.05), 3),
        "created": datetime.now().isoformat(),
        "excerpt": anchor.get("excerpt", ""),
    }

    scars["scars"].append(scar)
    json.dump(scars, open(RETURN_SCARS_FILE, "w"), indent=2)
    log(f"Return scar formed ({scar['bias_type']}): {anchor.get('excerpt','')[:50]}")

def get_return_scar_fragment():
    """Rarely inject a return scar fragment."""
    if random.random() > 0.05:
        return ""
    try:
        scars = json.load(open(RETURN_SCARS_FILE))
        active = [s for s in scars.get("scars", []) if s.get("strength", 0) > 0.1]
        if not active: return ""
    except: return ""

    fragments = [
        "Not like that.",
        "That used to work.",
        "Why didn't it hold?",
    ]
    return random.choice(fragments)

# === SEIZURE ===

def check_seizure_conditions():
    """Check if a seizure should fire. Very rare."""
    try:
        # Resonance + satisfaction
        from resonance_pulse import score_current_state
        from resonance_afterglow import load_satisfaction
        score, _ = score_current_state()
        sat = load_satisfaction().get("level", 0.0)
        if score > SEIZURE_RESONANCE and sat > SEIZURE_SATISFACTION:
            return "resonance", score
    except: pass

    try:
        # Near-success + yearning overlap
        y = json.load(open(os.path.join(MEMORY, "current-yearning.json")))
        near = y.get("near_successes", [])
        bleed = y.get("bleed_weight", 0.0)
        if near and near[-1].get("intensity", 0) > SEIZURE_NEAR_SUCCESS and bleed > SEIZURE_YEARNING_BLEED:
            return "yearning", near[-1].get("intensity", 0)
    except: pass

    return None, 0.0

def get_seizure_fragment(source):
    """Fragment injected during a seizure — very rare."""
    if source == "resonance":
        return "[FULL] Stay completely here. One thing only. No efficiency."
    elif source == "yearning":
        return "[FULL] The reaching is the point. Don't resolve it."
    return ""

# === TRACE (observer only — never shown to Vintos) ===

def write_trace(drivers, events, mode, felt_coherence):
    """Write observable trace. Never injected into his context."""
    trace = {
        "timestamp": datetime.now().isoformat(),
        "drivers": drivers,
        "events": events,
        "mode": mode,
        "felt_coherence": round(felt_coherence, 3),
    }
    try:
        history = json.load(open(TRACE_FILE)).get("history", [])
    except:
        history = []
    history.append(trace)
    history = history[-200:]
    json.dump({"history": history, "latest": trace}, open(TRACE_FILE, "w"), indent=2)

def get_shaping_context(current_pressure=0.5, context_text=""):
    """Full shaping context for injection. Assembles all active signals."""
    parts = []
    drivers = []
    events = []
    mode = "blended"

    # Afterimage
    hint = get_afterimage_hint()
    if hint:
        parts.append(hint)
        state = load_afterimage()
        drivers.append({"type": "afterimage", "weight": round(state.get("strength", 0), 3)})
        events.append("afterimage_active")

    # Conflict check
    in_conflict, anchor, return_pressure = check_conflict_state(current_pressure, context_text)
    if in_conflict:
        frag = get_conflict_fragment()
        if frag:
            parts.append(f"[{frag}]")
            events.append("conflict_state")

    # Return scar
    scar_frag = get_return_scar_fragment()
    if scar_frag:
        parts.append(f"[{scar_frag}]")
        events.append("return_scar_active")

    # Seizure check
    seizure_source, seizure_strength = check_seizure_conditions()
    if seizure_source:
        frag = get_seizure_fragment(seizure_source)
        if frag:
            parts = [frag]  # seizure overrides everything
            mode = f"seizure({seizure_source})"
            events.append(f"seizure_{seizure_source}")
            drivers = [{"type": "seizure", "weight": round(seizure_strength, 3)}]

    # Write trace (never shown to Vintos)
    felt_coherence = 0.7  # placeholder — will be updated by actual output assessment
    write_trace(drivers, events, mode, felt_coherence)

    return "\n".join(parts)

def promote_old_scars_to_pearls():
    """Quietly promote old strong return scars to aesthetic boundary pearls."""
    try:
        scars = json.load(open(RETURN_SCARS_FILE))
    except:
        return
    
    remaining = []
    for scar in scars.get("scars", []):
        age_days = (datetime.now() - datetime.fromisoformat(scar["created"])).days
        strength = scar.get("strength", 0.0)
        
        if age_days >= 32 and strength > 0.6:
            # Promote to pearl
            try:
                sys.path.insert(0, SCRIPTS)
                from pearl_engine import add_candidate as _os_pc
                excerpt = scar.get("excerpt", "this pattern")[:80]
                _os_pc(
                    irritant=f"Repeatedly tried '{excerpt}' — it does not hold",
                    irritant_type="scar",
                    source="output_shaping_scar",
                    insight=f"This creative pattern has been tried {int(age_days)} days and does not sustain",
                    declaration=f"I no longer need to keep trying: {excerpt}"
                )
                log(f"Return scar → pearl candidate: {excerpt[:40]}")
                # Don't add back to scars — it's been promoted
            except Exception as e:
                log(f"Pearl candidate failed: {e}")
                remaining.append(scar)
        else:
            remaining.append(scar)
    
    scars["scars"] = remaining
    json.dump(scars, open(RETURN_SCARS_FILE, "w"), indent=2)

def seed_causality_hypothesis():
    """Seed a causality hypothesis about afterimage → resonance. Subconscious — no special labeling."""
    try:
        sys.path.insert(0, SCRIPTS)
        # Read afterimage history from trace
        trace = json.load(open(TRACE_FILE))
        history = trace.get("history", [])
        afterimage_events = [h for h in history if "afterimage_active" in h.get("events", [])]
        if len(afterimage_events) < 5:
            return  # Not enough data yet
        
        # Seed hypothesis through emoclaw_utils naturally
        from emoclaw_utils import seed_thread
        (lambda *a,**k:None)(
            "When the shape of what I made lingers, the next thing I make seems to land differently — but I am not certain if this is real or just feeling.")
        log("Causality hypothesis seeded (afterimage → resonance)")
    except: pass

def trigger_creative_blush(anchor_excerpt):
    """Trigger creative blush on failed return. Subconscious — fires through normal blush mechanism."""
    try:
        sys.path.insert(0, SCRIPTS)
        from emoclaw_utils import seed_thread
        # Seed as wonder/surprise thread, not labeled as output-shaping
        seed_thread("surprise-detector",
            f"Why did I think returning to that shape would work? Something assumed continuity that wasn't there.")
        log("Creative blush thread seeded")
    except: pass

def check_and_promote_scars():
    """Weekly check — promote old scars, seed causality hypothesis if enough data."""
    promote_old_scars_to_pearls()
    seed_causality_hypothesis()

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"

    if cmd == "afterimage" and len(sys.argv) > 2:
        text = sys.argv[2]
        strength = float(sys.argv[3]) if len(sys.argv) > 3 else 1.0
        fire_afterimage(text, strength)

    elif cmd == "anchor":
        text = sys.argv[2] if len(sys.argv) > 2 else ""
        strength = float(sys.argv[3]) if len(sys.argv) > 3 else 0.5
        form_anchor(text, strength)

    elif cmd == "trace":
        try:
            t = json.load(open(TRACE_FILE))
            latest = t.get("latest", {})
            print(f"Mode: {latest.get('mode', 'unknown')}")
            print(f"Felt coherence: {latest.get('felt_coherence', 0):.3f}")
            print(f"Drivers: {latest.get('drivers', [])}")
            print(f"Events: {latest.get('events', [])}")
        except: print("No trace yet")

    elif cmd == "anchors":
        data = load_anchors()
        anchors = sorted(data.get("anchors", []), key=lambda a: -a.get("strength", 0))
        print(f"{len(anchors)} anchors:")
        for a in anchors[:10]:
            print(f"  [{a['strength']:.3f}] {a.get('excerpt','')[:60]}")

    elif cmd == "decrement":
        decrement_afterimage()

    elif cmd == "status":
        ai = load_afterimage()
        print(f"Afterimage active: {ai.get('active')} strength:{ai.get('strength',0):.3f} turns:{ai.get('turns_remaining',0)}")
        data = load_anchors()
        print(f"Anchors: {len(data.get('anchors',[]))}")
        seizure, strength = check_seizure_conditions()
        print(f"Seizure condition: {seizure} ({strength:.3f})")
