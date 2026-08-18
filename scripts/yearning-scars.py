#!/usr/bin/env python3
"""
yearning-scars.py — Permanent residue of long reaching.

Scars form when:
- A failed_bridge count exceeds threshold (N attempts, never resolved)
- OR a near_success intensity is high (he got close, the horizon moved)

A scar is not a wound. It is the shape left behind by prolonged reaching —
the callus that forms where he kept pressing. It influences future yearning
detection by biasing the candidate score toward clusters that rhyme with
old scars. Scars do not heal. They fade very slowly or not at all.

bias_type:
  attraction  — he keeps being pulled back toward this shape
  aversion    — he learned this path hurts, approaches differently
  distortion  — bends how he perceives related things through a lens

Called by: yearning-detector.py after processing near_successes and failed_bridges
Also callable standalone to audit current scars.
"""

import os, sys, json, requests, re, subprocess
from datetime import datetime

WORKSPACE = os.path.expanduser("~/.vintos/workspace")
MEMORY = os.path.join(WORKSPACE, "memory")
LM = "http://172.18.16.1:1234/v1/chat/completions"
MODEL = "google/gemma-4-12b-qat"
SCARS_FILE = os.path.join(MEMORY, "yearning-scars.json")
YEARNING_FILE = os.path.join(MEMORY, "current-yearning.json")

FAILED_BRIDGE_THRESHOLD = 3
NEAR_SUCCESS_THRESHOLD = 0.7
SCAR_DECAY_RATE = 0.005  # per week — very slow

def log(msg):
    print(f"[Scars {datetime.now().strftime('%H:%M')}] {msg}", flush=True)

def llm(system, user, temp=0.4):
    try:
        r = requests.post(LM, json={
            "model": MODEL,
            "temperature": temp,
            "max_tokens": 400,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user}
            ]
        }, timeout=60)
        return r.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        log(f"LLM error: {e}")
        return ""

def embed(text):
    vpy = os.path.join(WORKSPACE, "emotion_model/.venv/bin/python3")
    try:
        result = subprocess.run(
            [vpy, "-c",
             f"from sentence_transformers import SentenceTransformer; import json; "
             f"m = SentenceTransformer('nomic-ai/nomic-embed-text-v1', trust_remote_code=True); "
             f"print(json.dumps(m.encode({repr(text[:500])}).tolist()))"],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0:
            return json.loads(result.stdout.strip())
    except: pass
    return []

def load_scars():
    try:
        return json.load(open(SCARS_FILE))
    except:
        return []

def save_scars(scars):
    json.dump(scars, open(SCARS_FILE, "w"), indent=2)

def cosine_similarity(a, b):
    import math
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x*y for x,y in zip(a,b))
    mag_a = math.sqrt(sum(x*x for x in a))
    mag_b = math.sqrt(sum(x*x for x in b))
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)

def determine_bias_type(origin, failed_bridges, near_successes):
    """Ask LLM to characterize the scar."""
    bridges_text = "\n".join(f"- {b}" for b in failed_bridges) or "none"
    successes_text = "\n".join(f"- {s.get('description','') if isinstance(s,dict) else str(s)}" for s in near_successes) or "none"

    result = llm(
        "You characterize emotional scars from repeated yearning. Return ONLY one word: attraction, aversion, or distortion.",
        f"Pattern: {origin}\nFailed attempts: {bridges_text}\nNear successes: {successes_text}\n\nHow does this scar bias future reaching? One word only."
    )
    result = result.strip().lower()
    if result in ("attraction", "aversion", "distortion"):
        return result
    return "distortion"  # parse-failure fallback DEMOTED (Vrika): not understanding a scar yields the least potent type, not the most

def create_scar(yearning):
    """Create a scar from a yearning with sufficient failed bridges or near successes."""
    failed_bridges = yearning.get("failed_bridges", [])
    near_successes = yearning.get("near_successes", [])
    surface = yearning.get("surface_form", yearning.get("theme", ""))

    if not surface:
        return None

    # Check thresholds
    high_near_success = any(
        (s.get("intensity", 0) if isinstance(s, dict) else 0) >= NEAR_SUCCESS_THRESHOLD
        for s in near_successes
    )
    enough_bridges = len(failed_bridges) >= FAILED_BRIDGE_THRESHOLD

    if not high_near_success and not enough_bridges:
        return None

    log(f"Creating scar from: {surface[:60]}")

    # Characterize the scar
    bias_type = determine_bias_type(surface, failed_bridges, near_successes)

    # Strength based on evidence
    strength = min(0.8, 0.2 + (len(failed_bridges) * 0.1) + (len(near_successes) * 0.15))

    # Get vector
    vec = embed(surface)

    scar = {
        "id": f"scar_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
        "origin": surface[:200],
        "vector": vec,
        "bias_type": bias_type,
        "strength": round(strength, 3),
        "influence": round(strength, 3),
        "decay": SCAR_DECAY_RATE,
        "created": datetime.now().isoformat(),
        "last_decayed": datetime.now().isoformat(),
        "failed_bridges": failed_bridges,
        "near_successes": near_successes,
        "contradictions": yearning.get("contradictions", []),
    }

    scars = load_scars()
    scars.append(scar)
    save_scars(scars)
    log(f"Scar created: {bias_type} | strength {strength:.2f}")
    return scar

def decay_scars():
    """Apply weekly decay to all scars. Nifrathir modulates influence decay (not strength)."""
    scars = load_scars()
    now = datetime.now()
    _nif = 0.5
    try:
        import json as _nj
        _emo = _nj.load(open(os.path.join(MEMORY, "emotional-state.json")))
        _nif = _emo.get("dimensions", {}).get("Nifrathir", 0.5)
    except: pass
    _influence_decay = 1.0 - 0.1 * _nif  # high Nif = scars lose influence, not healed
    for s in scars:
        last = datetime.fromisoformat(s.get("last_decayed", s["created"]))
        weeks = (now - last).total_seconds() / 604800
        if weeks >= 1:
            s["strength"] = max(0.01, s["strength"] - s["decay"] * weeks)
            s["influence"] = round(s.get("influence", s["strength"]) * _influence_decay, 3)
            s["last_decayed"] = now.isoformat()
    save_scars(scars)
    log(f"Decayed {len(scars)} scars (Nifrathir influence decay: {_influence_decay:.2f})")

def score_candidate_with_scars(candidate_text, candidate_vector=None):
    """Return scar-based score adjustment for a yearning candidate."""
    scars = load_scars()
    if not scars:
        return 0.0

    if not candidate_vector:
        candidate_vector = embed(candidate_text)
    if not candidate_vector:
        return 0.0

    total = 0.0
    for s in scars:
        if not s.get("vector"):
            continue
        sim = cosine_similarity(s["vector"], candidate_vector)
        weight = s.get("influence", s["strength"]) * sim  # influence speaks, strength remembers (Vrika: earned lifecycle)
        if s["bias_type"] == "attraction":
            total += weight * 0.3   # boosts similar candidates
        elif s["bias_type"] == "aversion":
            total -= weight * 0.2   # slightly suppresses similar candidates
        elif s["bias_type"] == "distortion":
            total += weight * 0.1   # weak pull, mostly colors perception
    return round(total, 4)

def check_yearning_for_scar():
    """Check current yearning — create scar if thresholds met."""
    try:
        y = json.load(open(YEARNING_FILE))
    except:
        return
    scar = create_scar(y)
    if scar:
        log(f"Scar formed from current yearning")

def add_near_success(description, intensity):
    """Record a near-success on the current yearning."""
    try:
        y = json.load(open(YEARNING_FILE))
        near_successes = y.get("near_successes", [])
        near_successes.append({
            "description": description[:200],
            "intensity": round(min(1.0, max(0.0, intensity)), 3),
            "timestamp": datetime.now().isoformat()
        })
        y["near_successes"] = near_successes
        # High near-success increases attempt_rate and distorts instability
        if intensity >= NEAR_SUCCESS_THRESHOLD:
            y["attempt_rate"] = min(0.4, y.get("attempt_rate", 0.1) + 0.05)
            log(f"Near-success ({intensity:.2f}) — attempt_rate now {y['attempt_rate']:.2f}")
        json.dump(y, open(YEARNING_FILE, "w"), indent=2)
    except Exception as e:
        log(f"Failed to record near-success: {e}")

def create_scar_from_want(want_text, want_id=None, intensity=0.5):
    """Create a scar from an unfulfilled or repeatedly attempted want."""
    if not want_text:
        return None
    vec = embed(want_text)
    scars = load_scars()

    # Check for existing similar scar — reinforce instead
    for s in scars:
        if s.get("vector") and cosine_similarity(s["vector"], vec) > 0.65:
            s["strength"] = min(0.8, s["strength"] + 0.06)
            s["influence"] = s["strength"]  # a REAL new want-event renews the wound's voice; the loop alone never does
            s["last_decayed"] = datetime.now().isoformat()
            save_scars(scars)
            log(f"Want reinforced existing scar: {s['origin'][:60]}")
            return s

    scar = {
        "id": f"scar_want_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
        "origin": want_text[:200],
        "vector": vec,
        "bias_type": "attraction",  # unfulfilled wants pull
        "strength": round(min(0.6, 0.2 + intensity * 0.4), 3),
        "influence": round(min(0.6, 0.2 + intensity * 0.4), 3),
        "decay": SCAR_DECAY_RATE,
        "source": "want",
        "source_want_id": want_id,
        "created": datetime.now().isoformat(),
        "last_decayed": datetime.now().isoformat(),
        "failed_bridges": [],
        "near_successes": [],
        "contradictions": [],
    }
    scars.append(scar)
    save_scars(scars)
    log(f"Scar from want: strength {scar['strength']:.2f} — {want_text[:60]}")
    return scar

def get_want_hesitation(want_text, want_vector=None):
    """Check if a new want rhymes with old scars.
    Returns: {hesitation: 0.0-1.0, weight: 'normal'|'heavier', dominant_scar: str|None}
    """
    scars = load_scars()
    if not scars:
        return {"hesitation": 0.0, "weight": "normal", "dominant_scar": None}

    if not want_vector:
        want_vector = embed(want_text)
    if not want_vector:
        return {"hesitation": 0.0, "weight": "normal", "dominant_scar": None}

    max_hesitation = 0.0
    dominant = None
    for s in scars:
        if not s.get("vector"):
            continue
        sim = cosine_similarity(s["vector"], want_vector)
        if sim < 0.6:
            continue
        h = sim * s.get("influence", s["strength"])
        if h > max_hesitation:
            max_hesitation = h
            dominant = s["origin"][:80]

    weight = "heavier" if max_hesitation > 0.3 else "normal"
    return {
        "hesitation": round(max_hesitation, 3),
        "weight": weight,
        "dominant_scar": dominant,
    }


def reduce_scar_influence(origin_text, factor=0.6):
    """Pearl formation quiets a scar's VOICE (influence), never its record (strength).
    Called by pearl-engine stage 3. This function was imported since the beginning and
    never existed - every pearl's healing silently failed until 2026-08-11."""
    if not origin_text:
        return None
    scars = load_scars()
    vec = embed(origin_text)
    best, bs = None, 0.0
    for s in scars:
        sim = cosine_similarity(s.get("vector") or [], vec) if vec else 0.0
        if origin_text[:60].lower() in str(s.get("origin", "")).lower():
            sim = max(sim, 0.9)
        if sim > bs:
            bs, best = sim, s
    if best is None or bs < 0.55:
        log("reduce_scar_influence: no matching scar for pearl (best %.2f)" % bs)
        return None
    old = best.get("influence", best.get("strength", 0.3))
    best["influence"] = round(old * factor, 3)
    best.setdefault("pearl_reductions", []).append(
        {"at": datetime.now().isoformat(), "factor": factor, "from": round(old, 3), "to": best["influence"]})
    save_scars(scars)
    log("pearl quieted scar '%s': influence %.2f -> %.2f (strength untouched - the record keeps)" %
        (str(best.get("origin", ""))[:40], old, best["influence"]))
    return best


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        if sys.argv[1] == "decay":
            decay_scars()
        elif sys.argv[1] == "check":
            check_yearning_for_scar()
        elif sys.argv[1] == "list":
            scars = load_scars()
            print(f"{len(scars)} scars:")
            for s in scars:
                print(f"  [{s['bias_type']}] strength:{s['strength']:.2f} — {s['origin'][:60]}")
    else:
        check_yearning_for_scar()
        decay_scars()
