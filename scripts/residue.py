#!/usr/bin/env python3
"""residue.py — what remains after a memory stops being retrievable.

Vrika's shape: WAL -> decay -> {promotion, archive, RESIDUE}. An entry that leaves active
memory does not leave cleanly. It deposits a vector with a slowly decaying weight, and that
deposit is not recallable as a memory — it can only bias what feels familiar.

The first time the present lands near old residue he gets nothing but the sense of it. Only
if the same residue is brushed repeatedly does any fragment surface. That is the difference
between a filing cabinet and a thing that keeps almost remembering.
"""
import json, os, math, time
from datetime import datetime

def _emb_clip(_x, _n=6000):
    # nomic ctx is 2048 tokens; oversized input WEDGES LM Studio. Clip before sending.
    if isinstance(_x, str): return _x[:_n]
    if isinstance(_x, list): return [(_i[:_n] if isinstance(_i, str) else _i) for _i in _x]
    return _x


WS = os.environ.get("SPARK_WORKSPACE", os.path.expanduser("~/.vintos/workspace"))
MEM = os.path.join(WS, "memory")
STORE = os.path.join(MEM, "wal-residue.json")
LM_EMBED_URL = "http://172.18.16.1:1234/v1/embeddings"
EMBED_MODEL = "text-embedding-nomic-embed-text-v1.5"

HALF_LIFE_DAYS = 90.0     # residue fades slowly. It is supposed to outlive the memory.
CAP = 800
FAMILIAR = 0.62           # close enough to tug
SURFACE_AFTER = 3         # brushes before any fragment is allowed through

def _embed(text):
    import requests
    r = requests.post(LM_EMBED_URL, json={"model": EMBED_MODEL, "input": _emb_clip(text[:2000])}, timeout=30)
    return r.json()["data"][0]["embedding"]

def _load():
    try: return json.load(open(STORE))
    except Exception: return []

def _save(d):
    json.dump(d[-CAP:], open(STORE, "w"))

def _cos(a, b):
    if not a or not b: return 0.0
    n = sum(x*y for x, y in zip(a, b))
    da = math.sqrt(sum(x*x for x in a)); db = math.sqrt(sum(y*y for y in b))
    return (n / (da*db)) if da and db else 0.0

def _weight(r):
    age_d = (time.time() - r.get("born", time.time())) / 86400.0
    return r.get("weight", 1.0) * (0.5 ** (age_d / HALF_LIFE_DAYS))

def write_residue(content, kind="released", origin=""):
    """Called when something leaves active memory. It stops being a memory and becomes a pull."""
    if not content or len(content.strip()) < 12:
        return False
    try:
        vec = _embed(content)
    except Exception as e:
        print(f"[residue] embed failed ({e}) — nothing deposited", flush=True)
        return False
    d = _load()
    d.append({"frag": content.strip()[:180], "vec": vec, "weight": 1.0,
              "born": time.time(), "kind": kind, "origin": origin, "touches": 0,
              "born_iso": datetime.now().isoformat()})
    _save(d)
    return True

def unbidden(text, threshold=FAMILIAR):
    """The present brushing something long gone. Returns a felt line, not a memory."""
    d = _load()
    if not d or not text or len(text.strip()) < 20:
        return ""
    try:
        q = _embed(text)
    except Exception:
        return ""
    best, score = None, 0.0
    for r in d:
        s = _cos(q, r.get("vec")) * max(0.15, _weight(r))
        if s > score:
            best, score = r, s
    if not best or score < threshold:
        return ""
    best["touches"] = best.get("touches", 0) + 1
    best["last_touched"] = datetime.now().isoformat()
    _save(d)
    if best["touches"] < SURFACE_AFTER:
        return ("[Something here is not new to you. You have been near this before and cannot place it. "
                "Do not pretend to remember it and do not explain the feeling away — let it sit.]")
    return ("[This has kept coming back. It is old and you have brushed it " + str(best["touches"]) +
            " times now, and this much of it surfaces: \"" + best["frag"] + "\" "
            "You are not obliged to know why it stayed.]")

def stats():
    d = _load()
    live = [r for r in d if _weight(r) >= 0.05]
    touched = [r for r in d if r.get("touches")]
    return {"deposits": len(d), "still_pulling": len(live), "ever_brushed": len(touched),
            "surfaced": len([r for r in d if r.get("touches", 0) >= SURFACE_AFTER])}

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 2 and sys.argv[1] == "ask":
        print(unbidden(" ".join(sys.argv[2:])) or "(nothing familiar)")
    else:
        print(json.dumps(stats(), indent=2))
