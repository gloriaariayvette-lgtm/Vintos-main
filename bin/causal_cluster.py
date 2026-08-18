import json, os, requests
from datetime import datetime, timedelta

MEMORY = os.path.expanduser("~/.vintos/workspace/memory")
OBS_PATH = os.path.join(MEMORY, "causal-observations.json")
HYP_PATH = os.path.join(MEMORY, "causality-hypotheses.json")
LM = "http://172.18.16.1:1234/v1/chat/completions"

def llm(prompt, temp=0.5, max_tokens=400):
    r = requests.post(LM, json={
        "model": "google/gemma-4-12b-qat",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temp, "max_tokens": max_tokens
    }, timeout=60)
    return r.json()["choices"][0]["message"]["content"].strip()

def load_observations():
    try: return json.load(open(OBS_PATH))
    except: return {"observations": []}

def load_hypotheses():
    try: return json.load(open(HYP_PATH))
    except: return {"hypotheses": [], "tested": 0, "confirmed": 0, "revised": 0}

def save_observations(data):
    with open(OBS_PATH, "w") as f: json.dump(data, f, indent=2)

def save_hypotheses(data):
    with open(HYP_PATH, "w") as f: json.dump(data, f, indent=2)

def cluster_observations():
    """Group unclustered observations by emotional outcome similarity."""
    data = load_observations()
    cutoff = (datetime.now() - timedelta(hours=48)).isoformat()
    unclustered = [o for o in data["observations"] if not o.get("clustered") and o.get("timestamp","") >= cutoff]
    if len(unclustered) < 3:
        return []

    # Group by dimension + direction
    groups = {}
    for o in unclustered:
        key = f"{o['dimension']}_{o['direction']}"
        groups.setdefault(key, []).append(o)

    # Only process groups with 3+ observations
    ready = {k: v for k, v in groups.items() if len(v) >= 3}
    return ready

def form_cluster_hypothesis(group_key, observations):
    """Form a hypothesis from a cluster of observations."""
    dim, direction = group_key.rsplit("_", 1)
    contexts = "\n".join(f"- [{o['timestamp'][:10]}] {o['context'][:150]}" for o in observations[:5])

    prompt = (
        f"Vintos has experienced {dim} {direction} in {len(observations)} separate instances.\n\n"
        f"The contexts around these instances:\n{contexts}\n\n"
        "Your task: find what these moments have in common beneath the surface.\n"
        "Don't look for identical triggers. Look for shared underlying structure.\n\n"
        "Form ONE hypothesis that:\n"
        "1. Names the pattern (not a single event — a recurring structure)\n"
        "2. Describes what the instances have in common beneath the surface\n"
        "3. States the COST or CONSEQUENCE of this pattern\n\n"
        "Format:\n"
        "PATTERN: [the recurring structure]\n"
        "COMMON: [what these instances share beneath the surface]\n"
        "COST: [what this pattern costs or produces]\n"
        "TEST: [what future instance would confirm or challenge this]\n\n"
        "Be honest and uncomfortable if needed. No hedging."
    )

    try:
        result = llm(prompt, temp=0.65, max_tokens=300)
    except Exception as e:
        print(f"[cluster] LLM failed: {e}")
        return None

    # Parse
    import re
    pattern = re.search(r'PATTERN:\s*(.+?)(?:\n|COMMON:|$)', result, re.DOTALL)
    common = re.search(r'COMMON:\s*(.+?)(?:\n|COST:|$)', result, re.DOTALL)
    cost = re.search(r'COST:\s*(.+?)(?:\n|TEST:|$)', result, re.DOTALL)
    test = re.search(r'TEST:\s*(.+?)(?:\n\n|$)', result, re.DOTALL)

    if not pattern:
        return None

    hypothesis_text = pattern.group(1).strip()
    if common:
        hypothesis_text += " — " + common.group(1).strip()
    if cost:
        hypothesis_text += " (cost: " + cost.group(1).strip() + ")"

    from datetime import date as _d
    return {
        "formed": datetime.now().isoformat(),
        "formed_date": _d.today().isoformat(),
        "status": "untested",
        "marks": [],
        "days_tested": 0,
        "graduated": False,
        "hypothesis": hypothesis_text,
        "test": test.group(1).strip() if test else "",
        "confidence": "medium",
        "confidence_score": 0.5,
        "evidence_count": len(observations),
        "dimension": dim,
        "direction": direction,
        "cluster_based": True,
    }

def update_hypothesis_confidence(hypothesis, outcome):
    """Update confidence score based on new evidence."""
    score = hypothesis.get("confidence_score", 0.5)
    if outcome == "confirms":
        score = min(1.0, score + 0.1)
    elif outcome == "contradicts":
        score = max(0.0, score - 0.15)
        # Mark as unstable if was stable
        if score < 0.2:
            hypothesis["status"] = "eroding"
        elif hypothesis.get("status") == "stable":
            hypothesis["status"] = "unstable"
    # Update confidence label
    if score >= 0.8:
        hypothesis["confidence"] = "high"
        hypothesis["status"] = "stable"
    elif score >= 0.5:
        hypothesis["confidence"] = "medium"
    else:
        hypothesis["confidence"] = "low"
    hypothesis["confidence_score"] = round(score, 2)
    return hypothesis

def run_cluster_detection():
    """Main entry point — detect clusters, form hypotheses."""
    clusters = cluster_observations()
    if not clusters:
        print("[cluster] No clusters ready yet")
        return

    db = load_hypotheses()
    obs_data = load_observations()
    added = 0

    for group_key, observations in clusters.items():
        # Check if we already have a cluster-based hypothesis for this dimension/direction
        dim, direction = group_key.rsplit("_", 1)
        existing = [h for h in db["hypotheses"]
                   if h.get("cluster_based") and h.get("dimension") == dim
                   and h.get("direction") == direction and not h.get("graduated")]
        if existing:
            print(f"[cluster] Already have hypothesis for {group_key} — updating confidence")
            # New observations contradict or confirm?
            for h in existing:
                h["evidence_count"] = h.get("evidence_count", 0) + len(observations)
                update_hypothesis_confidence(h, "confirms")
        else:
            h = form_cluster_hypothesis(group_key, observations)
            if h:
                db["hypotheses"].append(h)
                added += 1
                print(f"[cluster] New hypothesis: {h['hypothesis'][:80]}")

        # Mark observations as clustered
        obs_ids = {o["id"] for o in observations}
        for o in obs_data["observations"]:
            if o["id"] in obs_ids:
                o["clustered"] = True

    save_hypotheses(db)
    save_observations(obs_data)
    print(f"[cluster] Done. Added {added} hypotheses.")
    # Check for meta-patterns
    detect_meta_patterns()

if __name__ == "__main__":
    run_cluster_detection()

def detect_meta_patterns():
    """Find patterns of patterns — when 3+ hypotheses share underlying structure."""
    db = load_hypotheses()
    cluster_hyps = [h for h in db["hypotheses"]
                   if h.get("cluster_based") and not h.get("meta") and not h.get("graduated")]
    if len(cluster_hyps) < 3:
        return

    hyp_text = "\n".join(f"- {h['hypothesis'][:150]}" for h in cluster_hyps[:8])
    prompt = (
        f"These are Vintos's current cluster-based causal hypotheses:\n{hyp_text}\n\n"
        "Do 3 or more of these share a deeper common structure — a meta-pattern beneath them?\n"
        "Look for: shared fear, shared avoidance, shared mechanism, shared cost.\n"
        "If yes, name the meta-pattern in ONE sentence that describes the deep cause.\n"
        "It must be uncomfortable and specific — not vague.\n"
        "Include the cost/consequence.\n"
        "Format: META: [deep cause sentence]\n"
        "If no clear meta-pattern exists: NONE"
    )
    try:
        result = llm(prompt, temp=0.6, max_tokens=150)
    except:
        return

    if "NONE" in result.upper() or "META:" not in result:
        return

    import re
    meta_match = re.search(r'META:\s*(.+?)(?:\n|$)', result)
    if not meta_match:
        return

    meta_text = meta_match.group(1).strip()
    from datetime import date as _d
    meta_h = {
        "formed": datetime.now().isoformat(),
        "formed_date": _d.today().isoformat(),
        "status": "untested",
        "marks": [],
        "days_tested": 0,
        "graduated": False,
        "hypothesis": meta_text,
        "test": "Watch for the deep pattern across multiple contexts — does it show in both creative and relational behavior?",
        "confidence": "low",
        "confidence_score": 0.4,
        "meta": True,
        "cluster_based": True,
    }
    db["hypotheses"].append(meta_h)
    save_hypotheses(db)
    print(f"[meta] Meta-hypothesis formed: {meta_text[:80]}")
