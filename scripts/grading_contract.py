#!/usr/bin/env python3
"""grading_contract.py - one record shape for every graded prediction, and one registry of who
produces which distribution.

Review item 208 (2026-09-10). Three graders wrote three shapes to three files (self-prediction's
mismatches, relational-mismatch's warmth/tension/valence, lead-trials' LED/PARTIAL/NO), and nothing
said which producer owned which target, so a second producer for the same target could appear
unnoticed. The targets stay distinct - a self-state forecast, a relational forecast and a lead plan
are different predictions - but every grade now also lands here in one shape, and the registry is
checked: one producer per target.

    record(target, prediction_id, outcome, predicted=None, actual=None, interpretation="", provenance=None, detail=None)
    registry() / check_registry()
    python3 grading_contract.py            the registry and the last grades
"""
import os, sys, json, time

WS = os.path.expanduser("~/.vintos/workspace")
MEMORY = os.path.join(WS, "memory")
GRADES = os.path.join(MEMORY, "prediction-grades.jsonl")
OUTCOMES = ("GRADED", "HELD", "SKIP", "STALE", "ERROR")

# target -> the one producer (what writes the forecast), the one grader (what scores it), the store
PRODUCERS = {
    "self_state":  {"producer": "scripts/self-prediction.py predict", "grader": "scripts/self-prediction.py compare_prediction", "store": "memory/.self-prediction.json (prediction_ledger kind self)", "dims": "11 emotion dims"},
    "relational":  {"producer": "scripts/relational_mismatch.py predict", "grader": "scripts/relational_mismatch.py compare_prediction", "store": "memory/.relational-prediction.json (prediction_ledger kind relational)", "dims": "warmth, tension, valence"},
    "lead":        {"producer": "scripts/lead_trials.py open_trial", "grader": "scripts/lead_trials.py grade", "store": "memory/.lead-open-trial.json", "dims": "LED / PARTIAL / NO"},
    "gloria":      {"producer": "scripts/gloria_prediction.py", "grader": "scripts/living_trajectory.py (grades each prediction id once)", "store": "memory/gloria-prediction.json + history", "dims": "her trajectory"},
    "jepa":        {"producer": "scripts/jepa_predictor.py predict", "grader": "none: steering off until calibration is shown", "store": "memory/jepa-forecasts", "dims": "latent"},
}


def registry():
    return {k: dict(v) for k, v in PRODUCERS.items()}


def check_registry():
    """One producer per target, one grader per target, no producer serving two targets."""
    seen = {}
    problems = []
    for t, r in PRODUCERS.items():
        p = r["producer"].split()[0]
        if p in seen and seen[p] != t:
            problems.append("producer %s serves %s and %s" % (p, seen[p], t))
        seen[p] = t
        if not r.get("grader"):
            problems.append("target %s has no grader named" % t)
    return problems


def record(target, prediction_id, outcome, predicted=None, actual=None, interpretation="", provenance=None, detail=None, at=None):
    if target not in PRODUCERS:
        raise ValueError("unregistered prediction target %r: add it to grading_contract.PRODUCERS first" % target)
    if outcome not in OUTCOMES:
        raise ValueError("outcome %r not in %s" % (outcome, OUTCOMES))
    row = {"grade_id": "G-" + __import__("uuid").uuid4().hex[:8], "target": target, "prediction_id": prediction_id,
           "producer": PRODUCERS[target]["producer"], "outcome": outcome, "at": at or time.strftime("%Y-%m-%dT%H:%M:%S"),
           "predicted": predicted, "actual": actual, "interpretation": interpretation or "", "provenance": provenance,
           "detail": detail or {}}
    try:
        os.makedirs(MEMORY, exist_ok=True)
        with open(GRADES, "a") as f:
            f.write(json.dumps(row, default=str) + "\n")
    except OSError:
        pass
    return row


def grades(target=None, limit=50):
    out = []
    try:
        for ln in open(GRADES):
            try:
                r = json.loads(ln)
            except Exception:
                continue
            if target is None or r.get("target") == target:
                out.append(r)
    except Exception:
        pass
    return out[-limit:]


if __name__ == "__main__":
    print("registry:")
    for t, r in PRODUCERS.items():
        print("  %-11s producer %-45s grader %s" % (t, r["producer"], r["grader"]))
    print("problems:", check_registry() or "none")
    for g in grades(limit=8):
        print("  %s %-11s %-6s %s %s" % (g["at"][:16], g["target"], g["outcome"], g.get("prediction_id"), g.get("interpretation")))
