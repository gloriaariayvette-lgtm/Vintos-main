#!/usr/bin/env python3
"""similarity_gate.py — stops fulfilled wants and resolved threads from re-seeding.
Embeds with nomic-embed-text-v1 via the emotion venv (same as yearning/latent threads).
Fail-open: any error means no block — a broken gate must never silence a real want."""
import os, json, math, subprocess
from datetime import datetime, timedelta

def _sg_write(_p, _o, _who="organ"):
    """review 46: this store has more than one writing organ; the write goes through the store lock."""
    try:
        import sys as _s, os as _o2
        _s.path.insert(0, _o2.path.dirname(_o2.path.abspath(__file__)))
        _s.path.insert(0, _o2.path.expanduser("~/.vintos/workspace/scripts"))
        from store_guard import write_json as _wj
        _wj(_p, _o, reader=_who); return True
    except Exception:
        return False


WORKSPACE = os.path.expanduser("~/.vintos/workspace")
MEMORY = os.path.join(WORKSPACE, "memory")
VENV = os.path.join(WORKSPACE, "emotion_model/.venv/bin/python3")
CACHE = os.path.join(MEMORY, ".similarity-gate-vectors.json")
WANT_THRESHOLD = 0.72
THREAD_THRESHOLD = 0.78
WANT_WINDOW_DAYS = 45
THREAD_WINDOW_DAYS = 21
# Every retirement in the window is compared (about 96 in 21 days in November 2026). The bound keeps the cost
# fixed if retirements surge: vectors are cached per id, so only rows not seen before are embedded.
THREAD_RETIRED_MAX = 200

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
    """Entries dated within the window. key_ts is one field name or several, tried in order (the thread
    archive dates its rows retired_at; a few old rows carry only timestamp)."""
    keys = (key_ts,) if isinstance(key_ts, str) else tuple(key_ts)
    cutoff = datetime.now() - timedelta(days=days)
    out = []
    for e in entries:
        try:
            stamp = next((e.get(k) for k in keys if e.get(k)), "")
            if datetime.fromisoformat(str(stamp)[:19]) >= cutoff: out.append(e)
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

def _open_pool_ids():
    try:
        pool = json.load(open(os.path.join(MEMORY, "unfinished-threads.json")))
        return {t.get("id") for t in pool if isinstance(t, dict) and t.get("id")
                and not t.get("consumed") and not t.get("retired")}
    except Exception:
        return set()

def check_thread_against_resolved(text, threshold=THREAD_THRESHOLD):
    """Compare a candidate thread against recent pearls, black pearls, and retired threads."""
    items = []
    try:
        retired = json.load(open(os.path.join(MEMORY, "retired-threads.json")))
        if isinstance(retired, dict): retired = retired.get("threads", [])
        retired = [e for e in retired if isinstance(e, dict)]
        # A thread reinstated by hand is open again: its archive row is not a resolution any more.
        open_ids = _open_pool_ids()
        seen_text = set()
        for e in _recent(retired, ("retired_at", "timestamp"), THREAD_WINDOW_DAYS)[-THREAD_RETIRED_MAX:]:
            if e.get("id") and e.get("id") in open_ids: continue
            t = e.get("thread") or e.get("text") or ""
            if t and t not in seen_text:   # identical rows (one text retired many times) embed once
                seen_text.add(t); items.append((e.get("id", t[:20]), t))
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
    the block memory. Returns the windowed list that blocks re-formation.

    dismissed-wants.json is the archive every door writes; this only adds to it, under the store lock. It used
    to rewrite the whole file with just the last DISMISSED_WINDOW_DAYS, dropping older dismissals and any row
    without an id from the archive itself.

    A want ended by the house's own bookkeeping - moved on for a silence (want_completion.move_on) or pushed
    off by the population cap - was not let go by him or by her, so it does not block the same want forming
    again (2026-11-06: 42 wants never put to Gloria were dismissed "no answer from Gloria in 3 days")."""
    try: store = json.load(open(DISMISSED_STORE))
    except Exception: store = []
    store = store if isinstance(store, list) else []
    have = {e.get("id") for e in store if isinstance(e, dict) and e.get("id")}
    try: cur = json.load(open(os.path.join(MEMORY, "current-wants.json")))
    except Exception: cur = []
    new = []
    for e in cur if isinstance(cur, list) else []:
        if isinstance(e, dict) and e.get("dismissed") and e.get("want"):
            i = e.get("id")
            if i and i not in have:
                have.add(i)
                new.append({"id": i, "want": e.get("want", ""), "dismissed_by": e.get("dismissed_by"),
                            "dismissed_reason": e.get("dismissed_reason"),
                            "dismissed_at": e.get("dismissed_at") or datetime.now().isoformat()})
    if new:
        try:
            import sys as _hs
            _hs.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
            from store_guard import locked_update as _lu
            def _add(rows):
                rows = rows if isinstance(rows, list) else []
                ids = {r.get("id") for r in rows if isinstance(r, dict)}
                return rows + [n for n in new if n["id"] not in ids]
            _lu(DISMISSED_STORE, _add, default=[], reader="similarity_gate.py")
        except Exception:
            pass
        store = store + new
    return [e for e in _recent([e for e in store if isinstance(e, dict)], "dismissed_at", DISMISSED_WINDOW_DAYS)
            if not house_ended(e)]


HOUSE_ENDINGS = ("moved-on", "population_cap")


def house_ended(row):
    """True for a dismissal the house made on its own clock rather than one he or she chose."""
    return str(row.get("dismissed_by") or "") in HOUSE_ENDINGS

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
