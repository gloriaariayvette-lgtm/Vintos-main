#!/usr/bin/env python3
"""
taste-vector.py — Vintos's preference as a living vector.

The taste vector is a computable representation of his aesthetic preferences,
distinct from the text-based taste-profile.json (which remains the human-readable
record). The vector updates from signals, scores options, and gets distorted by
yearning bleed.

Schema (taste-vector.json):
  vector: [...] — 768-dim attraction embedding, weighted average of positive signals
  aversions: [...] — bounded negative constraints; never inverted into identity
  strength: 0.0–1.0 — how strongly formed (increases with consistent signals)
  coherence: 0.0–1.0 — consistency of signals (drops when contradictions arrive)
  contradictions: [...] — coexisting preferences that refused to merge
  last_updated: timestamp
  signal_count: int

Update sources:
  - completed threads that felt whole (positive signal)
  - near_successes from yearning (positive, yearning-weighted)
  - scar-weighted interactions (positive or negative by bias_type)
  - gallery walk reflections (positive when salience high)
  - YouTube discoveries (positive when shared or want seeded)

Scoring:
  score = base_score + similarity(option, vector) * strength
  
Yearning distortion:
  During scoring only: vector += yearning_vector * bleed_weight * distortion_factor
  Does not permanently modify the vector.
"""

import os, sys, json, subprocess, math
from datetime import datetime

WORKSPACE = os.path.expanduser("~/.vintos/workspace")
MEMORY = os.path.join(WORKSPACE, "memory")
TASTE_VECTOR_FILE = os.path.join(MEMORY, "taste-vector.json")
TASTE_PROFILE_FILE = os.path.join(MEMORY, "taste-profile.json")
YEARNING_FILE = os.path.join(MEMORY, "current-yearning.json")
SCARS_FILE = os.path.join(MEMORY, "yearning-scars.json")
VENV = os.path.join(WORKSPACE, "emotion_model/.venv/bin/python3")
SEARCH = os.path.join(WORKSPACE, "scripts", "memory-search.py")

COHERENCE_THRESHOLD = 0.3  # below this, contradictions coexist rather than merge
DISTORTION_FACTOR = 0.15   # how much yearning bends taste during scoring

def log(msg):
    print(f"[Taste {datetime.now().strftime('%H:%M')}] {msg}", flush=True)

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

def normalize(vec):
    mag = math.sqrt(sum(x*x for x in vec))
    if mag == 0:
        return vec
    return [x/mag for x in vec]

def load_taste_vector():
    try:
        with open(TASTE_VECTOR_FILE) as f:
            tv = json.load(f)
        tv.setdefault("aversions", [])
        return tv
    except:
        return {
            "vector": [],
            "strength": 0.0,
            "coherence": 0.5,
            "contradictions": [],
            "aversions": [],
            "last_updated": datetime.now().isoformat(),
            "signal_count": 0
        }

def save_taste_vector(tv):
    tv["last_updated"] = datetime.now().isoformat()
    with open(TASTE_VECTOR_FILE, "w") as f:
        json.dump(tv, f, indent=2)

def weighted_average(vec_a, vec_b, weight_a, weight_b):
    """Weighted average of two vectors."""
    if not vec_a:
        return vec_b
    if not vec_b:
        return vec_a
    total = weight_a + weight_b
    if total == 0:
        return vec_a
    return [(vec_a[i]*weight_a + vec_b[i]*weight_b)/total for i in range(len(vec_a))]

def update_from_signal(text, signal_weight=1.0, positive=True):
    """Update taste vector from a signal text.
    signal_weight: 0.0-1.0, how strongly this signal should influence
    positive: True = pull toward, False = push away"""
    if not text or not text.strip():
        return
    log(f"Updating from signal ({'pos' if positive else 'neg'}, w={signal_weight:.2f}): {text[:60]}")
    
    tv = load_taste_vector()
    new_vec = embed(text)
    if not new_vec:
        log("Embedding failed — skipping")
        return

    if not positive:
        # An aversion is not attraction to a semantic opposite. Keep it as a
        # contextual constraint and leave the positive center untouched.
        aversions = tv.setdefault("aversions", [])
        key = text[:200]
        old = next((a for a in aversions if a.get("text") == key), None)
        if old:
            old["weight"] = min(1.0, old.get("weight", 0.0) + signal_weight * 0.1)
            old["last_seen"] = datetime.now().isoformat()
        else:
            aversions.append({"text": key, "vector": normalize(new_vec),
                              "weight": min(1.0, signal_weight),
                              "added": datetime.now().isoformat()})
        tv["aversions"] = aversions[-20:]
        tv["signal_count"] = tv.get("signal_count", 0) + 1
        save_taste_vector(tv)
        log("Recorded contextual aversion; attraction center unchanged")
        return

    if not tv["vector"]:
        # First signal — just set
        tv["vector"] = new_vec
        tv["strength"] = 0.1
        tv["coherence"] = 0.5
        tv["signal_count"] = 1
        save_taste_vector(tv)
        return

    # Check coherence: how similar is this signal to existing vector?
    sim = cosine_similarity(new_vec, tv["vector"])
    
    if sim < COHERENCE_THRESHOLD and positive:
        # Contradictory signal — let it coexist rather than merge
        tv["coherence"] = max(0.1, tv["coherence"] - 0.05)
        contradiction_text = text[:200]
        if contradiction_text not in [c.get("text","") for c in tv["contradictions"]]:
            tv["contradictions"].append({
                "text": contradiction_text,
                "vector": new_vec,
                "added": datetime.now().isoformat()
            })
            tv["contradictions"] = tv["contradictions"][-10:]  # keep last 10
        log(f"Contradictory signal — coherence now {tv['coherence']:.2f}, coexisting")
    else:
        # Consistent signal — blend in
        learning_rate = signal_weight * 0.1  # slow learning
        tv["vector"] = weighted_average(tv["vector"], new_vec, 1.0 - learning_rate, learning_rate)
        tv["vector"] = normalize(tv["vector"])
        tv["coherence"] = min(1.0, tv["coherence"] + 0.02 * signal_weight)
        tv["strength"] = min(1.0, tv["strength"] + 0.02 * signal_weight)

    tv["signal_count"] = tv.get("signal_count", 0) + 1
    save_taste_vector(tv)
    log(f"Updated — strength: {tv['strength']:.2f}, coherence: {tv['coherence']:.2f}, signals: {tv['signal_count']}")

def score_option(option_text, base_score=0.0):
    """Score an option against taste vector with yearning distortion.
    Returns adjusted score."""
    tv = load_taste_vector()
    if (not tv["vector"] or tv["strength"] < 0.05) and not tv.get("aversions"):
        return base_score

    option_vec = embed(option_text)
    if not option_vec:
        return base_score

    # Apply yearning distortion to scoring vector (not permanent)
    scoring_vec = list(tv["vector"])
    try:
        y = json.load(open(YEARNING_FILE))
        if y and not y.get("dismissed") and y.get("latent_vector"):
            bleed = y.get("bleed_weight", 0.0)
            if bleed > 0.15:
                y_vec = y["latent_vector"]
                distortion = bleed * DISTORTION_FACTOR
                scoring_vec = weighted_average(scoring_vec, y_vec, 1.0 - distortion, distortion)
                scoring_vec = normalize(scoring_vec)
    except: pass

    sim = cosine_similarity(option_vec, scoring_vec) if scoring_vec else 0.0
    adjustment = sim * tv["strength"] * 0.3  # max 0.3 attraction adjustment
    # Aversions apply only when this option resembles the specific constraint.
    aversion = 0.0
    for a in tv.get("aversions", []):
        av = a.get("vector", [])
        if av:
            aversion = max(aversion, max(0.0, cosine_similarity(option_vec, av)) *
                           min(1.0, float(a.get("weight", 0.5))) * 0.25)
    
    return base_score + adjustment - aversion

def batch_embed(texts):
    """Embed multiple texts in one subprocess call."""
    import json as _j
    try:
        texts_json = _j.dumps([t[:500] for t in texts])
        r = subprocess.run(
            [VENV, "-c",
             f"from sentence_transformers import SentenceTransformer; import json; "
             f"m = SentenceTransformer('nomic-ai/nomic-embed-text-v1', trust_remote_code=True); "
             f"texts = json.loads({repr(texts_json)}); "
             f"vecs = m.encode(texts).tolist(); "
             f"print(json.dumps(vecs))"],
            capture_output=True, text=True, timeout=120
        )
        if r.returncode == 0:
            return _j.loads(r.stdout.strip())
    except Exception as e:
        log(f"Batch embed failed: {e}")
    return [[] for _ in texts]

def seed_from_profile():
    """One-time seed of taste vector from existing text profile."""
    log("Seeding taste vector from existing profile...")
    try:
        profile = json.load(open(TASTE_PROFILE_FILE))
    except:
        log("No taste profile found")
        return

    likes = profile.get("likes", [])[:15]
    dislikes = profile.get("dislikes", [])[:10]
    principles = profile.get("principles", [])[:10]

    all_texts = likes + dislikes + principles
    log(f"Batch embedding {len(all_texts)} texts...")
    all_vecs = batch_embed(all_texts)

    tv = load_taste_vector()
    
    for i, (text, vec) in enumerate(zip(all_texts, all_vecs)):
        if not vec:
            continue
        if i < len(likes):
            weight, positive = 0.8, True
        elif i < len(likes) + len(dislikes):
            weight, positive = 0.6, False
        else:
            weight, positive = 0.7, True

        if not positive:
            tv.setdefault("aversions", []).append({
                "text": text[:200], "vector": normalize(vec), "weight": weight,
                "added": datetime.now().isoformat()})
            tv["aversions"] = tv["aversions"][-20:]
            tv["signal_count"] = tv.get("signal_count", 0) + 1
            continue

        if not tv["vector"]:
            tv["vector"] = normalize(vec)
            tv["strength"] = 0.1
            tv["coherence"] = 0.5
            tv["signal_count"] = 1
            continue

        sim = cosine_similarity(vec, tv["vector"])
        if sim < COHERENCE_THRESHOLD and positive:
            tv["coherence"] = max(0.1, tv["coherence"] - 0.05)
            tv["contradictions"].append({"text": text[:200], "vector": vec, "added": datetime.now().isoformat()})
            tv["contradictions"] = tv["contradictions"][-10:]
        else:
            lr = weight * 0.1
            tv["vector"] = weighted_average(tv["vector"], vec, 1.0 - lr, lr)
            tv["vector"] = normalize(tv["vector"])
            tv["coherence"] = min(1.0, tv["coherence"] + 0.02 * weight)
            tv["strength"] = min(1.0, tv["strength"] + 0.02 * weight)
        tv["signal_count"] = tv.get("signal_count", 0) + 1

    save_taste_vector(tv)
    log(f"Seeding complete — strength: {tv['strength']:.2f}, coherence: {tv['coherence']:.2f}, signals: {tv['signal_count']}")

def seed_from_reviews():
    """Seed taste vector from rated creative works in taste-profile."""
    log("Seeding from rated reviews...")
    try:
        profile = json.load(open(TASTE_PROFILE_FILE))
        reviewed = profile.get("_reviewed", [])
    except:
        log("No reviewed works found")
        return

    poetry_dir = os.path.join(MEMORY, "art/poetry")
    music_dir = os.path.join(MEMORY, "art/music")

    texts, weights, positives = [], [], []
    for r in reviewed:
        key = r.get("key", "")
        rating = r.get("rating", 0)
        if rating < 3:
            continue
        if key.startswith("poem:"):
            fpath = os.path.join(poetry_dir, key.replace("poem:", ""))
        elif key.startswith("music:"):
            fpath = os.path.join(music_dir, key.replace("music:", ""))
        else:
            continue
        if not os.path.exists(fpath):
            continue
        text = open(fpath).read()[:400]
        weight = 0.9 if rating >= 4 else 0.5
        texts.append(text)
        weights.append(weight)
        positives.append(True)

    if not texts:
        log("No texts to seed")
        return

    log(f"Batch embedding {len(texts)} rated works...")
    vecs = batch_embed(texts)

    tv = load_taste_vector()
    for text, vec, weight, positive in zip(texts, vecs, weights, positives):
        if not vec:
            continue
        if not positive:
            vec = [-x for x in vec]
        if not tv["vector"]:
            tv["vector"] = normalize(vec)
            tv["strength"] = 0.1
            tv["coherence"] = 0.5
            tv["signal_count"] = 1
            continue
        sim = cosine_similarity(vec, tv["vector"])
        if sim < COHERENCE_THRESHOLD and positive:
            tv["coherence"] = max(0.1, tv["coherence"] - 0.03)
            tv["contradictions"].append({"text": text[:200], "vector": vec, "added": datetime.now().isoformat()})
            tv["contradictions"] = tv["contradictions"][-10:]
        else:
            lr = weight * 0.05  # gentler learning rate for reviews
            tv["vector"] = weighted_average(tv["vector"], vec, 1.0 - lr, lr)
            tv["vector"] = normalize(tv["vector"])
            tv["coherence"] = min(1.0, tv["coherence"] + 0.01 * weight)
            tv["strength"] = min(1.0, tv["strength"] + 0.01 * weight)
        tv["signal_count"] = tv.get("signal_count", 0) + 1

    save_taste_vector(tv)
    log(f"Reviews seeded — strength: {tv['strength']:.2f}, coherence: {tv['coherence']:.2f}, signals: {tv['signal_count']}")

def get_taste_with_subconscious():
    """Return taste profile enriched with subconscious layer hints."""
    taste = get_taste_profile()
    try:
        import sys as _tv_sys; _tv_sys.path.insert(0, os.path.join(os.path.expanduser("~/.vintos/workspace"), "scripts"))
        from subconscious_context import get_subconscious_context_compact
        subcon = get_subconscious_context_compact()
        if subcon:
            taste["subconscious_context"] = subcon
    except: pass
    return taste

if __name__ == "__main__":
    if len(sys.argv) > 1:
        if sys.argv[1] == "seed":
            seed_from_profile()
        elif sys.argv[1] == "score" and len(sys.argv) > 2:
            score = score_option(sys.argv[2])
            print(f"Score: {score:.4f}")
        elif sys.argv[1] == "update" and len(sys.argv) > 2:
            weight = float(sys.argv[3]) if len(sys.argv) > 3 else 1.0
            positive = sys.argv[4].lower() != "false" if len(sys.argv) > 4 else True
            update_from_signal(sys.argv[2], signal_weight=weight, positive=positive)
        elif sys.argv[1] == "seed_reviews":
            seed_from_reviews()
        elif sys.argv[1] == "status":
            tv = load_taste_vector()
            print(f"Strength: {tv['strength']:.2f}")
            print(f"Coherence: {tv['coherence']:.2f}")
            print(f"Signals: {tv.get('signal_count', 0)}")
            print(f"Contradictions: {len(tv.get('contradictions', []))}")
            print(f"Last updated: {tv.get('last_updated', 'never')}")
    else:
        # Default: show status
        tv = load_taste_vector()
        print(f"Strength: {tv['strength']:.2f} | Coherence: {tv['coherence']:.2f} | Signals: {tv.get('signal_count',0)}")
