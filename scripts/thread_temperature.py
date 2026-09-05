#!/usr/bin/env python3
"""thread_temperature.py — Aegis. Density-vs-displacement temperature/stability (Gemini's math, wired to
the REAL box). Stability = local latent density: mean cosine of a thread's embedding to its top-k nearest
neighbors in memory/embeddings.jsonl. Temperature = init (1-S) first pass, then stability-scaled
exponential decay each pass, plus additive impulses (embedding drift since last pass, dream/mirror kicks).
NO LLM. Import-safe: exposes run(apply, quiet); triage calls run(apply=True, quiet=True) each pass.
Run standalone:  python3 thread_temperature.py [apply]
"""
import os, sys, json, math, time, shutil, urllib.request
from collections import deque
from datetime import datetime

def _emb_clip(_x, _n=4000):
    # nomic ctx is 2048 tokens; oversized input WEDGES LM Studio. Clip before sending.
    if isinstance(_x, str): return _x[:_n]
    if isinstance(_x, list): return [(_i[:_n] if isinstance(_i, str) else _i) for _i in _x]
    return _x

HOME = os.path.expanduser("~")
MEM = os.path.join(HOME, ".vintos/workspace/memory")
THREADS = os.path.join(MEM, "unfinished-threads.json")
IDX = os.path.join(MEM, "embeddings.jsonl")
EMBED_URL = "http://172.18.16.1:1234/v1/embeddings"
EMBED_MODEL = "text-embedding-nomic-embed-text-v1.5"
K, DECAY, BETA, CAP = 5, 0.15, 0.5, 2500
try:
    import numpy as np; NP = True
except Exception:
    NP = False


def _norm(v):
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / n for x in v]


def _load_index():
    if not os.path.isfile(IDX):
        raise RuntimeError("embeddings.jsonl not found at " + IDX)
    rows, vk, tk = deque(maxlen=CAP), None, None
    with open(IDX, encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except Exception:
                continue
            if vk is None:
                vk = next((k for k in ("vector", "embedding", "values", "emb") if isinstance(r.get(k), list)), None)
                tk = next((k for k in ("text", "message_text", "content", "chunk", "summary", "key") if isinstance(r.get(k), str)), None)
                if vk is None:
                    continue
            v = r.get(vk)
            if isinstance(v, list):
                rows.append(v)
    index = [_norm(v) for v in rows]
    if not index:
        raise RuntimeError("no vectors parsed from embeddings.jsonl (key=%s)" % vk)
    return index, (np.array(index) if NP else None), vk, tk


def _embed(batch):
    body = json.dumps({"model": EMBED_MODEL, "input": _emb_clip(batch)}).encode()
    req = urllib.request.Request(EMBED_URL, data=body, headers={"Content-Type": "application/json"})
    r = json.loads(urllib.request.urlopen(req, timeout=180).read())
    return [d["embedding"] for d in r["data"]]


def _stability(tv_n, index, idxmat):
    if NP:
        sims = idxmat @ np.array(tv_n)
        sims = sims[sims < 0.99]
        if sims.size == 0:
            return 0.1
        return float(min(1.0, max(0.0, np.sort(sims)[::-1][:K].mean())))
    sims = sorted((sum(a * b for a, b in zip(row, tv_n)) for row in index), reverse=True)
    sims = [s for s in sims if s < 0.99][:K]
    return min(1.0, max(0.0, sum(sims) / len(sims))) if sims else 0.1


def run(apply=False, quiet=False):
    def out(*a):
        if not quiet:
            print(*a)
    index, idxmat, vk, tk = _load_index()
    out(f"index: {len(index)} vectors (dim {len(index[0])}), vector-key='{vk}', text-key='{tk}', numpy={NP}")
    obj = json.load(open(THREADS))
    tlist = obj if isinstance(obj, list) else obj.get("threads", [])
    active = [t for t in tlist if isinstance(t, dict) and not t.get("consumed")]
    if not active:
        out("no unconsumed threads."); return {"count": 0}
    embs = _embed([str(t.get("thread", ""))[:400] for t in active])
    now = datetime.now()
    results = []
    for t, e in zip(active, embs):
        tv_n = _norm(e)
        S = _stability(tv_n, index, idxmat)
        first = t.get("_temp_emb") is None
        if first:
            T, heat = 1.0 - S, 0.0
        else:
            ts = t.get("temp_updated_at") or t.get("triaged_at") or ""
            try:
                dd = max(0.01, (now - datetime.fromisoformat(ts)).total_seconds() / 86400.0)
            except Exception:
                dd = 1.0
            T = t.get("temperature", 1.0 - S) * math.exp(-DECAY * (1.0 + S) * dd)
            heat = 0.0
            pe = t.get("_temp_emb")
            if isinstance(pe, list):
                heat += BETA * (1.0 - sum(a * b for a, b in zip(tv_n, _norm(pe))))
            if (t.get("dream_passes", 0) or 0) > (t.get("_temp_dream_passes", 0) or 0):
                heat += 0.20
            if (t.get("mirror_passes", 0) or 0) > (t.get("_temp_mirror_passes", 0) or 0):
                heat += 0.30
        results.append((t, tv_n, round(min(1.0, max(0.0, T + heat)), 4), round(S, 4), first))

    Ss = [r[3] for r in results]; Ts = [r[2] for r in results]
    out(f"\ncomputed for {len(results)} threads | S {min(Ss):.3f}-{max(Ss):.3f}  T {min(Ts):.3f}-{max(Ts):.3f}"
        f" | {'INIT' if all(r[4] for r in results) else 'decay'} pass")
    if not quiet:
        show = sorted(results, key=lambda r: r[2], reverse=True)
        out("  hottest:")
        for t, _, T, S, _f in show[:5]:
            out(f"    T={T:.3f} S={S:.3f} pull={t.get('priority','-')}  [{t.get('source','?')}] {str(t.get('thread',''))[:50]}")
        out("  coolest:")
        for t, _, T, S, _f in show[-3:][::-1]:
            out(f"    T={T:.3f} S={S:.3f} pull={t.get('priority','-')}  [{t.get('source','?')}] {str(t.get('thread',''))[:50]}")

    if apply:
        shutil.copy2(THREADS, THREADS + ".bak-temp-" + time.strftime("%Y%m%d-%H%M%S"))
        stamp = now.isoformat()
        for t, tv_n, T, S, _f in results:
            t["stability"] = S
            t["temperature"] = T
            t["_temp_emb"] = tv_n
            t["temp_updated_at"] = stamp
            t["_temp_dream_passes"] = t.get("dream_passes", 0) or 0
            t["_temp_mirror_passes"] = t.get("mirror_passes", 0) or 0
        _n_before = 0
        try:
            _n_before = len(json.load(open(THREADS)))
        except Exception: pass
        _obj_n = len(obj) if isinstance(obj, list) else len(obj.get("threads", obj) if isinstance(obj, dict) else [])
        if _n_before > 5 and _obj_n < _n_before // 2:
            print("[thread-temp] REFUSING write: would shrink pool %d -> %d (wipe guard 2026-08-11)" % (_n_before, _obj_n))
        else:
            _tmp = THREADS + ".tmp"
            json.dump(obj, open(_tmp, "w"), indent=2, ensure_ascii=False)
            os.replace(_tmp, THREADS)
        out("  applied: stability + temperature written, backed up.")
    else:
        out("  dry run — pass apply to write.")
    return {"count": len(results), "S": (min(Ss), max(Ss)), "T": (min(Ts), max(Ts))}


if __name__ == "__main__":
    run(apply="apply" in sys.argv)
