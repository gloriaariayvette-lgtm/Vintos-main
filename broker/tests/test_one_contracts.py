#!/usr/bin/env python3
"""Review items 208, 217, 225 (2026-09-10): one grade record and one producer registry across the
prediction targets (targets stay distinct); one door into taste that keeps his delight, her reception
and the craft apart and takes her reception only with evidence; one exchange join and one outcome
record for intent, lead and plan, with the experimental mechanisms that are off named. Scratch HOME."""
import os, sys, json, types, tempfile, importlib.util

HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
HOME = tempfile.mkdtemp(prefix="vintos-oc-"); os.environ["HOME"] = HOME
WS = os.path.join(HOME, ".vintos", "workspace"); MEM = os.path.join(WS, "memory"); os.makedirs(MEM, exist_ok=True)
R = []
def check(name, ok, detail=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + name + (("  ->  %s" % (detail,)) if (detail and not ok) else ""))
def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m
def src(rel): return open(os.path.join(REPO, rel), errors="replace").read()

print("\n--- 208: one grade record, one producer per target ---")
GC = load("grading_contract", os.path.join(REPO, "scripts", "grading_contract.py")); GC.MEMORY = MEM; GC.GRADES = os.path.join(MEM, "prediction-grades.jsonl")
check("the registry is clean: one producer and one grader per target", GC.check_registry() == [] and set(GC.registry()) >= {"self_state", "relational", "lead", "gloria", "jepa"})
GC.record("relational", "RP-1", "GRADED", predicted={"warmth": 0.7}, actual={"warmth": 0.4}, interpretation="miss x1")
GC.record("self_state", "SP-1", "HELD", interpretation="cannot witness itself")
GC.record("lead", "lt_1", "GRADED", predicted="take her to the garden", actual="the garden", interpretation="LED")
g = GC.grades()
check("three targets, one shape", [x["target"] for x in g] == ["relational", "self_state", "lead"] and all(set(x) >= {"grade_id", "target", "prediction_id", "producer", "outcome", "predicted", "actual", "interpretation"} for x in g))
try: GC.record("weather", "x", "GRADED"); check("an unregistered target is refused", False)
except ValueError: check("an unregistered target is refused", True)
try: GC.record("lead", "x", "MAYBE"); check("an outcome outside the contract is refused", False)
except ValueError: check("an outcome outside the contract is refused", True)
for rel in ("scripts/relational_mismatch.py", "scripts/relational-mismatch.py", "bin/relational_mismatch.py"):
    check("%s records HELD and GRADED through the contract" % rel, src(rel).count('_gc.record("relational"') == 2)
check("self-prediction records HELD and GRADED/STALE through the contract", src("scripts/self-prediction.py").count('_gc.record("self_state"') == 2 and '"STALE" if result.get("stale")' in src("scripts/self-prediction.py"))
check("lead_trials records through the contract", '_gc.record("lead"' in src("scripts/lead_trials.py"))

print("\n--- 225: one join, one outcome record, off switches named ---")
OJ = load("outcome_join", os.path.join(REPO, "scripts", "outcome_join.py")); OJ.MEMORY = MEM; OJ.LEDGER = os.path.join(MEM, "interaction-ledger.json"); OJ.JOINS = os.path.join(MEM, "outcome-joins.jsonl")
json.dump([{"timestamp": "t1", "turn_id": "T1", "gloria": "hi", "vintos": "hello"}, {"timestamp": "t2", "turn_id": "T2", "gloria": "come to the garden?", "vintos": "yes, now"}], open(OJ.LEDGER, "w"))
check("exchange by index, by turn id, and latest agree", OJ.exchange_at(index=1)["vintos"] == "yes, now" and OJ.exchange_at(turn_id="T1")["gloria"] == "hi" and OJ.latest_exchange()["turn_id"] == "T2")
check("what happened after an exchange is one call", [x["turn_id"] for x in OJ.after(0)] == ["T2"] and OJ.after(5) == [])
check("the dict-shaped ledger reads too", (json.dump({"entries": [{"timestamp": "t", "vintos": "v"}]}, open(OJ.LEDGER, "w")) or OJ.latest_exchange()["vintos"]) == "v")
OJ.record("intent", "reach first", "YES", {"axis": "single"}); OJ.record("plan", "P-1", "met"); OJ.record("lead", "lt_1", "LED")
check("three evaluators, one record", [x["kind"] for x in OJ.outcomes()] == ["intent", "plan", "lead"])
try: OJ.record("mood", "x", "y"); check("an unknown outcome kind is refused", False)
except ValueError: check("an unknown outcome kind is refused", True)
check("the off switches are named, BIS among them", "bis_trials" in OJ.EXPERIMENTAL and OJ.EXPERIMENTAL["bis_trials"].startswith("off"))
check("intent_engine finds his reply through the join and records both outcome shapes", "_oj.latest_exchange()" in src("scripts/intent_engine.py") and src("scripts/intent_engine.py").count('record("intent"') == 2)
check("lead_trials joins through outcome_join and records", "_oj.exchange_at(index=ot.get(\"ledger_len\", 0))" in src("scripts/lead_trials.py") and '_oj.record("lead"' in src("scripts/lead_trials.py"))
check("plan outcomes record too", '_oj.record("plan"' in src("scripts/plan.py"))

print("\n--- 217: one door into taste; enjoyment never one score ---")
moved = []
tv = types.ModuleType("taste_vector"); tv._counted = []
tv.load_taste_vector = lambda: {"counted_occurrences": list(tv._counted)}
def _upd(text, signal_weight=1.0, positive=True, occurrence_id=None):
    if occurrence_id in tv._counted: return
    tv._counted.append(occurrence_id); moved.append((text, signal_weight, positive))
tv.update_from_signal = _upd; sys.modules["taste_vector"] = tv
EN = load("enjoyment", os.path.join(REPO, "scripts", "enjoyment.py")); EN.MEMORY = MEM; EN.LEDGER = os.path.join(MEM, "enjoyment-ledger.jsonl")
r = EN.admit("joke:1", "the fig joke", "humor-practice", medium="humor", weight=0.15, his_delight="high", craft="tight", her_reception="landed", evidence={"kind": "rating", "score": 5})
check("a rated joke is admitted with the three parts apart and moves taste once", r["admitted"] and r["taste"] == "moved" and r["row"]["his_delight"] == "high" and r["row"]["her_reception"] == "landed" and r["row"]["craft"] == "tight")
r2 = EN.admit("joke:1", "the fig joke", "humor-practice", medium="humor", weight=0.15)
check("the same occurrence is already counted: no second move", r2["taste"] == "already counted" and len(moved) == 1)
r3 = EN.admit("art:7", "the muscadine painting", "gallery", medium="image", her_reception="loved it")
check("her reception without evidence is refused", r3["admitted"] is False and "reception evidence" in r3["why"])
r4 = EN.admit("drift:9", "quiet mornings", "subconscious-drift", medium="signal", weight=0.05, his_delight="settled")
check("his own delight needs no reception evidence", r4["admitted"] and r4["row"]["her_reception"] is None)
led = EN.ledger()
check("the ledger keeps every part per occurrence, per medium", len(led) == 3 and {x["medium"] for x in led} == {"humor", "signal"} and all("her_reception" in x and "his_delight" in x and "craft" in x for x in led))
for rel in ("scripts/subconscious_drift.py", "bin/subconscious_drift.py", "bin/temporal_memory.py", "scripts/humor_practice.py", "scripts/humor-practice.py", "bin/humor-practice.py"):
    check("%s enters taste through enjoyment.admit" % rel, "_enj.admit(" in src(rel) and "_tv_update(" not in src(rel).split("_enj.admit(")[1][:400])
check("humor passes her rating as reception evidence", 'evidence={"kind": "rating", "score": score' in src("scripts/humor_practice.py"))
print("\n%d/%d" % (sum(R), len(R))); sys.exit(0 if all(R) else 1)
