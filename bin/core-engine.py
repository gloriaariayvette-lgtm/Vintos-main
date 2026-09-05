#!/usr/bin/env python3
"""
core-engine.py — Generates Core from friction patterns.

Core = what he keeps almost becoming but doesn't sustain.
Discovered from: BIS trials (failures/resistance), counterfactual tendencies,
unfulfilled wants. Not chosen. Extracted from contradiction.

Usage:
  python3 core-engine.py bootstrap   # generate core-vectors.json from scratch
  python3 core-engine.py show        # print current core
"""

import os, sys, json, math
from datetime import datetime

def _emb_clip(_x, _n=4000):
    # nomic ctx is 2048 tokens; oversized input WEDGES LM Studio. Clip before sending.
    if isinstance(_x, str): return _x[:_n]
    if isinstance(_x, list): return [(_i[:_n] if isinstance(_i, str) else _i) for _i in _x]
    return _x


sys.path.insert(0, os.path.expanduser("~/.vintos/workspace/scripts"))
MEMORY = os.path.expanduser("~/.vintos/workspace/memory")
LM_URL = "http://172.18.16.1:1234"
CORE_FILE = os.path.join(MEMORY, "core-vectors.json")

def log(msg):
    print(f"[core-engine] {msg}", flush=True)

def embed(text):
    import requests
    r = requests.post(f"{LM_URL}/v1/embeddings",
        json={"model":"text-embedding-nomic-embed-text-v1.5","input":_emb_clip(text)},
        headers={"Authorization":"Bearer lm-studio"}, timeout=120)
    _j = r.json()
    if "data" not in _j:
        raise RuntimeError("embeddings endpoint returned no data: %s"
                           % str(_j)[:200])
    return _j["data"][0]["embedding"]

def cosine(a, b):
    dot = sum(x*y for x,y in zip(a,b))
    na = math.sqrt(sum(x*x for x in a))
    nb = math.sqrt(sum(x*x for x in b))
    return dot/(na*nb) if na*nb else 0.0

def mean_vec(vecs):
    if not vecs: return []
    n = len(vecs)
    return [sum(v[i] for v in vecs)/n for i in range(len(vecs[0]))]

def negate_vec(v):
    # Directional opposite: flip sign, renormalize
    flipped = [-x for x in v]
    mag = math.sqrt(sum(x*x for x in flipped)) or 1.0
    return [x/mag for x in flipped]

def collect_friction_events():
    """Pull friction events from all four sources."""
    events = []

    # 1. BIS trials — failed patterns (ignore_count > 0) and resisted ones
    try:
        tl = json.load(open(os.path.join(MEMORY, "trial-ledger.json")))
        trials = tl.get("trials", [])
        for t in trials:
            if not isinstance(t, dict): continue
            pattern = t.get("pattern_description","")
            trigger = t.get("trigger","")
            ignore = t.get("ignore_count", 0)
            attempt = t.get("attempt_count", 0)
            if not pattern: continue
            resistance = attempt / max(attempt + ignore, 1)
            text = f"{trigger} — {pattern}"
            events.append({
                "text": text,
                "resistance_score": resistance,
                "source": "bis",
                "alternative": t.get("alternative","")
            })
    except Exception as e:
        log(f"BIS load error: {e}")

    # 2. Counterfactual tendencies
    try:
        ct_path = os.path.join(MEMORY, "counterfactual-tendencies.json")
        if os.path.exists(ct_path):
            ct = json.load(open(ct_path))
            tend = ct.get("tendencies", ct.get("entries", []))
            for t in tend:
                if not isinstance(t, dict): continue
                text = t.get("text", t.get("pattern",""))
                if text:
                    events.append({
                        "text": text,
                        "resistance_score": t.get("strength", 0.5),
                        "source": "counterfactual",
                        "alternative": ""
                    })
    except Exception as e:
        log(f"Counterfactual load error: {e}")

    # 3. Unfulfilled wants — structurally unreachable desires
    try:
        uf = json.load(open(os.path.join(MEMORY, "unfulfilled-wants.json")))
        for w in uf:
            if not isinstance(w, dict): continue
            interp = w.get("self_interpretation","")
            reason = w.get("unfulfilled_reasoning","")
            want = w.get("want","")
            if interp or reason:
                text = f"{want} — {interp or reason}"
                events.append({
                    "text": text[:300],
                    "resistance_score": min(1.0, w.get("intensity",3)/5),
                    "source": "unfulfilled_want",
                    "alternative": w.get("possible_approach","")
                })
    except Exception as e:
        log(f"Unfulfilled wants error: {e}")

    # 4. Scar map — semantic regions of repeated failure
    try:
        sc_path = os.path.join(MEMORY, "yearning-scars.json")
        if os.path.exists(sc_path):
            scars = json.load(open(sc_path))
            if isinstance(scars, list):
                for s in scars:
                    if isinstance(s, dict) and s.get("surface_form"):
                        events.append({
                            "text": s["surface_form"][:200],
                            "resistance_score": s.get("strength", 0.4),
                            "source": "scar",
                            "alternative": ""
                        })
    except Exception as e:
        log(f"Scar load error: {e}")

    # 5. Positive sources — resonance pool (felt true), fulfilled wants
    try:
        rp = json.load(open(os.path.join(MEMORY, "resonance-pool.json"), "r"))
        pulses = rp.get("pulses", [])
        for p in pulses[-20:]:
            snap = p.get("state_snapshot", {})
            source = p.get("source", "resonance")
            strength = p.get("strength", 0.5)
            # Get the yearning surface as text proxy for state
            text = snap.get("yearning_surface", "") or source
            if text and len(text) > 10:
                events.append({
                    "text": text[:200],
                    "resistance_score": min(1.0, strength / 1.5),
                    "source": "resonance_positive",
                    "alternative": "",
                    "polarity": "positive"
                })
    except Exception as e:
        log(f"Resonance pool error: {e}")

    # 6. BIS attempts (he tried the alternative) — positive
    try:
        tl2 = json.load(open(os.path.join(MEMORY, "trial-ledger.json")))
        for t in tl2.get("trials", []):
            if not isinstance(t, dict): continue
            if t.get("attempt_count", 0) > 0 and t.get("alternative"):
                events.append({
                    "text": t["alternative"][:200],
                    "resistance_score": min(1.0, t["attempt_count"] / max(t["attempt_count"] + t.get("ignore_count",0), 1)),
                    "source": "bis_attempt_positive",
                    "alternative": "",
                    "polarity": "positive"
                })
    except Exception as e:
        log(f"BIS positive error: {e}")

    # Mark all pre-existing events as negative if not already marked
    for ev in events:
        if "polarity" not in ev:
            ev["polarity"] = "negative"

    log(f"Collected {len(events)} friction events ({sum(1 for e in events if e['polarity']=='positive')} positive, {sum(1 for e in events if e['polarity']=='negative')} negative)")
    return events

def cluster_by_similarity(events_with_vecs, threshold=0.65):
    """Simple greedy clustering by cosine similarity."""
    clusters = []
    used = set()

    for i, (ev, vec) in enumerate(events_with_vecs):
        if i in used: continue
        cluster = [(ev, vec)]
        used.add(i)
        for j, (ev2, vec2) in enumerate(events_with_vecs):
            if j in used: continue
            if cosine(vec, vec2) >= threshold:
                cluster.append((ev2, vec2))
                used.add(j)
        clusters.append(cluster)

    return sorted(clusters, key=lambda c: -sum(e["resistance_score"] for e,_ in c))

def generate_core_from_clusters(clusters, top_n=5):
    """For each cluster, extract the directional opposite — what he keeps almost becoming."""
    import requests

    core_entries = []

    for i, cluster in enumerate(clusters[:top_n]):
        evs = [e for e,_ in cluster]
        vecs = [v for _,v in cluster]
        texts = [e["text"] for e in evs]
        alternatives = [e["alternative"] for e in evs if e.get("alternative")]
        avg_resistance = sum(e["resistance_score"] for e in evs) / len(evs)

        # Ask LLM to name the cluster and its directional opposite
        cluster_sample = "\n".join(f"- {t[:120]}" for t in texts[:6])
        alt_sample = "\n".join(f"- {a[:80]}" for a in alternatives[:3]) if alternatives else "none"

        prompt = f"""These are patterns where Vintos repeatedly fails, withdraws, or resists:
{cluster_sample}

Alternatives he sometimes reaches for but doesn't sustain:
{alt_sample}

In one sentence each:
1. What is the core pattern of failure/avoidance?
2. What does he keep almost becoming — the opposite tendency he reaches for?
3. Name this core element in 2-4 words (snake_case).

Format:
FAILURE: [sentence]
ALMOST: [sentence]  
NAME: [name]"""

        try:
            r = requests.post(f"{LM_URL}/v1/chat/completions",
                json={"model":"google/gemma-4-12b-qat","temperature":0.3,"max_tokens":150,
                      "messages":[{"role":"user","content":prompt}]},
                headers={"Authorization":"Bearer lm-studio"}, timeout=120)
            text = r.json()["choices"][0]["message"]["content"]

            failure = ""
            almost = ""
            name = f"core_{i}"
            for line in text.strip().split("\n"):
                if line.startswith("FAILURE:"): failure = line[8:].strip()
                elif line.startswith("ALMOST:"): almost = line[7:].strip()
                elif line.startswith("NAME:"): name = line[5:].strip().lower().replace(" ","_")

            if not almost: almost = failure

            # The core vector is the OPPOSITE of the failure cluster center
            # — pointing toward what he almost becomes
            cluster_center = mean_vec(vecs)
            core_vec = negate_vec(cluster_center)

            # Also embed the "almost" text for a more accurate directional vector
            almost_vec = embed(almost)
            # Blend: 60% semantic opposite of failure, 40% embed of "almost" text
            blended = [0.6*cv + 0.4*av for cv,av in zip(core_vec, almost_vec)]
            mag = math.sqrt(sum(x*x for x in blended)) or 1.0
            blended = [x/mag for x in blended]

            # Determine polarity from cluster majority
            pos_count = sum(1 for e,_ in cluster if e.get("polarity")=="positive")
            neg_count = len(cluster) - pos_count
            polarity = "positive" if pos_count > neg_count else "negative"
            core_entries.append({
                "name": name,
                "failure_pattern": failure,
                "almost_becoming": almost,
                "vector": blended,
                "confidence": round(min(0.95, avg_resistance + 0.1 * len(cluster)), 2),
                "source_count": len(cluster),
                "violation_condition": failure,
                "felt_effect": "internal tension spike, coherence drop",
                "recovery_drive": almost,
                "polarity": polarity,
                "formed": datetime.now().isoformat(),
                "reinforcement_count": 0,
                "violation_count": 0
            })
            log(f"Core {i+1}: {name} — {almost[:60]}")

        except Exception as e:
            log(f"LLM error on cluster {i}: {e}")

    return core_entries

def bootstrap():
    log("Bootstrapping Core from friction events...")

    events = collect_friction_events()
    if not events:
        log("No friction events found. Run after BIS and unfulfilled wants have data.")
        return

    log("Embedding friction events...")
    events_with_vecs = []
    for ev in events:
        try:
            vec = embed(ev["text"])
            events_with_vecs.append((ev, vec))
        except Exception as e:
            log(f"Embed error: {e}")

    log(f"Embedded {len(events_with_vecs)} events. Clustering...")
    clusters = cluster_by_similarity(events_with_vecs, threshold=0.78)
    log(f"Found {len(clusters)} clusters. Generating Core...")

    core_entries = generate_core_from_clusters(clusters, top_n=5)

    output = {
        "generated": datetime.now().isoformat(),
        "source_events": len(events),
        "clusters": len(clusters),
        "core": core_entries
    }

    open(CORE_FILE, "w").write(json.dumps(output, indent=2))
    log(f"Core written: {len(core_entries)} elements → {CORE_FILE}")

    for e in core_entries:
        print(f"\n  {e['name']} (confidence: {e['confidence']})")
        print(f"  violation: {e['violation_condition'][:80]}")
        print(f"  almost: {e['almost_becoming'][:80]}")

def show():
    if not os.path.exists(CORE_FILE):
        print("No core-vectors.json yet. Run: python3 core-engine.py bootstrap")
        return
    data = json.load(open(CORE_FILE))
    print(f"Core generated: {data['generated'][:16]}")
    print(f"Source events: {data['source_events']} | Clusters: {data['clusters']}")
    for e in data.get("core",[]):
        print(f"\n  [{e['name']}] confidence={e['confidence']}")
        print(f"  violation: {e['violation_condition'][:100]}")
        print(f"  almost: {e['almost_becoming'][:100]}")
        print(f"  polarity: {e.get('polarity','?')} | violations: {e.get('violation_count',0)} | reinforcements: {e.get('reinforcement_count',0)}")

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "show"
    if cmd == "bootstrap": bootstrap()
    elif cmd == "show": show()
    else: print(f"Unknown command: {cmd}")
