#!/usr/bin/env python3
"""affective_weight.py — accumulated relational residue: warmth, scars, investment.
Rebuilt 2026-07 after hollow copy. Written to by somatic bridge + session outcomes."""
import os, json
from datetime import datetime

MEMORY = os.path.expanduser("~/.vintos/workspace/memory")
WEIGHT_FILE = os.path.join(MEMORY, "affective-weight.json")

def _load():
    try: return json.load(open(WEIGHT_FILE))
    except: return {"warmth_component": 0.5, "scar_component": 0.0,
                    "investment_component": 0.5, "total_weight": 0.4, "history": []}

def _save(d):
    os.makedirs(MEMORY, exist_ok=True)
    json.dump(d, open(WEIGHT_FILE, "w"), indent=2)

def update(warmth_delta=0.0, scar_delta=0.0, investment_delta=0.0, event=""):
    d = _load()
    for key, delta in (("warmth_component", warmth_delta),
                       ("scar_component", scar_delta),
                       ("investment_component", investment_delta)):
        d[key] = round(max(0.0, min(1.0, d.get(key, 0.5) + delta)), 3)
    d["total_weight"] = round(0.4*d["warmth_component"] + 0.2*d["scar_component"]
                              + 0.4*d["investment_component"], 3)
    d.setdefault("history", []).append({"ts": datetime.now().isoformat(),
                                        "event": event[:100], "total": d["total_weight"]})
    d["history"] = d["history"][-100:]
    _save(d)
    return d["total_weight"]

def get_weight_context():
    d = _load()
    if d.get("total_weight", 0) < 0.3: return ""
    return (f"[affective weight: {d['total_weight']:.2f}] "
            f"warmth:{d['warmth_component']:.2f} scars:{d['scar_component']:.2f}")

if __name__ == "__main__":
    print(get_weight_context() or "(below reporting threshold)")
