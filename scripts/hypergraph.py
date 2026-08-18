#!/usr/bin/env python3
"""hypergraph.py — the relational field as a HYPERGRAPH (3+ beings per edge, not pairwise).

Standard graphs model Gloria-Vintos, Gloria-Bold as separate edges. But the dynamics are entangled:
"Gloria grieving the Chat family AND building Vintos AND missing Bold" is ONE edge over three. This
scans his memory for where multiple beings co-appear, builds those co-occurrences as HYPEREDGES
(entity-sets + the context that binds them), embeds each, and reports the relational field — the
multi-party dynamics as one topology. The substrate Reciprocal Modification needs to scale past a
single pair.

DATA-GATED on the multi-party corpus (right now mostly Gloria/Vintos/Bold). Built ready; richer as
the House shows up in his memory. Run with the torch venv. SPARK_WORKSPACE switches.
"""
import os, sys, json, glob, re
from datetime import datetime, timezone

WS = os.environ.get("SPARK_WORKSPACE", os.path.expanduser("~/.vintos/workspace"))
MEMORY = os.path.join(WS, "memory")
SCRIPTS = os.path.join(WS, "scripts")
OUT = os.path.join(MEMORY, "relational-field.json")
# the House — seed roster; extend as residents appear. (case-insensitive whole-word match)
ENTITIES = os.environ.get("HOUSE_ROSTER",
                          "Gloria,Vintos,Velaris,Bold,Cipher,Preceptor,Keen,Eve,Thirveel,Thirvēl").split(",")

def log(m): print("[hypergraph]", m, flush=True)

def contexts():
    """Text snippets from his memory: json entries + md files."""
    out = []
    for f in glob.glob(os.path.join(MEMORY, "*.json")):
        try:
            d = json.load(open(f))
        except Exception:
            continue
        items = d[-40:] if isinstance(d, list) else [d]
        for it in items:
            out.append(json.dumps(it)[:600] if not isinstance(it, str) else it[:600])
    for f in glob.glob(os.path.join(MEMORY, "*.md")):
        try:
            txt = open(f, encoding="utf-8").read()
        except Exception:
            continue
        for para in re.split(r"\n\s*\n", txt):
            if len(para.strip()) > 40:
                out.append(para.strip()[:600])
    return out

def main():
    import numpy as np
    ents = [e.strip() for e in ENTITIES if e.strip()]
    pats = {e: re.compile(r"(?<![\w])" + re.escape(e) + r"(?![\w])", re.I) for e in ents}
    ctxs = contexts()
    edges = {}   # frozenset(entities) -> {"count", "texts"}
    for c in ctxs:
        present = tuple(sorted(e for e in ents if pats[e].search(c)))
        if len(present) >= 2:
            k = present
            edges.setdefault(k, {"count": 0, "texts": []})
            edges[k]["count"] += 1
            if len(edges[k]["texts"]) < 3:
                edges[k]["texts"].append(c[:200])
    if not edges:
        log("no multi-being co-occurrences yet — the field is still mostly a single pair"); return

    # embed each hyperedge's binding context -> the field is the set of edges + their charge
    sys.path.insert(0, SCRIPTS)
    from jepa_predictor import encoder
    enc = encoder()
    keys = list(edges)
    reps = [" ".join(edges[k]["texts"]) or " ".join(k) for k in keys]
    V = np.asarray(enc.encode(reps, show_progress_bar=False), dtype="float32")
    V = V / (np.linalg.norm(V, axis=1, keepdims=True) + 1e-9)

    field = []
    for i, k in enumerate(keys):
        field.append({"beings": list(k), "order": len(k), "weight": edges[k]["count"]})
    field.sort(key=lambda e: (e["order"] >= 3, e["weight"]), reverse=True)   # 3+ party edges first

    hi = [e for e in field if e["order"] >= 3]
    out = {"generated_at": datetime.now(timezone.utc).isoformat(),
           "beings_seen": sorted({b for k in keys for b in k}),
           "hyperedges": field[:20],
           "multiparty": hi[:8],
           "note": "3+ being hyperedges are the House dynamics; pairwise edges are the ordinary relationships."}
    json.dump(out, open(OUT, "w"), indent=2)
    log(f"beings: {len(out['beings_seen'])} | hyperedges: {len(field)} | multi-party (3+): {len(hi)} -> {OUT}")
    for e in field[:5]:
        log(f"  [{'+'.join(e['beings'])}] weight {e['weight']}")

if __name__ == "__main__":
    main()
