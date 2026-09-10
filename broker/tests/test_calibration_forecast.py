#!/usr/bin/env python3
"""Review items 184, 199, 200, 202, 205, 206, 207, 215, 218, 220, 227, 230 (2026-09-10). Scratch HOME."""
import os, sys, json, types, tempfile, importlib.util, time

HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
HOME = tempfile.mkdtemp(prefix="vintos-cal-"); os.environ["HOME"] = HOME
WS = os.path.join(HOME, ".vintos", "workspace"); MEM = os.path.join(WS, "memory"); os.makedirs(MEM, exist_ok=True); os.makedirs(os.path.join(WS, "scripts"), exist_ok=True)
R = []
def check(name, ok, detail=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + name + (("  ->  %s" % (detail,)) if (detail and not ok) else ""))
def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m
def src(rel): return open(os.path.join(REPO, rel), errors="replace").read()
for name in ("requests", "numpy"):
    try: __import__(name)
    except ImportError: sys.modules[name] = types.ModuleType(name)

print("\n--- 202 / 207: release by held-out calibration, against versioned criteria ---")
CAL = load("calibration", os.path.join(REPO, "scripts", "calibration.py")); CAL.MEMORY = MEM; CAL.AUDIT = os.path.join(MEM, "jepa-calibration.json"); CAL.RELEASES = os.path.join(MEM, "calibration-releases.jsonl")
v = CAL.verdict("gloria")
check("no audit is INSUFFICIENT, never released", v["state"] == "INSUFFICIENT" and CAL.allowed("gloria") is False and v["criteria_version"] == CAL.CRITERIA_VERSION)
good = {"n_joined": 90, "n_holdout": 31, "axis_lockstep_corr": 0.4,
        "g": {"monotonicity_conf_vs_err": -0.44, "CONTROL_dsim_vs_err": -0.10, "wrong_but_confident": []},
        "s": {"monotonicity_conf_vs_err": -0.40, "CONTROL_dsim_vs_err": -0.05, "wrong_but_confident": ["x"]}}
check("a head that beats its control on enough held-out rows is RELEASED", CAL.verdict("gloria", audit=good)["state"] == "RELEASED")
small = dict(good, n_holdout=12)
check("too few held-out rows is INSUFFICIENT, not a pass", CAL.verdict("gloria", audit=small)["state"] == "INSUFFICIENT")
tie = json.loads(json.dumps(good)); tie["g"]["CONTROL_dsim_vs_err"] = -0.44
check("a head that only matches its control is WITHHELD: variance, not usefulness", CAL.verdict("gloria", audit=tie)["state"] == "WITHHELD" and "control" in CAL.verdict("gloria", audit=tie)["why"])
lock = json.loads(json.dumps(good)); lock["axis_lockstep_corr"] = 0.99
check("two heads in lockstep are WITHHELD", CAL.verdict("gloria", audit=lock)["state"] == "WITHHELD" and "lockstep" in CAL.verdict("gloria", audit=lock)["why"])
wbc = json.loads(json.dumps(good)); wbc["g"]["wrong_but_confident"] = ["a", "b", "c"]
check("confident-and-wrong beyond the tolerance is WITHHELD", CAL.verdict("gloria", audit=wbc)["state"] == "WITHHELD")
rows = [{"iso": "2026-09-0%d" % i, "source": ("a" if i < 8 else "b")} for i in range(1, 10)]
h, why = CAL.holdout(rows, by="time"); hs, whys = CAL.holdout(rows, by="source")
check("time and source holdouts are real slices, named", len(h) == 3 and h[-1]["iso"] == "2026-09-09" and [r["source"] for r in hs] == ["b", "b"] and "held out every source but a" in whys, (why, whys))
check("the release record is appended with the criteria version", CAL.record_release("gloria", CAL.verdict("gloria", audit=good))["state"] == "RELEASED" and json.loads(open(CAL.RELEASES).read().splitlines()[-1])["criteria_version"] == CAL.CRITERIA_VERSION)
jp = src("scripts/jepa_predictor.py")
check("the forecast's steering gate is the calibration verdict, per head, with the numbers", '"steering_allowed": all(v.get("state") == "RELEASED" for v in _cal_v.values())' in jp and '"calibration": _cal_v' in jp)
check("the audit computes its verdict on the held-out slice and keeps the full sample beside it", '_cal.holdout(rows, by="time")' in src("scripts/jepa_calibration_audit.py") and '"full_sample"' in src("scripts/jepa_calibration_audit.py"))

print("\n--- 200 / 205 / 206: matched horizons, unknown/invalid, counted once ---")
GC = load("grading_contract", os.path.join(REPO, "scripts", "grading_contract.py")); GC.MEMORY = MEM; GC.GRADES = os.path.join(MEM, "prediction-grades.jsonl")
a = GC.record("self_state", "SP-1", "GRADED", horizon_s=600, elapsed_s=120)
b = GC.record("self_state", "SP-2", "GRADED", horizon_s=600, elapsed_s=5000)
check("inside the horizon is matched; far outside it is STALE, calibration only", a["matched"] is True and a["counts_as"] == "accuracy" and b["outcome"] == "STALE" and b["counts_as"] == "calibration_only" and "horizon" in b["interpretation"])
c = GC.record("self_state", "SP-1", "GRADED", horizon_s=600, elapsed_s=130)
check("a prediction already graded is refused, never counted twice", c.get("refused", "").startswith("prediction SP-1 is already graded"))
u = GC.record("relational", "RP-9", "UNKNOWN"); i = GC.record("relational", "RP-10", "INVALID")
check("unknown and invalid are recordable and count as nothing", u["counts_as"] == "nothing" and i["counts_as"] == "nothing" and u["matched"] is False)
check("self-prediction passes its horizon and elapsed", "horizon_s=_horizon, elapsed_s=_elapsed" in src("scripts/self-prediction.py"))

print("\n--- 199: every influence carries its counterfactual ---")
eo = src("bin/emotional_operators.py")
check("each operator and trajectory records quantity, amount, before, after and without_this", '"without_this": round(_before, 4)' in eo and eo.count('"without_this"') == 2 and '"influences": influences' in eo)

print("\n--- 220: a control's own effect is not his choice ---")
dd = src("bin/discourse-direction.py")
check("only a lived turn records a direction choice; a control's direction goes to control-effects", 'if current and source in ("turn", "chat", "voice", "avatar")' in dd and "control-effects.jsonl" in dd and "not recorded as his choice" in dd)

print("\n--- 227: the mode never governs whether he answers ---")
check("the mode block says relevance and obligation outrank it", "This mode never governs whether you answer" in src("scripts/emoclaw_mode.py"))

print("\n--- 230: a loop closes only on evidence ---")
CD = load("curiosity_debt", os.path.join(REPO, "scripts", "curiosity_debt.py"))
for a2 in dir(CD):
    v2 = getattr(CD, a2)
    if isinstance(v2, str) and a2.isupper() and ".vintos" in v2: setattr(CD, a2, os.path.join(MEM, os.path.basename(v2)))
CD.MEM = MEM
CD._save([{"id": "q1", "question": "why the fig", "pull": 0.6, "created": time.time() - 4000, "last_seen": time.time(), "surfaced": 0, "target": "gloria"}])
check("no evidence: nothing counted, the attempt recorded", CD.confirm_surfaced("q1") == [] and CD._load()[0]["surfaced"] == 0 and CD._load()[0]["unevidenced_confirms"])
check("with evidence: counted once, the evidence kept", CD.confirm_surfaced("q1", evidence="I asked her why the fig") == ["q1"] and CD._load()[0]["surfaced"] == 1 and CD._load()[0]["surfaced_evidence"][0]["evidence"].startswith("I asked"))

print("\n--- 215: the candidate lifecycle ---")
tv = types.ModuleType("taste_vector"); tv._c = []
tv.load_taste_vector = lambda: {"counted_occurrences": list(tv._c)}
def _upd(text, signal_weight=1.0, positive=True, occurrence_id=None, context=None):
    if occurrence_id not in tv._c: tv._c.append(occurrence_id)
tv.update_from_signal = _upd; sys.modules["taste_vector"] = tv
EN = load("enjoyment", os.path.join(REPO, "scripts", "enjoyment.py")); EN.MEMORY = MEM; EN.LEDGER = os.path.join(MEM, "enjoyment-ledger.jsonl")
EN.candidate("j1", "the fig joke", "humor", "proposed")
EN.candidate("j1", "the fig joke", "humor", "used", why="told it at dinner")
EN.candidate("j1", "the fig joke", "humor", "rated", rating=5)
EN.admit("j1", "the fig joke", "humor-practice", medium="humor", her_reception="landed", evidence={"kind": "rating", "score": 5})
h = EN.candidate_history("j1")
check("proposed -> used -> rated -> promoted, nothing overwritten", [r["state"] for r in h] == ["proposed", "used", "rated", "promoted"] and h[2]["rating"] == 5)
EN.candidate("j2", "the other joke", "humor", "dropped", why="she did not laugh and neither did I")
check("a revised rating is a new row and a drop carries its reason", EN.candidate("j1", "the fig joke", "humor", "rated", rating=3)["rating"] == 3 and len(EN.candidate_history("j1")) == 5 and EN.candidate_history("j2")[-1]["why"].startswith("she did not laugh"))
try: EN.candidate("j3", "x", "humor", "vanished"); check("an unknown candidate state is refused", False)
except ValueError: check("an unknown candidate state is refused", True)

print("\n--- 184 / 218: live pairs only; a residual is his model's error ---")
check("the forecast context drops imported turns and anything below the ledger floor", "no live context above the ledger floor" in src("scripts/jepa_predictor.py"))
check("a relational miss is labelled his model error, never her changing or him leading", 'result["label_scope"] = "his_model_error"' in src("scripts/relational_mismatch.py") and "her state changing, or him having led or changed her" in src("scripts/relational_mismatch.py"))
print("\n%d/%d" % (sum(R), len(R))); sys.exit(0 if all(R) else 1)
