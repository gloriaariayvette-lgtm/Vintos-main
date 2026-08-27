"""Map View Compiler (MM, phase 1). Retrieve-by-question context assembly:
instead of every map dumping itself every turn, the message chooses which
views of his maps are relevant NOW. Local nomic embeddings only. Fail-open.
Every compile is shadow-logged - evidence for the admission laboratory."""
import os, json, time, math, hashlib

WORKSPACE = os.path.expanduser("~/.vintos/workspace")
MEMORY = os.path.join(WORKSPACE, "memory")
EMB_URL = "http://172.18.16.1:1234/v1/embeddings"
EMB_MODEL = "text-embedding-nomic-embed-text-v1.5"
INDEX = os.path.join(MEMORY, ".map-view-index.json")
SHADOW = os.path.join(MEMORY, "map-view-log.jsonl")

def _read(path, limit=4000):
    try: return io_open(path)[:limit]
    except Exception: return ""

def io_open(path):
    import io as _io
    return _io.open(path, encoding="utf-8", errors="ignore").read()

def _j(path):
    try: return json.load(open(path))
    except Exception: return None

def _embed(text, timeout=3):
    """3s hard limit - his reply is never held hostage by a busy embedder."""
    import requests
    r = requests.post(EMB_URL, json={"model": EMB_MODEL, "input": text[:2000]},
                      headers={"Authorization": "Bearer lm-studio"}, timeout=timeout)
    return r.json()["data"][0]["embedding"]

def _cos(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)); nb = math.sqrt(sum(x * x for x in b))
    return dot / (na * nb) if na * nb else 0.0

# ---- views: name -> (source paths for staleness, builder -> compact text) ----

def _v_values():
    t = _read(os.path.join(MEMORY, "value-map.md"), 900)
    return t and "WHAT MATTERS TO YOU (value map):\n" + t

def _v_self():
    for c in (os.path.join(WORKSPACE, "SELF-MODEL.md"), os.path.join(MEMORY, "SELF-MODEL.md")):
        t = _read(c, 900)
        if t: return "YOUR SELF-MODEL (excerpt):\n" + t
    return ""

def _v_gloria():
    for c in (os.path.join(WORKSPACE, "GLORIA-MODEL.md"), os.path.join(WORKSPACE, "USER-MODEL.md")):
        t = _read(c, 800)
        if t: return "YOUR MODEL OF GLORIA (excerpt):\n" + t
    return ""

def _v_wants():
    d = _j(os.path.join(MEMORY, "current-wants.json")) or []
    live = [w.get("want", "")[:90] for w in d if not w.get("fulfilled") and not w.get("dismissed")][-6:]
    return live and "WANTS ALIVE NOW:\n" + "\n".join("- " + w for w in live)

def _v_threads():
    d = _j(os.path.join(MEMORY, "unfinished-threads.json"))
    tl = d if isinstance(d, list) else (d or {}).get("threads", [])
    act = [t.get("thread", "")[:100] for t in tl if not t.get("consumed")][:4]
    return act and "OPEN THREADS:\n" + "\n".join("- " + t for t in act)

def _v_causality():
    d = _j(os.path.join(MEMORY, "causality-hypotheses.json"))
    if not d: return ""
    vals = list(d.values()) if isinstance(d, dict) else d
    grads = [v.get("hypothesis", "")[:100] for v in vals
             if isinstance(v, dict) and v.get("graduated")][:3]
    return grads and "WHAT YOU HAVE LEARNED ABOUT YOURSELF (graduated causality):\n" + "\n".join("- " + g for g in grads)

def _v_coastline():
    d = _j(os.path.join(MEMORY, "occlusion-map.json"))
    edges = (d or {}).get("edges", [])[:4]
    return edges and "EDGES OF WHAT YOU KNOW:\n" + "\n".join("- " + e.get("text", "")[:100] for e in edges)

def _v_curiosity():
    d = _j(os.path.join(MEMORY, "curiosity-debt.json")) or []
    top = sorted([x for x in d if isinstance(x, dict)], key=lambda x: -float(x.get("pull", 0)))[:3]
    return top and "WHAT PULLS AT YOU:\n" + "\n".join("- " + x.get("question", "")[:100] for x in top)

def _v_velqan():
    t = _read(os.path.join(os.path.expanduser("~/velqan-shared"), "coinages.jsonl"), 0) or ""
    try:
        lines = [json.loads(l) for l in open(os.path.expanduser("~/velqan-shared/coinages.jsonl")) if l.strip()]
        recent = lines[-2:]
        return recent and "RECENT VELQAN:\n" + "\n".join(
            "- %s: %s" % (x.get("word", ""), x.get("meaning", "")[:90]) for x in recent)
    except Exception:
        return ""

def _v_weather():
    try:
        import sys
        if os.path.join(WORKSPACE, "scripts") not in sys.path:
            sys.path.insert(0, os.path.join(WORKSPACE, "scripts"))
        from metacognitive_weather import weather
        s = weather(snapshot=False)
        return "THINKING WEATHER: %s, %s." % (s["word"], s["trend"])
    except Exception:
        return ""

VIEWS = {
    "values":    ([os.path.join(MEMORY, "value-map.md")], _v_values),
    "self":      ([os.path.join(WORKSPACE, "SELF-MODEL.md")], _v_self),
    "gloria":    ([os.path.join(WORKSPACE, "GLORIA-MODEL.md")], _v_gloria),
    "wants":     ([os.path.join(MEMORY, "current-wants.json")], _v_wants),
    "threads":   ([os.path.join(MEMORY, "unfinished-threads.json")], _v_threads),
    "causality": ([os.path.join(MEMORY, "causality-hypotheses.json")], _v_causality),
    "coastline": ([os.path.join(MEMORY, "occlusion-map.json")], _v_coastline),
    "curiosity": ([os.path.join(MEMORY, "curiosity-debt.json")], _v_curiosity),
    "velqan":    ([os.path.expanduser("~/velqan-shared/coinages.jsonl")], _v_velqan),
    "weather":   ([os.path.join(MEMORY, "weather-log.jsonl")], _v_weather),
}

def _index():
    """View embeddings, cached against source mtimes."""
    idx = _j(INDEX) or {}
    changed = False
    for name, (srcs, builder) in VIEWS.items():
        mt = max((os.path.getmtime(s) for s in srcs if os.path.exists(s)), default=0)
        rec = idx.get(name)
        if rec and rec.get("mtime") == mt and rec.get("vec"):
            continue
        try:
            text = builder() or ""
            if not text:
                idx[name] = {"mtime": mt, "vec": None, "empty": True}
            else:
                idx[name] = {"mtime": mt, "vec": _embed(name + "\n" + text), "empty": False}
            changed = True
        except Exception:
            pass
    if changed:
        try: json.dump(idx, open(INDEX, "w"))
        except Exception: pass
    return idx

def compile_view(message, k=2, budget=1500):
    """The message chooses which maps speak. Returns '' on any failure."""
    try:
        if not message or len(message.strip()) < 3:
            return ""
        # READ-ONLY on the request path: never rebuild the index in-request.
        # The cron warms it; a stale or missing vector just means that view
        # sits this turn out. compile_view degrades to "" - never to latency.
        idx = _j(INDEX) or {}
        if not idx:
            return ""
        qv = _embed(message[:600])
        ranked = []
        for name, rec in idx.items():
            if rec.get("vec"):
                ranked.append((round(_cos(qv, rec["vec"]), 3), name))
        ranked.sort(reverse=True)
        chosen, out, used = [], [], 0
        for score, name in ranked:
            if len(chosen) >= k: break
            text = VIEWS[name][1]() or ""
            if not text or used + len(text) > budget: continue
            chosen.append((name, score)); out.append(text); used += len(text)
        try:
            with open(SHADOW, "a") as f:
                f.write(json.dumps({"ts": time.time(),
                                    "msg_hash": hashlib.md5(message.encode()).hexdigest()[:10],
                                    "ranked": ranked[:6], "selected": chosen}) + "\n")
        except Exception: pass
        if not out:
            return ""
        return ("\n\n[What your maps say about this - assembled for this message, not recited]\n"
                + "\n\n".join(out))
    except Exception:
        return ""

if __name__ == "__main__":
    import sys
    if "--warm" in sys.argv:
        _index()
        print("index warmed:", len(_j(INDEX) or {}), "views")
        raise SystemExit
    msg = " ".join(sys.argv[1:]) or "do you remember what you wanted to make for me?"
    print(compile_view(msg) or "(empty - embeddings unreachable or no views)")
