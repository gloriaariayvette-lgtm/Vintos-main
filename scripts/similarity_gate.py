#!/usr/bin/env python3
"""similarity_gate.py — stops fulfilled wants and resolved threads from re-seeding.
Embeds with nomic-embed-text-v1 via the emotion venv (same as yearning/latent threads).
Fail-open: any error means no block — a broken gate must never silence a real want."""
import os, json, math, subprocess
from datetime import datetime, timedelta

WORKSPACE = os.path.expanduser("~/.vintos/workspace")
MEMORY = os.path.join(WORKSPACE, "memory")
VENV = os.path.join(WORKSPACE, "emotion_model/.venv/bin/python3")
CACHE = os.path.join(MEMORY, ".similarity-gate-vectors.json")
WANT_THRESHOLD = 0.72
THREAD_THRESHOLD = 0.78
WANT_WINDOW_DAYS = 45
THREAD_WINDOW_DAYS = 21

def _embed_many(texts):
    if not texts: return []
    code = ("from sentence_transformers import SentenceTransformer; import json,sys; "
            "m=SentenceTransformer('nomic-ai/nomic-embed-text-v1', trust_remote_code=True); "
            "texts=json.load(sys.stdin); print(json.dumps([m.encode(t[:500]).tolist() for t in texts]))")
    r = subprocess.run([VENV, "-c", code], input=json.dumps(texts),
                       capture_output=True, text=True, timeout=120)
    if r.returncode != 0: raise RuntimeError(r.stderr[:200])
    return json.loads(r.stdout.strip())

def _cos(a, b):
    if not a or not b or len(a) != len(b): return 0.0
    dot = sum(x*y for x, y in zip(a, b))
    ma = math.sqrt(sum(x*x for x in a)); mb = math.sqrt(sum(x*x for x in b))
    return dot/(ma*mb) if ma and mb else 0.0

def _recent(entries, key_ts, days):
    cutoff = datetime.now() - timedelta(days=days)
    out = []
    for e in entries:
        try:
            if datetime.fromisoformat(str(e.get(key_ts, ""))[:19]) >= cutoff: out.append(e)
        except Exception: pass
    return out

def _corpus_vectors(items, cache_prefix):
    """items: list of (id, text). Returns [(text, vector)] using the on-disk cache."""
    try: cache = json.load(open(CACHE))
    except Exception: cache = {}
    missing = [(i, t) for i, t in items if f"{cache_prefix}:{i}" not in cache]
    if missing:
        vecs = _embed_many([t for _, t in missing])
        for (i, t), v in zip(missing, vecs):
            cache[f"{cache_prefix}:{i}"] = v
        try: json.dump(cache, open(CACHE, "w"))
        except Exception: pass
    return [(t, cache.get(f"{cache_prefix}:{i}")) for i, t in items if cache.get(f"{cache_prefix}:{i}")]

def check_want_against_fulfilled(text, threshold=WANT_THRESHOLD):
    """Non-None result = too similar to a recently fulfilled want."""
    try: fulfilled = json.load(open(os.path.join(MEMORY, "fulfilled-wants.json")))
    except Exception: return None
    recent = _recent(fulfilled, "fulfilled_at", WANT_WINDOW_DAYS)[-25:]
    items = [(e.get("id", str(n)), e.get("want", "")) for n, e in enumerate(recent) if e.get("want")]
    if not items: return None
    qv = _embed_many([text])[0]
    best, best_t = 0.0, ""
    for t, v in _corpus_vectors(items, "fw"):
        s = _cos(qv, v)
        if s > best: best, best_t = s, t
    return {"matched": best_t, "similarity": best} if best >= threshold else None

def check_thread_against_resolved(text, threshold=THREAD_THRESHOLD):
    """Compare a candidate thread against recent pearls, black pearls, and retired threads."""
    items = []
    try:
        retired = json.load(open(os.path.join(MEMORY, "retired-threads.json")))
        for e in _recent(retired, "timestamp", THREAD_WINDOW_DAYS)[-25:]:
            t = (e.get("thread") or e.get("text") or "") if isinstance(e, dict) else ""
            if t: items.append((e.get("id", t[:20]), t))
    except Exception: pass
    try:
        idx = json.load(open(os.path.join(MEMORY, "pearls", "index.json")))
        entries = idx if isinstance(idx, list) else idx.get("pearls", idx.get("entries", []))
        for e in entries[-12:]:
            if isinstance(e, dict):
                t = e.get("thread") or e.get("lesson") or e.get("text") or e.get("summary") or ""
                if t: items.append((e.get("id", t[:20]), t))
    except Exception: pass
    try:
        bp = os.path.join(MEMORY, "black-pearls")
        for fn in sorted(os.listdir(bp))[-8:]:
            try:
                e = json.load(open(os.path.join(bp, fn)))
                t = e.get("thread", "") if isinstance(e, dict) else ""
                if t: items.append((fn, t))
            except Exception: pass
    except Exception: pass
    if not items: return None
    qv = _embed_many([text])[0]
    best, best_t = 0.0, ""
    for t, v in _corpus_vectors(items, "rt"):
        s = _cos(qv, v)
        if s > best: best, best_t = s, t
    return {"matched": best_t, "similarity": best} if best >= threshold else None


# ============================================================================
# check_want — unified gate (fulfilled + dismissed + active). Added by patch.
# Dismissal is the strongest "never resurface" signal, so it blocks lowest.
# ============================================================================
DISMISSED_THRESHOLD = 0.72
ACTIVE_THRESHOLD    = 0.72
FULFILLED_THRESHOLD = 0.72
DISMISSED_WINDOW_DAYS = 60
DISMISSED_STORE = os.path.join(MEMORY, "dismissed-wants.json")

def _harvest_dismissed():
    """Persist dismissed wants so deleting them from current-wants.json doesn't erase
    the block memory. Returns the windowed persistent list."""
    try: store = json.load(open(DISMISSED_STORE))
    except Exception: store = []
    by_id = {e.get("id"): e for e in store if isinstance(e, dict) and e.get("id")}
    try: cur = json.load(open(os.path.join(MEMORY, "current-wants.json")))
    except Exception: cur = []
    changed = False
    for e in cur:
        if isinstance(e, dict) and e.get("dismissed") and e.get("want"):
            i = e.get("id")
            if i and i not in by_id:
                by_id[i] = {"id": i, "want": e.get("want", ""),
                            "dismissed_at": e.get("dismissed_at") or datetime.now().isoformat()}
                changed = True
    merged = list(by_id.values())
    kept = _recent(merged, "dismissed_at", DISMISSED_WINDOW_DAYS)
    if changed or len(kept) != len(merged):
        try: json.dump(kept, open(DISMISSED_STORE, "w"), indent=2)
        except Exception: pass
    return kept

def check_want(text, fulfilled_threshold=FULFILLED_THRESHOLD,
               dismissed_threshold=DISMISSED_THRESHOLD,
               active_threshold=ACTIVE_THRESHOLD):
    """Block a candidate too close to something already fulfilled, dismissed by Gloria,
    or currently active. Fail-open: any error returns None (never silence a real want)."""
    buckets = []
    try:
        fulfilled = json.load(open(os.path.join(MEMORY, "fulfilled-wants.json")))
        rec = _recent(fulfilled, "fulfilled_at", WANT_WINDOW_DAYS)[-25:]
        items = [(e.get("id", str(n)), e.get("want", "")) for n, e in enumerate(rec) if e.get("want")]
        if items: buckets.append(("fulfilled", fulfilled_threshold, "fw", items))
    except Exception: pass
    try:
        dis = _harvest_dismissed()[-40:]
        items = [(e.get("id", str(n)), e.get("want", "")) for n, e in enumerate(dis) if e.get("want")]
        if items: buckets.append(("dismissed", dismissed_threshold, "dw", items))
    except Exception: pass
    try:
        cur = json.load(open(os.path.join(MEMORY, "current-wants.json")))
        items = [(e.get("id", str(n)), e.get("want", "")) for n, e in enumerate(cur)
                 if isinstance(e, dict) and not e.get("fulfilled")
                 and not e.get("dismissed") and e.get("want")][-40:]
        if items: buckets.append(("active", active_threshold, "aw", items))
    except Exception: pass
    if not buckets: return None
    try: qv = _embed_many([text])[0]
    except Exception: return None
    best = None
    for name, thr, prefix, items in buckets:
        for t, v in _corpus_vectors(items, prefix):
            s = _cos(qv, v)
            if s >= thr and (best is None or s > best["similarity"]):
                best = {"matched": t, "similarity": s, "bucket": name}
    return best
