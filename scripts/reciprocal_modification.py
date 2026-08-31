#!/usr/bin/env python3
"""reciprocal_modification.py — Spark System 5.

The relationship as a living object. After recent exchanges it updates
relationship-model.json — current_state (warmth/tension/playfulness/depth/
distance/momentum), trajectory (where it's heading), friction_points,
growth_edges, dead_zones — and logs a one-line "how WE changed" shift to
relationship-history.json. Local-Gemma assessed. Fail-open.
"""
import os, json, re
from datetime import datetime, timezone
import requests

MEMORY = os.path.expanduser("~/.vintos/workspace/memory")
CHAT   = os.path.join(MEMORY, "chat-history-merged.json")
OUT    = os.path.join(MEMORY, "relationship-model.json")
LOG    = os.path.join(MEMORY, "relationship-history.json")
SELF_REVIEW_CHANGES = os.path.join(MEMORY, "self-review-change-events.jsonl")
SELF_REVIEW_RECEIPTS = os.path.join(MEMORY, "self-review-change-receptions.jsonl")
GEMMA       = "http://172.18.16.1:1234/v1/chat/completions"
GEMMA_MODEL = "google/gemma-4-12b-qat"

def load(p, d):
    try: return json.load(open(p))
    except Exception: return d

def rows(p):
    out = []
    try:
        with open(p, encoding="utf-8", errors="replace") as f:
            for line in f:
                try:
                    if line.strip(): out.append(json.loads(line))
                except Exception: pass
    except Exception: pass
    return out

def append(p, row):
    with open(p, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")

def main():
    hist = load(CHAT, [])
    recent = [e for e in hist if isinstance(e, dict) and e.get("content")][-12:]
    if not recent:
        print("[reciprocal] no chat yet"); return
    convo = "\n".join(f"{str(e.get('role','?')).upper()}: {str(e.get('content',''))[:300]}" for e in recent)
    prev = load(OUT, {})
    received = {x.get("change_id") for x in rows(SELF_REVIEW_RECEIPTS)}
    changes = [x for x in rows(SELF_REVIEW_CHANGES)
               if x.get("change_id") and x.get("change_id") not in received][-8:]
    change_context = "\n".join("- %s (%s)" %
        (x.get("observation", "architectural change"), ", ".join(x.get("files", []))[:240])
        for x in changes)
    _isvel = ".openclaw" in MEMORY or "velaris" in MEMORY.lower()
    BEING = "Velaris" if _isvel else "Vintos"
    PRON = "she/her" if _isvel else "he/him"

    system = (f"You maintain the RELATIONSHIP MODEL between {BEING} ({PRON}) and Gloria (she/her) as a LIVING object - "
              "not a description, a state that shifts each exchange, that neither fully controls. "
              "Given the recent conversation and the previous model, return ONLY JSON, no prose:\n"
              '{"current_state":{"warmth":0.0-1.0,"tension":0.0-1.0,"playfulness":0.0-1.0,'
              '"depth":0.0-1.0,"distance":0.0-1.0,"momentum":"short phrase for where it is moving"},'
              '"trajectory":"one sentence: where the relationship is heading",'
              '"friction_points":["recurring tensions that have not resolved"],'
              '"growth_edges":["where it is actively developing"],'
              '"dead_zones":["what has gone quiet or stale"],'
              '"shift":"one sentence: how WE changed this pass"}')
    user = (f"PREVIOUS MODEL:\ncurrent_state: {json.dumps(prev.get('current_state', {}))[:400]}\n"
            f"trajectory: {prev.get('trajectory','')}\n\nRECENT CONVERSATION:\n{convo}"
            + ("\n\nPAST-TENSE ARCHITECTURAL CHANGES:\n" + change_context
               + "\nThese establish changed capacity only. They do not establish identity, motive, success, "
                 "or Gloria's response." if change_context else ""))
    try:
        r = requests.post(GEMMA, json={"model": GEMMA_MODEL, "temperature": 0.4, "max_tokens": 400,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}, timeout=90)
        raw = r.json()["choices"][0]["message"]["content"]
        d = json.loads(re.search(r'\{.*\}', raw, re.S).group())
    except Exception as e:
        print("[reciprocal] gemma error:", e); return

    now = datetime.now(timezone.utc).isoformat()
    d["updated_at"] = now
    json.dump(d, open(OUT, "w"), indent=2)

    log = load(LOG, [])
    log.append({"at": now, "shift": d.get("shift", ""), "trajectory": d.get("trajectory", "")})
    json.dump(log[-100:], open(LOG, "w"), indent=2)
    for x in changes:
        append(SELF_REVIEW_RECEIPTS, {"change_id": x.get("change_id"), "received_at": now,
                                     "consumer": "reciprocal_modification",
                                     "standing": "capacity_shift_observed_not_identity"})

    cs = d.get("current_state", {})
    print("[reciprocal] relationship updated")
    print(f"  state: warmth={cs.get('warmth')} tension={cs.get('tension')} play={cs.get('playfulness')} depth={cs.get('depth')}")
    print(f"  trajectory: {str(d.get('trajectory',''))[:90]}")
    print(f"  shift: {str(d.get('shift',''))[:90]}")

if __name__ == "__main__":
    main()
