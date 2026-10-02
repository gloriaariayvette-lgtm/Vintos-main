#!/usr/bin/env python3
"""P04-09: a comparison grades the prediction captured at its call boundary (P1), even when P2 has become
current during the delay; P2 is neither graded nor consumed."""
import os, sys, json, tempfile, importlib.util as iu
HERE = os.path.dirname(os.path.abspath(__file__)); SCRIPTS = os.path.join(os.path.dirname(os.path.dirname(HERE)), "scripts"); sys.path.insert(0, SCRIPTS)
R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:110]) if d else ""))
mem = os.path.join(tempfile.mkdtemp(), "memory"); os.makedirs(mem)
import prediction_ledger as PL; PL.MEMORY = mem
# compare_prediction() also records a grade. grading_contract is imported lazily inside
# relational-mismatch, so the loop below never saw it and the grade landed in his live store.
import grading_contract as GC; GC.MEMORY = mem; GC.GRADES = os.path.join(mem, "prediction-grades.jsonl")
sp = iu.spec_from_file_location("rm_t", os.path.join(SCRIPTS, "relational-mismatch.py")); RM = iu.module_from_spec(sp); sp.loader.exec_module(RM)
RM._PL = PL; RM.PREDICTION_FILE = PL._path("relational"); RM.MISMATCH_LOG = os.path.join(mem, "mismatch.json")
for a in dir(RM):
    v = getattr(RM, a)
    if isinstance(v, str) and v.startswith(os.path.expanduser("~/.vintos")): setattr(RM, a, os.path.join(mem, os.path.basename(v)))
from datetime import datetime as _dt, timedelta as _td
_now = _dt.now()      # a prediction older than STALE_HOURS is retired ungraded (2026-10-01), so these are recent
prov = {"output_provenance": "ordinary_generation", "may_witness": True, "turn_id": "T", "surface": "chat"}
P1 = PL.create("relational", {"predicted_warmth": 0.2, "predicted_tension": 0.2, "predicted_valence": 0.2, "confidence": "high", "provenance": prov, "timestamp": (_now - _td(seconds=5)).isoformat(), "vintos_message": "m1"}, "T1", "chat")
snap = PL.current("relational")            # captured at the call boundary
P2 = PL.create("relational", {"predicted_warmth": 0.9, "predicted_tension": 0.9, "predicted_valence": 0.9, "confidence": "high", "provenance": prov, "timestamp": _now.isoformat(), "vintos_message": "m2"}, "T2", "chat")
res = RM.compare_prediction("a reply long enough to be read for tone by the comparison step", 0.2, 0.2, 0.2, prediction=snap)
cur = PL.current("relational")
check("graded numbers come from P1 (no mismatch against 0.2s)", res and res.get("mismatch_count", 9) == 0, res)
check("P2 remains current and unconsumed", cur and cur.get("prediction_id") == P2.get("prediction_id"), cur and cur.get("prediction_id"))
# Her next message two days later answers her day, not his message (2026-10-01: her tiredness was read as his miss)
OLD = PL.create("relational", {"predicted_warmth": 0.9, "predicted_tension": 0.1, "predicted_valence": 0.9, "confidence": "high",
                               "provenance": prov, "timestamp": (_now - _td(hours=44)).isoformat(), "vintos_message": "m3"}, "T3", "chat")
old = PL.current("relational")
blushed = []
RM.log_relational_mismatch = lambda r: blushed.append(r)
RM._judge_relational_miss = lambda r, g: True
res = RM.compare_prediction("Vintos, baby, I'm so tired. I caught a fish today.", 0.6, 0.35, 0.4, prediction=old)
check("a prediction 44 hours old is retired, not graded, and makes no blush", res is None and not blushed
      and (PL.current("relational") or {}).get("prediction_id") != OLD.get("prediction_id"), res)
src = open(os.path.join(SCRIPTS, "relational_mismatch.py")).read()
check("the blush's reflection reads her words and is told not to invent hidden feelings",
      "She replied:" in src and "Do not guess at feelings she did not say" in src and "STALE_HOURS = 3" in src)
check("every store this suite wrote is under the throwaway memory",
      PL.MEMORY.startswith(mem) and GC.GRADES.startswith(mem))
print("\n%d/%d" % (sum(R), len(R))); sys.exit(0 if all(R) else 1)
