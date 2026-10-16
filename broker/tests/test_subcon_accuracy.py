#!/usr/bin/env python3
"""The accuracy report reads his records and writes nothing; a placeholder confidence never counts as measured.

Scratch HOME and workspace; requests cannot reach anything."""
import json, os, sys, tempfile, types
from datetime import datetime, timedelta
HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="subcon-accuracy-"); os.environ["HOME"] = HOME
WS = os.path.join(HOME, ".vintos", "workspace"); os.environ["SPARK_WORKSPACE"] = WS
MEM = os.path.join(WS, "memory"); os.makedirs(MEM)
def no_network(*a, **k): raise AssertionError("a test must never reach the network or send")
sys.modules["requests"] = types.SimpleNamespace(get=no_network, post=no_network)
sys.path.insert(0, os.path.join(REPO, "scripts"))
import subcon_accuracy as A
R = []
def check(name, ok, detail=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + name + ((" -> " + str(detail)[:400]) if detail and not ok else ""))
check("the store is throwaway", A.MEM == MEM and MEM.startswith(HOME))

now = datetime.now()
iso = lambda d: (now - timedelta(days=d)).isoformat()
hist = [{"at": iso(3), "confidence": 0.8, "graded_previous": None}]
for i, g in enumerate((0.9, 0.0, 0.5, 0.1, 1.0, 0.0, 0.4, 0.8, 0.0, 0.2)):
    hist.append({"at": iso(2.9 - i * 0.1), "confidence": 0.5, "graded_previous": g, "grade_outcome": "graded"})
hist.append({"at": iso(1), "grade_outcome": "HELD", "graded_previous": None})
hist.append({"at": iso(90), "graded_previous": 1.0, "grade_outcome": "graded"})   # outside the window
json.dump(hist, open(os.path.join(MEM, "gloria-prediction-history.json"), "w"))
json.dump([{"timestamp": iso(1), "realized": "YES", "target": {"goal": "g", "success_criterion": "c"}},
           {"timestamp": iso(1), "realized": "NO", "target": {"goal": "g", "success_criterion": "c"}},
           {"timestamp": iso(1), "realized": "HELD", "target": {}},
           {"timestamp": iso(1), "realized": None, "target": {"field_state": "x"}}],
          open(os.path.join(MEM, "intent-ledger.json"), "w"))
json.dump({"n_joined": 40, "n_holdout": 13, "g": {"monotonicity_conf_vs_err": -0.4, "CONTROL_dsim_vs_err": -0.1,
           "bins_low_mid_high_err": [0.5, 0.4, 0.3]}, "s": {"unmeasured": "placeholder"}, "axis_lockstep_corr": None},
          open(os.path.join(MEM, "jepa-calibration.json"), "w"))
before = {f: open(os.path.join(MEM, f)).read() for f in os.listdir(MEM)}
cut = now - timedelta(days=30)
g = "\n".join(A.gloria_prediction(cut)); i = "\n".join(A.intent(cut)); j = "\n".join(A.jepa(cut))
check("graded predictions counted inside the window only", "graded: 10" in g and "held (tactical window): 1" in g, g)
check("hits and misses split by grade", "right 3 (30%)" in g and "missed 5 (50%)" in g, g)
check("intent verdicts tallied; unresolved shown, not dropped", "YES 1" in i and "UNRESOLVED 1" in i and "HELD 1" in i, i)
check("criterion-judged intents reported apart", "with a declared success criterion: 2 of 4" in i and "landed 50%" in i, i)
check("the self-judging caveat is printed", "his own model grading his own move" in i)
check("gloria head reads as useful only when it beats its control", "confidence means something" in j, j)
check("a placeholder self axis is reported unmeasured", "self    unmeasured" in j, j)
check("the report wrote nothing", before == {f: open(os.path.join(MEM, f)).read() for f in os.listdir(MEM)})

print("--- the readers of self confidence ---")
sys.modules["torch"] = types.ModuleType("torch")
src = open(os.path.join(REPO, "scripts", "emoclaw_utils.py")).read()
start = src.index("def _novelty_directive"); body = src[start:src.index("\ndef ", start + 10)]
ns = {}; exec(body, ns)
json.dump({"source": "jepa", "self": {"novelty": 0.9, "confidence": 0.5, "confidence_placeholder": True}},
          open(os.path.join(MEM, "jepa-prediction.json"), "w"))
json.dump({"self_trajectory": {"declared": ["toward making"]}}, open(os.path.join(MEM, "living-trajectory.json"), "w"))
d = ns["_novelty_directive"]()
check("a placeholder confidence never licenses commitment", "curiosity, not a conclusion" in d, d)
json.dump({"source": "jepa", "self": {"novelty": None, "confidence": None}}, open(os.path.join(MEM, "jepa-prediction.json"), "w"))
try:
    ns["_novelty_directive"](); ok = True
except Exception as e:
    ok = False
check("a null confidence or novelty does not crash the directive", ok)
check("the bin twin carries the same guard",
      open(os.path.join(REPO, "bin", "emoclaw_utils.py")).read() == src)
audit = open(os.path.join(REPO, "scripts", "jepa_calibration_audit.py")).read()
check("the calibration audit skips placeholder rows", "confidence_placeholder" in audit and '"unmeasured"' in audit)
pa = open(os.path.join(REPO, "scripts", "presence_audit.py")).read()
check("a held presence head clears the old forecast", "os.remove(FORECAST)" in pa)
srv = open(os.path.join(REPO, "bin", "server.py")).read()
check("the post-turn path names its door to discourse direction", 'turn_completed(gloria_text, source=surface.split("/")[0])' in srv)
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
