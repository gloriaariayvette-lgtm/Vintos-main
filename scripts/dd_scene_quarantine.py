#!/usr/bin/env python3
"""dd_scene_quarantine.py — Vrika ruling 2026-08-11: scene-born HELD differences are quarantined from
priority competition. Not deleted, not converted to NO - flagged. Unjudgeable != failed != important.
Weekly sweep; idempotent; only touches HELD entries lacking a flag."""
def _subcon_route(url, model):
    """The subconscious flag (subcon_target.py): AEON (the 26B was removed, Gloria 2026-11-08)."""
    try:
        import os as _o, sys as _s
        for _d in (_o.path.dirname(_o.path.abspath(__file__)), _o.path.expanduser("~/.vintos/workspace/scripts")):
            if _d not in _s.path:
                _s.path.append(_d)
        import subcon_target
        return subcon_target.generative_route(url, model)
    except Exception:
        return url, model


def _subcon_url(url):
    return _subcon_route(url, None)[0]


def _subcon_model(model):
    return _subcon_route(None, model)[1]


import os, json, re, requests
MEM = os.path.expanduser("~/.vintos/workspace/memory")
P = os.path.join(MEM, "gloria-difference.json")
d = json.load(open(P))
dde = d if isinstance(d, list) else next(v for v in d.values() if isinstance(v, list))
GEMMA = _subcon_url("http://100.79.177.103:1234/v1/chat/completions")
n = 0
for e in dde:
    if not isinstance(e, dict) or str(e.get("verdict")) != "HELD" or "scene_quarantined" in e: continue
    try:
        r = requests.post(GEMMA, json={"model": _subcon_model("aeon-gemma-4-12b"), "temperature": 0.0, "max_tokens": 20,
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
