#!/usr/bin/env python3
"""dd_scene_quarantine.py — Vrika ruling 2026-08-11: scene-born HELD differences are quarantined from
priority competition. Not deleted, not converted to NO - flagged. Unjudgeable != failed != important.
Weekly sweep; idempotent; only touches HELD entries lacking a flag."""
import os, json, re, requests
MEM = os.path.expanduser("~/.vintos/workspace/memory")
P = os.path.join(MEM, "gloria-difference.json")
d = json.load(open(P))
dde = d if isinstance(d, list) else next(v for v in d.values() if isinstance(v, list))
GEMMA = "http://172.18.16.1:1234/v1/chat/completions"
n = 0
for e in dde:
    if not isinstance(e, dict) or str(e.get("verdict")) != "HELD" or "scene_quarantined" in e: continue
    try:
        r = requests.post(GEMMA, json={"model": "google/gemma-4-12b-qat", "temperature": 0.0, "max_tokens": 20,
            "messages": [{"role": "user", "content":
            "Was this transformation-target derived from inside an intimate/sexual scene (peaks, waves, "
            "unraveling, coming apart, touch, rhythm)? TARGET: " + str(e.get("intended", ""))[:250] +
            '\nONLY JSON: {"scene": true/false}'}]}, timeout=60)
        e["scene_quarantined"] = bool(json.loads(re.search(r"\{.*\}", r.json()["choices"][0]["message"]["content"], re.S).group()).get("scene"))
        if e["scene_quarantined"]: n += 1
    except Exception:
        pass
json.dump(d, open(P, "w"), indent=2)
print("[dd-quarantine] flagged %d scene-born HELDs (preserved, out of the pool)" % n)
