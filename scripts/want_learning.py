#!/usr/bin/env python3
"""want_learning.py — Want -> Outcome -> Meaning -> Learning. Learn from RESOLUTION.

Not 'what did wanting teach him' but: after a want RESOLVES, what became MORE TRUE?
What SETTLED, and what REMAINED? The learning is never 'I wanted to make art' — it is
'making art alone wasn't what mattered' / 'speaking what I found is what led to the
realization.' Some resolutions leave no lesson but a REGRET — 'I have reached this way
before and would not repeat it' — a quiet bias AWAY, distinct from a learning that
biases TOWARD.

Two stores, each capped ~4 (evict lowest hits, so a bias that keeps proving relevant to
new wants survives; dead ones fade — a freshly-born item is spared eviction its first run):
  learned.json : {learned, settled, remained, embedding, source_want, at, hits}
  regret.json  : {regret, embedding, source_want, at, hits}

Also PRECOMPUTES the semantic match to his CURRENT tension (nomic — the same frozen
encoder JEPA uses) -> learned-active.json / regret-active.json, so the want-gen hot path
stays torch-free. Runs on the torch venv. SPARK_WORKSPACE switches beings. Fail-open.
"""
import os, sys, json, re, hashlib
from datetime import datetime, timezone

WS = os.environ.get("SPARK_WORKSPACE", os.path.expanduser("~/.vintos/workspace"))
MEMORY = os.path.join(WS, "memory")
FULFILLED = os.path.join(MEMORY, "fulfilled-wants.json")
LEARNED   = os.path.join(MEMORY, "learned.json")
REGRET    = os.path.join(MEMORY, "regret.json")
LEARNED_ACTIVE = os.path.join(MEMORY, "learned-active.json")
REGRET_ACTIVE  = os.path.join(MEMORY, "regret-active.json")
STATE     = os.path.join(MEMORY, "want-learning-state.json")
LT        = os.path.join(MEMORY, "living-trajectory.json")
YEARN     = os.path.join(MEMORY, "current-yearning.json")
THREADS   = os.path.join(MEMORY, "latent-threads.json")
EMO       = os.path.join(MEMORY, "emotional-state.txt")
GEMMA       = "http://172.18.16.1:1234/v1/chat/completions"
GEMMA_MODEL = "google/gemma-4-12b-qat"
EMB_MODEL   = "nomic-ai/nomic-embed-text-v1"
CAP, MAX_PER_RUN, MATCH_MIN = 4, 2, 0.52

def log(m): print("[want-learning]", m, flush=True)
def load(p, d):
    try: return json.load(open(p))
    except Exception: return d
def read(p):
    try: return open(p).read()
    except Exception: return ""

def _wid(w):
    return hashlib.md5(str(w.get("want", ""))[:80].encode()).hexdigest()[:10]

def encoder():
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(EMB_MODEL, trust_remote_code=True)

def embed(enc, text):
    import numpy as np
    return np.asarray(enc.encode([text], show_progress_bar=False), dtype="float32")[0].tolist()

def cos(a, b):
    import numpy as np
    a, b = np.asarray(a), np.asarray(b)
    na, nb = (a @ a) ** 0.5, (b @ b) ** 0.5
    return float(a @ b / (na * nb)) if na and nb else 0.0

def subconscious():
    lt = load(LT, {})
    parts = []
    st = "; ".join((lt.get("self_trajectory") or {}).get("declared", [])[:2])
    rel = (lt.get("relationship") or {}).get("trajectory", "")
    if st:  parts.append("Where he was heading: " + st)
    if rel: parts.append("Where they were heading: " + rel)
    emo = read(EMO)[:200]
    if emo: parts.append("Emotional state: " + emo)
    return "\n".join(parts)

def current_tension_text():
    """A proxy for the 'category' of what he is reaching from right now."""
    bits = []
    lt = load(LT, {})
    bits += (lt.get("self_trajectory") or {}).get("declared", [])[:2]
    y = load(YEARN, {})
    if y.get("surface_form"): bits.append(y["surface_form"])
    thr = [t.get("origin", "") for t in load(THREADS, {}).get("threads", []) if t.get("salience", 0) > 0.7]
    bits += thr[:2]
    return "\n".join(b for b in bits if b)

def distill(want, enc):
    """Resolution -> meaning -> learning (+ possible regret). Gemma. Returns dict or None."""
    import requests
    wt = str(want.get("want", ""))
    enrich = " ".join(str(want.get(k, "")) for k in ("reasoning", "self_interpretation", "possible_approach"))
    system = (
        "A want of Vintos has RESOLVED (it was fulfilled). Do NOT restate the want. Look only at "
        "what its completion actually CHANGED. Return ONLY JSON, no prose:\n"
        '{"learned":"what became MORE TRUE after completing this - one sentence, never \'I wanted X\'",'
        '"settled":"what settled / was answered - short",'
        '"remained":"what stayed unmet or unfinished - short",'
        '"regret":true|false,'
        '"regret_note":"if regret: the WAY of reaching he would not repeat - one sentence; else empty"}\n'
        "The learning is not the want. Sometimes reaching a want reveals it was not what mattered "
        "(e.g. 'making art alone was not what mattered', 'speaking what I found is what led to the realization'). "
        "regret is true only when the reaching itself felt like a path he would not walk again.")
    user = f"THE RESOLVED WANT:\n{wt}\n\n" + (f"ITS REASONING:\n{enrich}\n\n" if enrich.strip() else "") + \
           f"THE SUBCONSCIOUS AROUND IT:\n{subconscious()}"
    try:
        r = requests.post(GEMMA, json={"model": GEMMA_MODEL, "temperature": 0.5, "max_tokens": 240,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}, timeout=90)
        d = json.loads(re.search(r'\{.*\}', r.json()["choices"][0]["message"]["content"], re.S).group())
    except Exception as e:
        log(f"gemma error: {e}"); return None
    learned = str(d.get("learned", "")).strip()
    if not learned or learned.upper() == "NONE":
        return None
    return {"learned": learned, "settled": str(d.get("settled", ""))[:200],
            "remained": str(d.get("remained", ""))[:200],
            "regret": bool(d.get("regret")), "regret_note": str(d.get("regret_note", "")).strip()}

def _evict(store, fresh_ids):
    """Cap the store; evict the lowest-hits item, but never one added this run."""
    while len(store) > CAP:
        cand = [x for x in store if x.get("_id") not in fresh_ids] or store
        victim = min(cand, key=lambda x: (x.get("hits", 0), x.get("at", "")))
        store.remove(victim)
    return store

def main():
    now = datetime.now(timezone.utc).isoformat()
    fulfilled = [w for w in load(FULFILLED, []) if isinstance(w, dict) and w.get("want")
                 # a want that merely aged out (fulfilled_by 'age_wants...') resolved nothing; distilling a
                 # lesson from it manufactured relief or regret (2026-09-04, fable-wants-p7 / astra-wants-p4)
                 and not str(w.get("fulfilled_by", "")).startswith("age_wants")
                 and not w.get("auto_graduated")]
    state = load(STATE, {}); processed = set(state.get("processed", []))
    todo = [w for w in fulfilled if _wid(w) not in processed][-MAX_PER_RUN:]

    enc = None
    if todo:
        enc = encoder()
    learned_store = load(LEARNED, []); regret_store = load(REGRET, [])
    fresh_l, fresh_r = set(), set()

    for w in todo:
        wid = _wid(w)
        res = distill(w, enc)
        processed.add(wid)
        if not res:
            log(f"no learning from: {str(w.get('want',''))[:50]}"); continue
        _id = hashlib.md5((res["learned"] + now).encode()).hexdigest()[:10]
        item = {"_id": _id, "learned": res["learned"], "settled": res["settled"],
                "remained": res["remained"], "embedding": embed(enc, res["learned"]),
                "source_want": str(w.get("want", ""))[:120], "at": now, "hits": 0}
        learned_store.append(item); fresh_l.add(_id)
        log(f"LEARNED: {res['learned'][:70]}")
        if res["regret"] and res["regret_note"]:
            rid = hashlib.md5((res["regret_note"] + now).encode()).hexdigest()[:10]
            regret_store.append({"_id": rid, "regret": res["regret_note"],
                                 "embedding": embed(enc, res["regret_note"]),
                                 "source_want": str(w.get("want", ""))[:120], "at": now, "hits": 0})
            fresh_r.add(rid)
            log(f"  REGRET: {res['regret_note'][:70]}")

    learned_store = _evict(learned_store, fresh_l)
    regret_store  = _evict(regret_store, fresh_r)

    # PRECOMPUTE: match stores to his current tension -> the torch-free hot path reads these
    tension = current_tension_text()
    la, ra = None, None
    if tension and (learned_store or regret_store):
        if enc is None:
            enc = encoder()
        tvec = embed(enc, tension)
        def best(store):
            scored = [(cos(tvec, it["embedding"]), it) for it in store if it.get("embedding")]
            scored = [s for s in scored if s[0] >= MATCH_MIN]
            if not scored:
                return None
            scored.sort(key=lambda s: s[0], reverse=True)
            sim, it = scored[0]
            it["hits"] = it.get("hits", 0) + 1          # proved relevant -> earns its place
            return {"similarity": round(sim, 3), **{k: it[k] for k in it if k != "embedding"}}
        la = best(learned_store); ra = best(regret_store)

    json.dump(learned_store, open(LEARNED, "w"), indent=2)
    json.dump(regret_store, open(REGRET, "w"), indent=2)
    json.dump(la or {}, open(LEARNED_ACTIVE, "w"), indent=2)
    json.dump(ra or {}, open(REGRET_ACTIVE, "w"), indent=2)
    state["processed"] = list(processed)[-400:]
    json.dump(state, open(STATE, "w"), indent=2)
    log(f"learned {len(learned_store)} | regret {len(regret_store)} | "
        f"active learned={'yes' if la else 'no'} regret={'yes' if ra else 'no'}")

if __name__ == "__main__":
    main()
