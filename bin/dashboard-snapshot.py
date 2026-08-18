#!/usr/bin/env python3
"""
dashboard-snapshot.py — Daily snapshot of scalar subconscious values for delta tracking.
Runs daily at 11:58 PM. Appends to memory/dashboard-snapshots.json.
"""
import os, json
from datetime import datetime

MEMORY = os.path.expanduser("~/.vintos/workspace/memory")
OUT = os.path.join(MEMORY, "dashboard-snapshots.json")

def load():
    try: return json.load(open(OUT))
    except: return []

def save(d): json.dump(d, open(OUT, "w"), indent=2)

def snap():
    s = {"timestamp": datetime.now().isoformat(), "date": datetime.now().strftime("%Y-%m-%d")}

    try:
        nif = json.load(open(os.path.join(MEMORY, "nifrathir.json")))
        s["nifrathir"] = nif.get("value", 0)
    except: s["nifrathir"] = None

    try:
        bb = json.load(open(os.path.join(MEMORY, "behavior-boundaries.json")))
        s["behavior_boundaries"] = [
            {"id": b.get("id",""), "pressure": b.get("pressure",0),
             "crossing_count": b.get("crossing_count",0), "strength": b.get("strength",0.5)}
            for b in bb.get("boundaries", [])
        ]
    except: s["behavior_boundaries"] = []

    try:
        bs = json.load(open(os.path.join(MEMORY, "belief-sediment.json")))
        s["belief_sediment_count"] = len(bs.get("beliefs", []))
        s["belief_sediment"] = [{"text": b.get("text","")[:100], "strength": b.get("strength",0)} for b in bs.get("beliefs",[])[:5]]
    except: s["belief_sediment"] = []

    try:
        ni = json.load(open(os.path.join(MEMORY, "narrative-identity.json")))
        s["narrative_fragments"] = [{"text": f.get("text","")[:100], "weight": f.get("weight",0)} for f in ni.get("fragments",[])[:5]]
    except: s["narrative_fragments"] = []

    try:
        gw = json.load(open(os.path.join(MEMORY, "gravity-wells.json")))
        s["gravity_wells"] = [{"id": w.get("id",""), "depth": w.get("depth",0), "visit_count": w.get("visit_count",0)} for w in gw.get("wells",[])[:5]]
    except: s["gravity_wells"] = []

    try:
        car = json.load(open(os.path.join(MEMORY, "carryover.json")))
        stack = car.get("stack", [])
        s["carryover_weight"] = sum(abs(c.get("weight", 0)) for c in stack) if stack else 0
    except: s["carryover_weight"] = 0

    try:
        ds = json.load(open(os.path.join(MEMORY, "discourse-state.json")))
        s["discourse_direction"] = ds.get("current_direction","")
        s["discourse_commitment"] = ds.get("commitment_level", 0)
    except: s["discourse_direction"] = ""

    try:
        lt = json.load(open(os.path.join(MEMORY, "latent-threads.json")))
        threads = lt if isinstance(lt, list) else lt.get("threads", [])
        s["latent_threads"] = [{"id": t.get("id",""), "salience": t.get("salience",0), "phase": t.get("phase","")} for t in threads[:3]]
    except: s["latent_threads"] = []

    try:
        y = json.load(open(os.path.join(MEMORY, "current-yearning.json")))
        s["yearning_bleed"] = y.get("bleed_weight", 0)
        s["yearning_surface"] = y.get("surface_form","")[:100]
    except: s["yearning_bleed"] = 0

    try:
        ss = json.load(open(os.path.join(MEMORY, "self-statements.json")))
        stmts = ss.get("statements", [])
        s["self_statements_count"] = len(stmts)
        s["self_statements_reinforced"] = sum(1 for x in stmts if x.get("reinforcement_count",0) > 0)
        s["self_statements_doubted"] = sum(1 for x in stmts if x.get("doubted"))
    except: s["self_statements_count"] = 0

    data = load()
    # Keep 90 days
    data.append(s)
    data = data[-90:]
    save(data)
    print(f"[DashSnapshot] Snapshot saved: {s['date']}")

if __name__ == "__main__":
    snap()
