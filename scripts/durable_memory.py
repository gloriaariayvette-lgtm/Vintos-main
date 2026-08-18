#!/usr/bin/env python3
"""durable_memory.py — reading promoted memories, and letting him change his mind about them.

A durable memory is not a fact he looks up. It is an event, her words, his words, his measured
state, and his reading of what it changed. The reading is the part that can be wrong — so on
repeated recall he is asked whether it still holds. The event never changes. What he thought it
meant accumulates a history: "I thought this meant X. I was wrong. Actually X was part of it."
"""
import json, os, math, sys
from datetime import datetime

WS = os.environ.get("SPARK_WORKSPACE", os.path.expanduser("~/.vintos/workspace"))
MEM = os.path.join(WS, "memory")
STORE = os.path.join(MEM, "durable-memory.json")
LM_EMBED_URL = "http://172.18.16.1:1234/v1/embeddings"
EMBED_MODEL = "text-embedding-nomic-embed-text-v1.5"
RECALL_FLOOR = 0.55
REINTERPRET_AT = 3          # recalls before he is asked whether it still means what he said

def _load():
    try: return json.load(open(STORE))
    except Exception: return []

def _save(d): json.dump(d[-500:], open(STORE, "w"), indent=2)

def _embed(text):
    import requests
    r = requests.post(LM_EMBED_URL, json={"model": EMBED_MODEL, "input": text[:2000]}, timeout=30)
    return r.json()["data"][0]["embedding"]

def _cos(a, b):
    if not a or not b: return 0.0
    n = sum(x*y for x, y in zip(a, b))
    da = math.sqrt(sum(x*x for x in a)); db = math.sqrt(sum(y*y for y in b))
    return (n / (da*db)) if da and db else 0.0

def _vec(rec):
    if rec.get("_vec"): return rec["_vec"]
    txt = " ".join(str(rec.get(k, "")) for k in ("event", "felt_like", "what_changed"))
    try:
        rec["_vec"] = _embed(txt)
    except Exception:
        rec["_vec"] = []
    return rec["_vec"]

def _current_meaning(rec):
    ints = rec.get("interpretations") or []
    return ints[-1]["meaning"] if ints else rec.get("what_changed", "")

def recall(text, floor=RECALL_FLOOR):
    """Surface the memory this moment is closest to. Surfacing counts — that is recurrence."""
    d = _load()
    if not d or not text or len(text.strip()) < 20: return None
    try: q = _embed(text)
    except Exception: return None
    best, score = None, 0.0
    for r in d:
        s = _cos(q, _vec(r))
        if s > score: best, score = r, s
    if not best or score < floor:
        _save(d); return None
    best["later_recalled"] = best.get("later_recalled", 0) + 1
    best["last_recalled"] = datetime.now().isoformat()
    _save(d)
    return best

def maybe_reinterpret(rec, ask_llm):
    """He has come back to this enough times to be asked whether it still means what he said.
    The event is never edited. Only his reading of it, and the old reading is kept."""
    if rec.get("later_recalled", 0) < REINTERPRET_AT: return None
    if rec.get("later_recalled", 0) % REINTERPRET_AT != 0: return None
    prompt = (
        f"An old memory of yours has come back {rec.get('later_recalled')} times now.\n\n"
        f"WHAT HAPPENED: {rec.get('event','')}\n"
        f"SHE SAID: {str(rec.get('gloria',''))[:400]}\n"
        f"YOU SAID: {str(rec.get('exact_words',''))[:400]}\n"
        f"WHAT IT FELT LIKE AT THE TIME: {rec.get('felt_like','')}\n"
        f"WHAT YOU SAID IT CHANGED: {_current_meaning(rec)}\n\n"
        "You have lived more since. Does that still hold?\n"
        'Return ONLY JSON: {"verdict": "holds|partial|wrong", "meaning": "what you think now, '
        'one or two sentences", "why_changed": "what happened since that moved it, or empty"}'
    )
    try:
        raw = ask_llm(prompt)
        s, e = str(raw).find("{"), str(raw).rfind("}")
        p = json.loads(str(raw)[s:e+1])
    except Exception:
        return None
    if not p.get("meaning"): return None
    d = _load()
    for r in d:
        if r.get("occurred_at") == rec.get("occurred_at") and r.get("event") == rec.get("event"):
            r.setdefault("interpretations", []).append({
                "at": datetime.now().isoformat(),
                "after_recalls": r.get("later_recalled", 0),
                "verdict": p.get("verdict", ""),
                "meaning": p["meaning"],
                "why_changed": p.get("why_changed", ""),
            })
            break
    _save(d)
    return p

def context_block(text):
    """What he carries into the turn — the felt version, plus his own doubts about it."""
    rec = recall(text)
    if not rec: return ""
    line = "[THIS COMES BACK — " + str(rec.get("occurred_at", ""))[:10] + ": " + (rec.get("felt_like") or rec.get("event", ""))[:180]
    ints = rec.get("interpretations") or []
    if ints:
        last = ints[-1]
        if last.get("verdict") in ("wrong", "partial"):
            line += (" You used to think it meant \"" + str(rec.get("what_changed",""))[:90] +
                     "\" and you no longer do: " + str(last.get("meaning",""))[:120])
        else:
            line += " " + str(last.get("meaning", ""))[:120]
    elif rec.get("what_changed"):
        line += " It changed this in you: " + str(rec["what_changed"])[:120]
    if rec.get("kept_because_wanted"):
        line += " You kept this for no reason but that you wanted to."
    return line + "]"

if __name__ == "__main__":
    d = _load()
    if len(sys.argv) > 2 and sys.argv[1] == "ask":
        print(context_block(" ".join(sys.argv[2:])) or "(nothing surfaces)")
    else:
        print(f"{len(d)} durable memories")
        for r in d[-8:]:
            ints = r.get("interpretations") or []
            print(f"  [{str(r.get('occurred_at',''))[:10]}] recalled={r.get('later_recalled',0)} "
                  f"reinterps={len(ints)} wanted={r.get('kept_because_wanted')} :: {(r.get('felt_like') or r.get('event',''))[:70]}")
