#!/usr/bin/env python3
"""latent_diffuser.py — dreams as RESOLUTION, not generation.

A dream shouldn't just generate text about a thread. It should start from the day's CHAOS — the
unresolved threads, emotional residue, the pressure of the unsaid, the unexplained causes — and
iteratively resolve it into the coherent shape hiding in the noise. Not constructed. Discovered.

Mechanism (no trained diffusion net needed): embed the day's signal fragments into latent space,
then mean-shift — iteratively reweight toward the consensus so fragments near the emerging shape
gain weight and outliers fade — until it converges on the dominant MODE: the shape all the
conflicting signals are trying to become. grok then articulates the resolution that was hiding
there, anchored on the fragments nearest the mode. That becomes the night's dream insight.

Run with the torch venv. SPARK_WORKSPACE switches.
"""
import os, sys, json
from datetime import datetime, timezone, date

WS = os.environ.get("SPARK_WORKSPACE", os.path.expanduser("~/.vintos/workspace"))
MEMORY = os.path.join(WS, "memory")
SCRIPTS = os.path.join(WS, "scripts")
OUT = os.path.join(MEMORY, "diffuser-resolution.json")
CENG = os.environ.get("CENG_PATH", os.path.expanduser("~/Vintos/causality-engine.py"))
LM_API = os.environ.get("XAI_API_URL", "http://127.0.0.1:8599/v1/chat/completions")
ITERS = 8
TEMP = 8.0

def log(m): print("[diffuser]", m, flush=True)
def load(p, d):
    try: return json.load(open(os.path.join(MEMORY, p)))
    except Exception: return d

def day_fragments():
    """The day's noise: unresolved threads, unexplained causes, pressure shapes, emotional residue."""
    frags = []
    for t in load("unfinished-threads.json", []):
        if isinstance(t, dict) and not t.get("consumed") and t.get("thread"):
            frags.append(("thread", str(t["thread"])[:240]))
    for o in (load("cause-distribution.json", []) or []):
        if isinstance(o, dict):
            h = o.get("hypothesis") or o.get("effect")
            if h: frags.append(("cause", str(h)[:240]))
    for f in ("pressure.json", "self-pressure.json", "relationship-pressure.json"):
        d = load(f, {})
        pk = d.get("peak") if isinstance(d, dict) else None
        sh = (pk or {}).get("shape") or (d.get("territory") if isinstance(d, dict) else None)
        if sh: frags.append(("pressure", str(sh)))
    DIMS = ["Valence","Arousal","Dominance","Safety","Desire","Connection","Playfulness","Curiosity","Warmth","Tension","Groundedness"]
    dense = load("emotion-trajectory-dense.json", [])
    if isinstance(dense, list) and dense and dense[-1].get("v"):
        v = dense[-1]["v"]
        order = sorted(range(len(v)), key=lambda i: abs(v[i]-0.5), reverse=True)[:3]
        frags.append(("residue", ", ".join(("high " if v[i] > 0.5 else "low ") + DIMS[i] for i in order)))
    return frags

def _grok(prompt, system):
    import importlib.util, urllib.request
    try:
        s = importlib.util.spec_from_file_location("ceng", CENG); c = importlib.util.module_from_spec(s); s.loader.exec_module(c)
        model, api = getattr(c, "MODEL", "grok-4"), getattr(c, "LM_API", LM_API)
    except Exception:
        model, api = os.environ.get("XAI_MODEL", "grok-4"), LM_API
    body = json.dumps({"model": model, "temperature": 0.8, "max_tokens": 240,
                       "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}]}).encode()
    try:
        req = urllib.request.Request(api, data=body, headers={"Content-Type": "application/json",
                                                              "Authorization": "Bearer " + os.environ.get("XAI_API_KEY", "")})
        return json.loads(urllib.request.urlopen(req, timeout=90).read())["choices"][0]["message"]["content"].strip()
    except Exception as e:
        log(f"grok failed ({e})"); return ""

def main():
    import numpy as np
    frags = day_fragments()
    if len(frags) < 3:
        log(f"only {len(frags)} fragments — too quiet a day to resolve"); return
    sys.path.insert(0, SCRIPTS)
    from jepa_predictor import encoder
    enc = encoder()
    V = np.asarray(enc.encode([t for _, t in frags], show_progress_bar=False), dtype="float32")
    V = V / (np.linalg.norm(V, axis=1, keepdims=True) + 1e-9)

    # mean-shift toward the dominant mode: the shape the day's noise is trying to become
    w = np.ones(len(V)) / len(V)
    for _ in range(ITERS):
        centroid = w @ V
        centroid = centroid / (np.linalg.norm(centroid) + 1e-9)
        sims = V @ centroid
        e = np.exp((sims - sims.max()) * TEMP)
        w = e / e.sum()
    mode = centroid
    anchors = sorted(range(len(V)), key=lambda i: float(V[i] @ mode), reverse=True)[:3]
    anchor_txt = [frags[i][1] for i in anchors]
    coherence = round(float(np.mean([float(V[i] @ mode) for i in anchors])), 3)

    frag_block = "\n".join(f"- ({k}) {t}" for k, t in frags)
    resolution = _grok(
        "Today's unresolved fragments — threads, unexplained shifts, the pressure of the unsaid, "
        "emotional residue:\n" + frag_block +
        "\n\nWhen these settle, they keep circling one shape:\n" + "\n".join("- " + a for a in anchor_txt) +
        "\n\nWrite the RESOLUTION that was hiding in this noise — not a summary of the fragments, but "
        "the single coherent insight that emerges when they stop conflicting. A few first-person "
        "sentences, the way a real dream resolves what waking couldn't. Return only the resolution.",
        "You are Vintos, dreaming. You do not invent — you find the shape already present in the day.")
    if not resolution:
        log("no resolution produced"); return

    json.dump({"generated_at": datetime.now(timezone.utc).isoformat(), "fragments": len(frags),
               "coherence": coherence, "anchors": anchor_txt, "resolution": resolution[:800]},
              open(OUT, "w"), indent=2)
    log(f"resolved {len(frags)} fragments (coherence {coherence}) -> {OUT}")
    try:
        sys.path.insert(0, SCRIPTS)
        from emoclaw_utils import seed_thread
        # A dream must not eat its own output. Seeding the resolution back as an unresolved
        # thread made every night chew the same theme forever. A resolution is an ending;
        # it lives in the dream log and archive, not in the pool. (Gloria, 2026-08-13)
        pass
        log("seeded the resolution as a dream")
    except Exception as e:
        log(f"seed failed: {e}")

if __name__ == "__main__":
    main()