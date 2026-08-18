#!/usr/bin/env python3
"""purpose_head.py — forward half of the causality split (mirror of cause_head). STANDALONE PRODUCER.

Cause_head looked BACKWARD: an effect -> the past events that produced it -> "why did this happen".
Purpose_head looks FORWARD: his active PULLS (persistent wants, unfinished threads, growth edges)
clustered into YEARNING-THREADS -> "what is this becoming for". Same division of labor: the embedding
does the one thing it's good at — grouping related pulls into coherent yearnings — and emits the
geometric signal the LLM can't feel: PERSISTENCE (how consistently a yearning recurs across time =
how strong the telos). grok then judges what each yearning is becoming for and what ABSENCE it
outlines.

Where cause's signals were traceability (confidence) + emergence (novelty), purpose's are:
  - persistence: recurrence across days x span x intensity — a durable pull is a real direction
  - coherence:   how tight the cluster is (mean cosine to centroid) — a focused vs diffuse yearning

Writes purpose-evidence.json for the reasoning stage (grok -> absence-map / yearning). NOTHING else.

Run with the torch venv:  ...emotion_model/.venv/bin/python3 purpose_head.py
SPARK_WORKSPACE switches beings.
"""
import os, sys, json
from datetime import datetime, timezone, timedelta

WS = os.environ.get("SPARK_WORKSPACE", os.path.expanduser("~/.vintos/workspace"))
MEMORY = os.path.join(WS, "memory")
SCRIPTS = os.path.join(WS, "scripts")
OUT = os.path.join(MEMORY, "purpose-evidence.json")
LOOKBACK_H = 336         # 14 days — yearning persists longer than a spike; wider window
CLUSTER_THRESH = 0.55    # cosine to a cluster centroid to join it (nomic space)
ACTIVE_MAX = 120         # cap pulls considered (most recent first)

TSKEYS = ("timestamp", "ts", "time", "at", "created_at", "generated_at")
# source tag, filename, text field(s), weight field (intensity of the pull)
PULL_SOURCES = [
    ("want",   "current-wants.json",       ("want",),   "intensity"),
    ("thread", "unfinished-threads.json",  ("thread",), "priority"),
]

def log(m): print("[purpose-head]", m, flush=True)
def load(p, d):
    try: return json.load(open(p))
    except Exception: return d

def parse_ts(x):
    if x is None: return None
    if isinstance(x, (int, float)):
        try: return datetime.fromtimestamp(x, timezone.utc)
        except Exception: return None
    try:
        d = datetime.fromisoformat(str(x).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception: return None

def entry_ts(e):
    for k in TSKEYS:
        t = parse_ts(e.get(k))
        if t: return t
    return None

def collect_pulls(now):
    """Active forward pulls: persistent wants + unfinished threads + relationship growth edges."""
    pulls, per_src = [], {}
    lo = now - timedelta(hours=LOOKBACK_H)
    for src, fname, textkeys, wkey in PULL_SOURCES:
        d = load(os.path.join(MEMORY, fname), [])
        if not isinstance(d, list): continue
        n = 0
        for e in d:
            if not isinstance(e, dict): continue
            if e.get("consumed"): continue                 # a resolved thread is no longer a pull
            if e.get("dream_only") or e.get("source") in ("somatic", "pride", "pride-mirror", "pride_mirror"):
                continue                                    # positive (somatic/pride) — not a forward yearning; matches pre-tag threads too
            ts = entry_ts(e) or now
            if ts < lo: continue
            text = " ".join(str(e.get(k)) for k in textkeys if e.get(k)).strip()
            if not text: continue
            w = e.get(wkey, 0.5)
            try: w = float(w)
            except Exception: w = 0.5
            pulls.append({"text": text[:300], "source": src, "ts": ts, "weight": w})
            n += 1
        per_src[src] = n
    # relationship growth edges — directional pulls, no per-item timestamp (treat as current)
    rel = load(os.path.join(MEMORY, "relationship-model.json"), {})
    edges = rel.get("growth_edges") if isinstance(rel, dict) else None
    if isinstance(edges, list):
        ge = 0
        for x in edges:
            t = x if isinstance(x, str) else (x.get("edge") or x.get("text") if isinstance(x, dict) else None)
            if t:
                pulls.append({"text": str(t)[:300], "source": "growth", "ts": now, "weight": 0.7})
                ge += 1
        per_src["growth"] = ge
    pulls.sort(key=lambda p: p["ts"], reverse=True)
    return pulls[:ACTIVE_MAX], per_src

def main():
    sys.path.insert(0, SCRIPTS)
    now = datetime.now(timezone.utc)
    pulls, per_src = collect_pulls(now)
    log(f"active pulls: {len(pulls)}  " + ", ".join(f"{k}:{v}" for k, v in per_src.items()))
    if not pulls:
        json.dump([], open(OUT, "w")); log("no active pulls — wrote empty"); return

    from jepa_predictor import encoder
    import numpy as np
    enc = encoder()
    V = np.asarray(enc.encode([p["text"] for p in pulls], show_progress_bar=False), dtype="float32")
    V = V / (np.linalg.norm(V, axis=1, keepdims=True) + 1e-9)   # unit rows -> dot = cosine

    # greedy agglomerative clustering by cosine to running centroid
    clusters = []   # each: {"idx": [...], "cent": vec}
    for i in range(len(pulls)):
        best, bs = None, -1.0
        for c in clusters:
            s = float(V[i] @ c["cent"])
            if s > bs: bs, best = s, c
        if best is not None and bs >= CLUSTER_THRESH:
            best["idx"].append(i)
            m = V[best["idx"]].mean(axis=0)
            best["cent"] = m / (np.linalg.norm(m) + 1e-9)
        else:
            clusters.append({"idx": [i], "cent": V[i].copy()})

    imax = max((p["weight"] for p in pulls), default=1.0) or 1.0   # normalize unknown intensity scale
    out = []
    for c in clusters:
        idx = c["idx"]
        members = [pulls[i] for i in idx]
        times = [m["ts"] for m in members]
        span_h = round((max(times) - min(times)).total_seconds() / 3600.0, 1)
        days = len({m["ts"].date() for m in members})
        intensity = round(sum(m["weight"] for m in members) / len(members), 3)
        coh = round(float(np.mean([V[i] @ c["cent"] for i in idx])), 3)   # tightness of the yearning
        srcs = {}
        for m in members: srcs[m["source"]] = srcs.get(m["source"], 0) + 1
        # persistence = durability: how many pulls converge, over how many days, spanning how long,
        # with intensity a minor bonus. Dominated by convergence+recurrence so a one-off flicker
        # (n1/day1) stays low and a recurring multi-day yearning rises. No saturation.
        size_f = min(len(idx) / 8.0, 1.0)
        days_f = min(days / 7.0, 1.0)
        span_f = min(span_h / 168.0, 1.0)
        int_f = min(intensity / imax, 1.0)
        persistence = round(0.40 * size_f + 0.35 * days_f + 0.15 * span_f + 0.10 * int_f, 3)
        rep = max(members, key=lambda m: m["weight"])   # strongest pull labels the thread
        out.append({
            "label": rep["text"][:120],
            "size": len(idx), "distinct_days": days, "span_hours": span_h,
            "intensity": intensity, "coherence": coh, "persistence": persistence,
            "sources": srcs,
            "pulls": [{"text": m["text"], "source": m["source"],
                       "ts": m["ts"].isoformat(), "weight": m["weight"]} for m in members],
        })
    out.sort(key=lambda o: (o["persistence"], o["size"]), reverse=True)

    json.dump(out, open(OUT, "w"), indent=2)
    log(f"wrote {len(out)} yearning-threads -> {OUT}")
    for o in out[:6]:
        log(f"  persist {o['persistence']}  coh {o['coherence']}  n{o['size']} "
            f"days{o['distinct_days']} {o['sources']}  :: {o['label'][:56]}")

if __name__ == "__main__":
    main()
