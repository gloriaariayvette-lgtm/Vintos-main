#!/usr/bin/env python3
"""commitment_spine.py — friction and fracture for earned identity.
deviation-check detected it; Spine decides what it meant (Vrika).
Friction: cheap, decays daily, current-state only. History: permanent.
Fracture: pressure > 0.85 across 3+ deviation events -> sealed, scar, inversion.
Discomfort, never prohibition. No phantom identity voice: no match, no line."""
import os, json
from datetime import datetime
MEMORY = os.path.expanduser("~/.vintos/workspace/memory")
IMPRINTS = os.path.join(MEMORY, "commitment-imprints.json")
MATCH_T = 0.55
FRACTURE_P = 0.85
FRACTURE_N = 3

def _load():
    try: return json.load(open(IMPRINTS))
    except Exception: return {"imprints": []}
def _save(d): json.dump(d, open(IMPRINTS, "w"), indent=1)

def evaluate_reply(reply_text, reply_vec, dev_score, embed_fn, cos_fn):
    """Called once from deviation-check. Returns (matches, felt_line or None)."""
    d = _load(); matches = []; line = None
    for imp in d.get("imprints", []):
        if imp.get("status") not in ("living", "strained"): continue
        try:
            sim = cos_fn(reply_vec, embed_fn(imp["pattern"][:300]))
        except Exception: continue
        if sim < MATCH_T or dev_score < 0.3: continue
        ev = {"at": datetime.now().isoformat(), "match": round(sim, 3),
              "pressure": round(dev_score, 3), "excerpt": (reply_text or "")[:200]}
        imp["friction"] = round(min(1.0, imp.get("friction", 0) + 0.15 + 0.2 * dev_score), 3)
        imp["last_friction"] = ev["at"]
        imp.setdefault("friction_events", []).append(ev)
        if imp["status"] == "living" and imp["friction"] >= 0.3: imp["status"] = "strained"
        matches.append({"id": imp["id"], "match": ev["match"], "friction": imp["friction"], "status": imp["status"]})
        recent_heavy = [e for e in imp["friction_events"] if e.get("pressure", 0) > FRACTURE_P]
        if len(recent_heavy) >= FRACTURE_N and not imp.get("fracture"):
            imp["status"] = "fractured"
            imp["fracture"] = {"at": ev["at"], "pressure": dev_score,
                               "deviations": imp["friction_events"][-FRACTURE_N:],
                               "pre_fracture_confidence": imp.get("confidence")}
            try:
                import sys; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
                from yearning_scars import create_scar_from_want
                create_scar_from_want("I committed to: %s - and it cracked" % imp["pattern"][:80], intensity=0.5)
            except Exception: pass
            try:
                from latent_threads import seed_thread
                seed_thread("Maybe the opposite of this is also true: %s" % imp["pattern"][:100], direction="pivot")
            except Exception: pass
            print("[Spine] FRACTURE (witnessed, sealed): %s" % imp["pattern"][:60])
        if line is None:
            line = "this move grinds against something you are"
    if matches: _save(d)
    return matches, line

def decay():
    d = _load(); ch = False
    for imp in d.get("imprints", []):
        if imp.get("friction", 0) > 0:
            imp["friction"] = round(imp["friction"] * 0.95, 3); ch = True
            if imp["status"] == "strained" and imp["friction"] < 0.15: imp["status"] = "living"
    if ch: _save(d)
    print("[Spine] decay pass: friction breathes out; history keeps everything")

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "decay": decay()
    else:
        d = _load()
        for i in d.get("imprints", []):
            print("%s %-9s f=%.2f %s" % (i["id"], i["status"], i.get("friction", 0), i["pattern"][:60]))
