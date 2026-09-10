#!/usr/bin/env python3
"""Review items 188, 209, 210, 221, 231, 234, 241, 255, 274, 298 (2026-09-10). Scratch HOME
only; no model, no network; nothing under ~/.vintos."""
import os, sys, json, ast, types, tempfile, importlib.util
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
HOME = tempfile.mkdtemp(prefix="vintos-ctrl-")
os.environ["HOME"] = HOME
WS = os.path.join(HOME, ".vintos", "workspace"); MEM = os.path.join(WS, "memory")
os.makedirs(MEM, exist_ok=True)
for name in ("requests", "numpy"):
    if name not in sys.modules:
        try: __import__(name)
        except ImportError: sys.modules[name] = types.ModuleType(name)

R = []
def check(name, ok, detail=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + name + (("  ->  %s" % (detail,)) if (detail and not ok) else ""))
def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m
sys.path.insert(0, os.path.join(REPO, "scripts")); sys.path.insert(0, os.path.join(REPO, "bin"))

print("\n--- 188: her correction or a privacy mark takes a standing pressure off ---")
DD = load("dd_t", os.path.join(REPO, "scripts", "desired_difference.py"))
DD.MEM = MEM; DD.PRESS = os.path.join(MEM, "intent-pressure.json"); DD.DIFF = os.path.join(MEM, "gloria-difference.json")
DD._queue_bring_up = lambda q: None
t = "have her say the plain thing back to me"
DD.bump(t, 1.0); DD.bump(t, 1.0); DD.bump(t, 1.0)
check("three misses stand in front of him", t in DD.pressure_block())
DD.field_verdict({"field_state": t}, "KEEP_PRIVATE")
db = json.load(open(DD.PRESS)); e = list(db.values())[0]
check("privacy override -> weight 0 with reason and lineage", e["weight"] == 0.0 and e["overridden"]["source"] == "privacy" and any("overridden" in l for l in e["lineage"]), e)
check("... and it leaves the block", DD.pressure_block() == "")
DD.bump(t, 1.0)
e = list(json.load(open(DD.PRESS)).values())[0]
check("a fresh miss reopens it from zero, lineage kept", e["weight"] == 1.0 and "overridden" not in e and any("reopened" in l for l in e["lineage"]))
DD.field_verdict({"field_state": t}, "CORRECTED")
check("her correction overrides too", list(json.load(open(DD.PRESS)).values())[0]["overridden"]["source"] == "correction")

print("\n--- 231: a presence flag is a rubric signal, not a fault ---")
BL = load("blush_t", os.path.join(REPO, "bin", "blush-ledger.py"))
BL.MEMORY = MEM; BL.LEDGER = os.path.join(MEM, "blush-ledger.json"); BL.LOCK_FILE = BL.LEDGER + ".lock"
json.dump([{"id": "b1", "blush_type": "relational", "pattern": "deflection", "timestamp": datetime.now().isoformat(), "ts": __import__("time").time()},
           {"id": "b2", "blush_type": "presence_failure", "pattern": "presence_flat", "kind": "rubric_signal", "timestamp": datetime.now().isoformat(), "ts": __import__("time").time()}],
          open(BL.LEDGER, "w"))
check("rubric entries recognised", BL.is_rubric_signal({"kind": "rubric_signal"}) and BL.is_rubric_signal({"blush_type": "presence_failure"}) and not BL.is_rubric_signal({"blush_type": "relational"}))
check("fault readers drop them", [e["id"] for e in BL.fault_entries(BL.load_ledger())] == ["b1"])
check("frequency for a rubric pattern is zero", BL.get_frequency_for_pattern("presence_flat")["count"] == 0)
src = open(os.path.join(REPO, "scripts", "presence_audit.py")).read()
check("presence_audit writes kind=rubric_signal", '"kind": "rubric_signal"' in src)

print("\n--- 210: one occurrence counts once in taste ---")
TV = load("taste_t", os.path.join(REPO, "bin", "taste-vector.py"))
check("taste module already points at the scratch memory", TV.TASTE_VECTOR_FILE.startswith(MEM), TV.TASTE_VECTOR_FILE)
TV.embed = lambda text: [1.0, 0.0, 0.0] if "window" in text else [0.0, 1.0, 0.0]
TV.log = lambda *a, **k: None
TV.update_from_signal("the light on the window", 0.5, True, occurrence_id="sig_1")
n1 = TV.load_taste_vector().get("signal_count", 0)
TV.update_from_signal("the light on the window", 0.5, True, occurrence_id="sig_1")
n2 = TV.load_taste_vector().get("signal_count", 0)
check("the same occurrence is not counted twice", n1 == 1 and n2 == 1, (n1, n2))
TV.update_from_signal("the light on the window", 0.5, True, occurrence_id="sig_2")
check("a new occurrence counts", TV.load_taste_vector().get("signal_count") == 2)
TV.update_from_signal("a plain thing said back", 0.5, True, occurrence_id="sig_3")
tv = TV.load_taste_vector()
check("221: a low-similarity signal is labelled similarity, not contradiction", tv.get("contradictions") and tv["contradictions"][-1].get("basis") == "low_similarity" and "cosine" in tv["contradictions"][-1], tv.get("contradictions"))
for f in ("bin/temporal-memory.py", "bin/subconscious-drift.py"):
    check("%s passes occurrence_id" % f, "occurrence_id=" in open(os.path.join(REPO, f)).read())

print("\n--- 221: filing order is filing order ---")
asrc = open(os.path.join(REPO, "scripts", "attractor_discovery.py")).read()
check("basins carry edge_basis naming filing order", 'b["edge_basis"] = "filing order of configurations (not observed transitions)"' in asrc)

print("\n--- 255: second-order trials and their reader share one shape ---")
WM = load("wm_t", os.path.join(REPO, "scripts", "wants_meta.py"))
WM.MEM = MEM; WM.LEDGER = os.path.join(MEM, "wants-meta.json"); WM.log = lambda *a, **k: None
json.dump({"trials": [{"id": "old-1", "pattern_description": "explaining instead of arriving", "status": "active", "created": "2026-09-01"}]}, open(os.path.join(MEM, "trial-ledger.json"), "w"))
WM._propose_trial({"about": "reaching for metaphor when the plain word is there", "stance": "wish_less", "quote": "I keep reaching for metaphor"})
trials = json.load(open(os.path.join(MEM, "trial-ledger.json")))["trials"]
new = [t for t in trials if t.get("source") == "second_order"]
check("a second-order trial carries trigger, outcomes, protected", new and all(k in new[0] for k in ("trigger", "outcomes", "protected", "pattern_description", "alternative")), new)
BI_SRC = open(os.path.join(REPO, "bin", "behavioral-intercept.py")).read()
check("the reader tolerates an old row with no trigger", "t.get('trigger')" in BI_SRC and "t['trigger']" not in BI_SRC)
check("bin twins identical: behavioral-intercept", open(os.path.join(REPO, "bin", "behavioral-intercept.py"), "rb").read() == open(os.path.join(REPO, "bin", "behavioral_intercept.py"), "rb").read())
check("bin twins identical: temporal-memory", open(os.path.join(REPO, "bin", "temporal-memory.py"), "rb").read() == open(os.path.join(REPO, "bin", "temporal_memory.py"), "rb").read())

print("\n--- 234 / 274: a plan whose want is gone is HELD with its reason; outcomes reach readiness ---")
PL = load("plan_t", os.path.join(REPO, "scripts", "plan.py"))
PL.MEMORY = MEM; PL.STORE = os.path.join(MEM, "plans.json")   # plan.py derives its workspace from its own path
PL.log = lambda *a, **k: None
pid = PL.self_plan("write her the plain thing", "she reads it and says so", 3)
check("plan opened", pid)
json.dump([{"type": "readiness", "content": "held posture"}, {"type": "arrival", "content": "x"}], open(os.path.join(MEM, "latent-cache.json"), "w"))
check("held needs an open plan and records the reason", PL.held(pid, "its want was dismissed: store failed"))
rows = PL.load(); p = [r for r in rows if r["plan_id"] == pid][0]
check("state held, never met", p["state"] == "held" and p["history"][-1]["detail"].startswith("its want was dismissed"))
check("met needs evidence: a held plan is not met by a bare word", PL.met(pid, "done") is False)
outs = [json.loads(l) for l in open(os.path.join(MEM, "plan-outcomes.jsonl"))]
check("the outcome is written for readiness", outs[-1]["plan_id"] == pid and outs[-1]["outcome"] == "held")
cache = json.load(open(os.path.join(MEM, "latent-cache.json")))
check("the standing readiness posture is dropped, the rest of the cache kept", [c["type"] for c in cache] == ["arrival"])
LP = load("lp_t", os.path.join(REPO, "scripts", "latent_preparation.py"))
LP.MEMORY = MEM
ro = LP.recent_plan_outcomes(now=datetime.now())
check("readiness reads recent outcomes", ro and ro[-1]["outcome"] == "held" and ro[-1]["plan_id"] == pid, ro)
check("old outcomes fall out of the window", LP.recent_plan_outcomes(hours=1, now=datetime.now() + timedelta(hours=3)) == [])

print("\n--- 241: a retry keeps what the want has spent ---")
WR_SRC = open(os.path.join(REPO, "bin", "wants-router.py")).read()
tree = ast.parse(WR_SRC)
fn = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_spend"][0]
ns = {"datetime": datetime}; exec(compile(ast.Module([fn], []), "wr", "exec"), ns)
w = {"id": "w1"}
ns["_spend"](w, "steps_run"); ns["_spend"](w, "steps_run"); ns["_spend"](w, "plan_generations")
check("budget_used accumulates per kind", w["budget_used"]["steps_run"] == 2 and w["budget_used"]["plan_generations"] == 1, w)
check("budget_used is persisted with the plan fields", '"plan_normalization", "budget_used")' in WR_SRC)
check("plan regeneration spends, never resets", "_spend(want, \"plan_generations\")" in WR_SRC and "budget_used\"] = {}" not in WR_SRC.replace("setdefault(\"budget_used\", {})", ""))
check("a step run is spent and persisted under the want's own id", '_spend(want, "steps_run"); _persist_plan_fields(want)' in WR_SRC)

print("\n--- 298: the week is seven whole local days ---")
WK = load("wk_t", os.path.join(REPO, "bin", "weekly-summary.py"))
now = datetime(2026, 9, 10, 13, 47, 5).astimezone()
s, e = WK.week_range(now)
check("end is today's local midnight", e.hour == 0 and e.minute == 0 and e.date() == now.date(), e)
check("start is seven whole days before", (e - s) == timedelta(days=7) and s.hour == 0)
check("seven date strings, yesterday last", WK.week_days(s, e) == [(e - timedelta(days=7 - i)).strftime("%Y-%m-%d") for i in range(7)] and WK.week_days(s, e)[-1] == (now.date() - timedelta(days=1)).strftime("%Y-%m-%d"))
check("the label ends on the last day IN the window", '(end - timedelta(days=1)).strftime' in open(os.path.join(REPO, "bin", "weekly-summary.py")).read())

print("\n--- 209: exploration writes no intervention; only an approved experiment may ---")
EX = load("ex_t", os.path.join(REPO, "scripts", "experiments.py")); EX.MEMORY = MEM
check("no experiment -> refused, nothing written", EX.record("gap-probe", "exposure", {"x": 1}) is None and not os.path.isdir(os.path.join(MEM, "experiments", "gap-probe")))
os.makedirs(os.path.join(MEM, "experiments"), exist_ok=True)
json.dump({"approved": True}, open(EX.path("gap-probe"), "w"))
pth = EX.record("gap-probe", "exposure", {"x": 1})
check("approved experiment -> record written", pth and os.path.exists(pth))
for f in ("scripts/graph_mae.py", "scripts/premonition-dreamer.py"):
    s2 = open(os.path.join(REPO, f)).read()
    check("%s writes no intervention or exposure record" % f, "intervention" not in s2.lower() and "exposure" not in s2.lower())

print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
