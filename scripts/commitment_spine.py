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

# ---------------------------------------------------------------- the one store (review 132)
# Two stores used to hold commitments with different fracture/promotion paths: this file
# (commitment-imprints.json: living/strained/fractured, friction, the Vrika gate) and a list inside
# causal-self-model.json (commitment_imprints: confidence, promote/fracture with no gate). Now this file
# is the only store. A promotion that did not pass the gate enters as a CANDIDATE, never living; a
# fracture from any path is the same fracture record; the old list is migrated once, lineage kept.

def imprints(statuses=None):
    """The commitments, optionally filtered by status ('living', 'strained', 'candidate', 'fractured')."""
    rows = _load().get("imprints", [])
    return [i for i in rows if statuses is None or i.get("status") in statuses] if isinstance(rows, list) else []

def held():
    """What he holds now: living or strained. Candidates and fractures are not identity."""
    return imprints(("living", "strained"))

def promote_candidate(pattern, confidence=0.6, source="behavioral-intercept", kind="tentative_inference", lineage=None):
    """A recurring pattern offered as a commitment WITHOUT the gate's evidence: recorded as a candidate.
    It becomes living only through can_promote/_write_imprint in the causal model (the one door).
    A repeat of the same pattern reinforces the candidate."""
    d = _load(); rows = d.setdefault("imprints", [])
    for imp in rows:
        if imp.get("pattern", "")[:80] == str(pattern)[:80] and imp.get("status") != "fractured":
            imp["reinforcement_count"] = imp.get("reinforcement_count", 1) + 1
            imp["confidence"] = min(0.95, float(imp.get("confidence", 0) or 0) + 0.05)
            imp.setdefault("reinforcements", []).append({"observed_at": datetime.now().isoformat(), "source": source})
            _save(d); return imp
    import uuid
    imp = {"id": "ci_" + uuid.uuid4().hex[:6], "pattern": str(pattern)[:300], "confidence": float(confidence),
           "status": "candidate", "source": source, "kind": kind, "formed": datetime.now().isoformat(),
           "reinforcement_count": 1, "reinforcements": [{"observed_at": datetime.now().isoformat(), "source": source}],
           "lineage": lineage or {"offered_by": source, "gate": "not passed: candidate until can_promote"},
           "friction": 0.0, "last_friction": None, "friction_events": [], "fracture": None}
    rows.append(imp); _save(d); return imp

def fracture(pattern, pressure=0.8, source="causal-self-model"):
    """One fracture path for every caller: status fractured, the fracture record kept, confidence down."""
    d = _load(); hit = None; best = 0.0
    for imp in d.get("imprints", []):
        if imp.get("status") == "fractured": continue
        a, b = str(imp.get("pattern", "")).lower(), str(pattern).lower()
        wa, wb = set(a.split()), set(b.split())
        score = 1.0 if a[:80] == b[:80] else (len(wa & wb) / float(len(wb)) if wb else 0.0)
        if score >= 0.6 and score > best:
            hit, best = imp, score
    if hit:
        imp = hit
        if True:
            imp["status"] = "fractured"
            imp["fracture"] = {"at": datetime.now().isoformat(), "pressure": float(pressure), "source": source,
                               "pre_fracture_confidence": imp.get("confidence")}
            imp["confidence"] = max(0.1, float(imp.get("confidence", 0) or 0) - 0.25)
        _save(d)
    return hit

def migrate_legacy(csm_path=None):
    """Move any commitment_imprints still inside causal-self-model.json into this store, once, as
    candidates (they never passed the gate) or fractured, with lineage naming where they came from."""
    csm_path = csm_path or os.path.join(MEMORY, "causal-self-model.json")
    try: csm = json.load(open(csm_path))
    except Exception: return 0
    legacy = csm.get("commitment_imprints") if isinstance(csm, dict) else None
    if not legacy: return 0
    d = _load(); rows = d.setdefault("imprints", []); have = {i.get("pattern", "")[:80] for i in rows}
    n = 0
    for imp in legacy:
        if not isinstance(imp, dict) or imp.get("pattern", "")[:80] in have: continue
        rows.append({"id": imp.get("id") or ("ci_" + __import__("uuid").uuid4().hex[:6]), "pattern": imp.get("pattern", "")[:300],
                     "confidence": imp.get("confidence", 0.5), "status": "fractured" if imp.get("fractured") else "candidate",
                     "source": imp.get("source", "legacy"), "kind": "tentative_inference", "formed": imp.get("formed"),
                     "reinforcement_count": imp.get("reinforcement_count", 1), "reinforcements": [],
                     "lineage": {"migrated_from": "causal-self-model.json commitment_imprints", "migrated_at": datetime.now().isoformat(), "gate": "not passed"},
                     "friction": 0.0, "last_friction": None, "friction_events": [],
                     "fracture": ({"at": imp.get("fracture_at"), "pressure": None, "source": "legacy", "pre_fracture_confidence": None} if imp.get("fractured") else None)})
        n += 1
    csm["commitment_imprints_migrated"] = {"at": datetime.now().isoformat(), "count": len(legacy)}
    csm["commitment_imprints"] = []
    _save(d)
    tmp = csm_path + ".tmp"; json.dump(csm, open(tmp, "w"), indent=2); os.replace(tmp, csm_path)
    return n

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
    elif len(sys.argv) > 1 and sys.argv[1] == "migrate": print("[Spine] migrated %d legacy commitment(s)" % migrate_legacy())
    else:
        d = _load()
        for i in d.get("imprints", []):
            print("%s %-9s f=%.2f %s" % (i["id"], i["status"], i.get("friction", 0), i["pattern"][:60]))
