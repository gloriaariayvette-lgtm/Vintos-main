#!/usr/bin/env python3
"""relational-geometry.py — Maps how Gloria and Vintos move through emotional space together.
Regions are transformation spaces, not positions. Never shown to Vintos."""

import os, json, math, hashlib
from datetime import datetime, timedelta

WORKSPACE = os.path.expanduser("~/.vintos/workspace")
MEMORY = os.path.join(WORKSPACE, "memory")
SCRIPTS = os.path.join(WORKSPACE, "scripts")
GEOMETRY_FILE = os.path.join(MEMORY, "relational-geometry.json")
LM_STUDIO = "http://172.18.16.1:1234/v1/chat/completions"

MAX_REGIONS = 24
FAMILIARITY_DECAY = 0.95
MIN_VISITS_FOR_FAMILIARITY = 3
AVOIDED_PROXIMITY_THRESHOLD = 0.75
AVOIDED_VISIT_MAX = 2

def log(msg):
    print(f"[RelGeo {datetime.now().strftime('%H:%M')}] {msg}", flush=True)

def load_geometry():
    try:
        return json.load(open(GEOMETRY_FILE))
    except:
        return {"regions": [], "snapshots": [], "last_updated": ""}

def save_geometry(data):
    data["last_updated"] = datetime.now().isoformat()
    json.dump(data, open(GEOMETRY_FILE, "w"), indent=2)

def cos_sim(a, b):
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x*y for x,y in zip(a,b))
    ma = math.sqrt(sum(x*x for x in a))
    mb = math.sqrt(sum(x*x for x in b))
    return dot / (ma * mb) if ma and mb else 0.0

def embed(text):
    import subprocess
    try:
        r = subprocess.run(
            [os.path.join(WORKSPACE, "emotion_model/.venv/bin/python3"), "-c",
             "from sentence_transformers import SentenceTransformer; import json; "
             "m = SentenceTransformer('nomic-ai/nomic-embed-text-v1', trust_remote_code=True); "
             f"print(json.dumps(m.encode({repr(text[:300])}).tolist()))"],
            capture_output=True, text=True, timeout=20
        )
        return json.loads(r.stdout.strip()) if r.returncode == 0 else []
    except:
        return []

def get_emotional_snapshot():
    """Read current emotional state as dict."""
    try:
        import sys as _es; _es.path.insert(0, SCRIPTS)
        from emoclaw_utils import get_state
        return get_state() or {}
    except:
        try:
            lines = open(os.path.join(MEMORY, "emotional-state.txt")).read().strip().split("\n")
            return {l.split(":")[0].strip(): float(l.split(":")[1].strip()) for l in lines if ":" in l}
        except:
            return {}

def compute_delta(before, after):
    """Compute emotional delta between two state snapshots."""
    if not before or not after:
        return {}
    delta = {}
    for dim in set(list(before.keys()) + list(after.keys())):
        b = before.get(dim, 0.5)
        a = after.get(dim, 0.5)
        delta[dim] = round(a - b, 4)
    return delta

def classify_outcome(delta):
    """Classify interaction outcome from emotional delta."""
    if not delta:
        return "neutral"
    connection_change = delta.get("Connection", 0)
    valence_change = delta.get("Valence", 0)
    tension_change = delta.get("Tension", 0)
    warmth_change = delta.get("Warmth", 0)
    
    if connection_change > 0.05 and valence_change > 0:
        return "deepened"
    elif tension_change > 0.08 and valence_change < -0.05:
        return "ruptured"
    elif connection_change > 0.02 or warmth_change > 0.03:
        return "resolved"
    elif abs(connection_change) < 0.02 and abs(valence_change) < 0.02:
        return "stalled"
    return "neutral"

def get_discourse_direction():
    """Get current dominant discourse direction."""
    try:
        import sys as _dd; _dd.path.insert(0, SCRIPTS)
        from self_drift import get_direction_bias
        direction, _ = get_direction_bias()
        return direction or "expand"
    except:
        return "expand"

def get_thread_context():
    """Get top active latent thread text."""
    try:
        import sys as _tc; _tc.path.insert(0, SCRIPTS)
        from latent_threads import load_threads
        data = load_threads()
        threads = data.get("threads", [])
        if threads:
            top = sorted(threads, key=lambda t: t.get("salience", 0), reverse=True)
            return top[0].get("text", top[0].get("origin", ""))[:100]
    except:
        pass
    return ""

def build_region_embedding(state, delta, direction, thread_context, outcome):
    """Build embedding input from transformation components."""
    dims = ["Valence","Arousal","Dominance","Safety","Desire","Connection",
            "Playfulness","Curiosity","Warmth","Tension","Groundedness"]
    state_vec = " ".join(f"{d}:{round(state.get(d,0.5),2)}" for d in dims)
    delta_vec = " ".join(f"d{d}:{round(delta.get(d,0),3)}" for d in dims if d in delta)
    text = f"state:{state_vec} delta:{delta_vec} direction:{direction} thread:{thread_context} outcome:{outcome}"
    return embed(text)

def record_interaction(before_state, after_state, gloria_text="", vintos_text=""):
    """Record an interaction and update geometry."""
    delta = compute_delta(before_state, after_state)
    outcome = classify_outcome(delta)
    direction = get_discourse_direction()
    thread_ctx = get_thread_context()

    vec = build_region_embedding(after_state, delta, direction, thread_ctx, outcome)
    if not vec:
        log("Embedding failed — skipping")
        return

    data = load_geometry()
    regions = data.get("regions", [])

    # Find nearest region
    nearest = None
    nearest_sim = 0.0
    for r in regions:
        sim = cos_sim(vec, r.get("center", []))
        if sim > nearest_sim:
            nearest_sim = sim
            nearest = r

    if nearest and nearest_sim > 0.72:
        # Update existing region
        nearest["visit_count"] = nearest.get("visit_count", 1) + 1
        nearest["last_visited"] = datetime.now().isoformat()
        # Update centroid (running average)
        old_center = nearest["center"]
        n = nearest["visit_count"]
        nearest["center"] = [round((old_center[i] * (n-1) + vec[i]) / n, 6) for i in range(len(vec))]
        # Update familiarity
        recency_weight = 1.0
        coherence_gain = max(0, delta.get("Connection", 0) + delta.get("Warmth", 0))
        nearest["familiarity"] = round(min(1.0, nearest.get("familiarity", 0.3) +
            (recency_weight * coherence_gain * 0.1)), 3)
        nearest["dominant_outcome"] = outcome
        log(f"Region updated: {nearest['id']} (visits:{nearest['visit_count']}, sim:{nearest_sim:.2f})")
    else:
        # Create new region
        region_id = f"reg_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        region = {
            "id": region_id,
            "center": vec,
            "visit_count": 1,
            "created": datetime.now().isoformat(),
            "last_visited": datetime.now().isoformat(),
            "familiarity": 0.1,
            "avoided": False,
            "dominant_outcome": outcome,
            "dominant_direction": direction,
            "sample_delta": {k: v for k, v in delta.items() if abs(v) > 0.02}
        }
        regions.append(region)
        log(f"New region: {region_id} (outcome:{outcome}, direction:{direction})")

    # Mark avoided regions — high proximity, low visits
    for r in regions:
        if r.get("visit_count", 0) <= AVOIDED_VISIT_MAX:
            proximity_sum = sum(cos_sim(vec, r2.get("center", [])) for r2 in regions if r2["id"] != r["id"])
            if proximity_sum > AVOIDED_PROXIMITY_THRESHOLD * len(regions):
                r["avoided"] = True

    # Trim to max regions
    if len(regions) > MAX_REGIONS:
        regions.sort(key=lambda r: r.get("familiarity", 0) * r.get("visit_count", 1))
        regions = regions[-MAX_REGIONS:]

    data["regions"] = regions
    save_geometry(data)

def get_current_region():
    """Find which region we're currently in."""
    state = get_emotional_snapshot()
    direction = get_discourse_direction()
    thread_ctx = get_thread_context()
    vec = build_region_embedding(state, {}, direction, thread_ctx, "neutral")
    if not vec:
        return None
    data = load_geometry()
    regions = data.get("regions", [])
    nearest = None
    nearest_sim = 0.0
    for r in regions:
        sim = cos_sim(vec, r.get("center", []))
        if sim > nearest_sim:
            nearest_sim = sim
            nearest = r
    if nearest and nearest_sim > 0.5:
        return nearest
    return None

def get_discourse_bias():
    """Return discourse direction bias based on current region familiarity."""
    region = get_current_region()
    if not region:
        return ""
    familiarity = region.get("familiarity", 0)
    avoided = region.get("avoided", False)
    dominant_dir = region.get("dominant_direction", "")
    
    if avoided:
        return "expand"  # push toward unexplored
    if familiarity > 0.7:
        return dominant_dir or "refine"  # familiar territory — refine or hold
    if familiarity < 0.2:
        return "expand"  # new territory — open up
    return dominant_dir or "expand"

def get_unexplored_pressure():
    """How much pull toward unexplored regions."""
    try:
        import sys as _up; _up.path.insert(0, SCRIPTS)
        from emoclaw_utils import get_state
        state = get_state() or {}
        curiosity = state.get("Curiosity", 0.5)
    except:
        curiosity = 0.5
    data = load_geometry()
    regions = data.get("regions", [])
    unvisited = [r for r in regions if r.get("visit_count", 0) <= 1]
    density = len(unvisited) / max(len(regions), 1)
    return round(density * curiosity, 3)

def feed_from_absence_map():
    """Pull high-intensity absences into geometry as avoided regions."""
    try:
        absence_file = os.path.join(MEMORY, "absence-cold.json")
        data_a = json.load(open(absence_file))
        absences = data_a.get("absences", [])
        data = load_geometry()
        regions = data.get("regions", [])
        count = 0
        for a in absences:
            if a.get("intensity", 0) < 0.4:
                continue
            vec = a.get("vector", [])
            if not vec:
                continue
            # Check if already represented
            already = False
            for r in regions:
                if cos_sim(vec, r.get("center", [])) > 0.8:
                    already = True
                    r["avoided"] = True
                    break
            if not already:
                region_id = f"absence_{a['id']}"
                regions.append({
                    "id": region_id,
                    "center": vec,
                    "visit_count": 0,
                    "created": datetime.now().isoformat(),
                    "last_visited": None,
                    "familiarity": 0.0,
                    "avoided": True,
                    "dominant_outcome": "unvisited",
                    "dominant_direction": "expand",
                    "source": "absence-map",
                    "description": a.get("description", "")[:100]
                })
                count += 1
        data["regions"] = regions
        save_geometry(data)
        log(f"Fed {count} absence regions into geometry")
    except Exception as e:
        log(f"Absence feed error: {e}")

if __name__ == "__main__":
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    if cmd == "feed_absences":
        feed_from_absence_map()
    elif cmd == "status":
        data = load_geometry()
        regions = data.get("regions", [])
        print(f"{len(regions)} regions")
        for r in sorted(regions, key=lambda x: x.get("familiarity",0), reverse=True)[:5]:
            avoided = " [AVOIDED]" if r.get("avoided") else ""
            print(f"  {r['id']}: visits={r.get('visit_count',0)} familiarity={r.get('familiarity',0):.2f} outcome={r.get('dominant_outcome','?')}{avoided}")
        region = get_current_region()
        if region:
            print(f"Current region: {region['id']}")
        print(f"Unexplored pressure: {get_unexplored_pressure():.3f}")
        print(f"Discourse bias: {get_discourse_bias()}")
