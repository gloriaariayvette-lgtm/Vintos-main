#!/usr/bin/env python3
"""Review items 159, 222, 232, 328, 351, 368, 388, 389 (2026-09-10). Scratch HOME; no model; no network."""
import os, sys, json, types, tempfile, importlib.util, time, subprocess

HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
HOME = tempfile.mkdtemp(prefix="vintos-p911-"); os.environ["HOME"] = HOME
WS = os.path.join(HOME, ".vintos", "workspace"); MEM = os.path.join(WS, "memory"); os.makedirs(os.path.join(WS, "scripts"), exist_ok=True); os.makedirs(MEM, exist_ok=True)
os.environ["SPARK_WORKSPACE"] = WS
R = []
def check(name, ok, detail=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + name + (("  ->  %s" % (detail,)) if (detail and not ok) else ""))
def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m
def src(rel): return open(os.path.join(REPO, rel), errors="replace").read()
for name in ("requests", "numpy"):
    try: __import__(name)
    except ImportError: sys.modules[name] = types.ModuleType(name)

print("\n--- 222: evaluator failure is HELD ---")
ie = src("scripts/intent_engine.py")
check("_judge_realized returns HELD on a failed or off-vocabulary judgment, never NO", 'return "HELD"   # review 222' in ie and 'return "HELD"       # an answer outside' in ie)

print("\n--- 232: a step carries its receipt ---")
rs = src("bin/wants-router.py")
check("step history records receipt kind file/text/none with a ref", '"receipt": _rcpt' in rs and '_rcpt = {"capability": action, "kind": "file", "ref": _m.group(1)}' in rs)

print("\n--- 351: recheck before install ---")
B = load("srb", os.path.join(REPO, "scripts", "self_review_builder.py"))
for a in ("PROPOSALS", "DECISIONS", "BUILDS", "CHANGES", "BUILD_ROOT", "RUNTIME_MAP"): setattr(B, a, os.path.join(MEM, os.path.basename(getattr(B, a))))
B.WS = WS; B.MEM = MEM; B.SCRIPTS = os.path.join(WS, "scripts")
live = os.path.join(WS, "scripts", "wings.py"); open(live, "w").write("def fly():\n    return 'walk'\n")
PATCH = "--- a/scripts/wings.py\n+++ b/scripts/wings.py\n@@ -1,2 +1,2 @@\n def fly():\n-    return 'walk'\n+    return 'fly'\n"
B.append(B.PROPOSALS, {"proposal_id": "SRP-1", "implementation_files": ["scripts/wings.py"], "gloria_approval_required": False})
B.append(B.DECISIONS, {"proposal_id": "SRP-1", "decision_id": "SRD-1", "actor": "vintos", "action": "ADOPT", "reason": "x"})
def _ask_and_move(system, user, max_tokens=7000):
    open(live, "w").write("def fly():\n    return 'walk'  # edited under the build\n")   # the source moves after the stage is cut? no: before _ask, stage not cut yet
    return "```diff\n" + PATCH + "```"
_orig_stage = B._stage
def _stage_then_move(p, patch, files, build_dir):
    out = _orig_stage(p, patch, files, build_dir)
    open(live, "w").write("def fly():\n    return 'walk'  # moved under the build\n")
    return out
B._ask = lambda system, user, max_tokens=7000: "```diff\n" + PATCH + "```"; B._stage = _stage_then_move
try:
    B.build("SRP-1"); check("a live source that moved under the build refuses the install", False)
except PermissionError as e:
    check("a live source that moved under the build refuses the install", "changed since the stage was cut" in str(e), e)
check("the moved file was not overwritten", "moved under the build" in open(live).read())
B._stage = _orig_stage; open(live, "w").write("def fly():\n    return 'walk'\n")
B.append(B.DECISIONS, {"proposal_id": "SRP-1", "decision_id": "SRD-2", "actor": "vintos", "action": "ABANDON", "reason": "changed my mind"})
try:
    B.build("SRP-1"); check("a decision revoked since the build started refuses the install", False)
except PermissionError as e:
    check("a decision revoked since the build started refuses the install", "ABANDON" in str(e) or "internal proposal requires" in str(e) or "revoked" in str(e), e)

print("\n--- 368: read roots by real path ---")
rt = src("agent-room/room-tools.mjs")
check("containment resolves symlinks on both sides", "fs.realpathSync(r)" in rt and "r = fs.realpathSync(lex)" in rt)

print("\n--- 388: the untested report ---")
UR = load("untested_report", os.path.join(REPO, "scripts", "untested_report.py"))
rep = UR.report()
check("routes and modules are counted and the untested ones named", rep["routes_total"] > 100 and rep["modules_total"] > 100 and isinstance(rep["routes_untested"], list) and isinstance(rep["modules_untested"], list))
check("docs/untested.md is the generated report and current", open(os.path.join(REPO, "docs", "untested.md")).read() == UR.render())

print("\n--- 389: health in words that differ ---")
HV = load("health_view", os.path.join(REPO, "scripts", "health_view.py")); HV.MEMORY = MEM; HV.WS = WS
json.dump([], open(os.path.join(MEM, "current-wants.json"), "w"))
open(os.path.join(MEM, "belief-sediment.json"), "w").write("{broken")
json.dump({"nope": 1}, open(os.path.join(MEM, "causal-self-model.json"), "w"))
json.dump([{"timestamp": "t"}], open(os.path.join(MEM, "interaction-ledger.json"), "w")); old = time.time() - 100 * 3600; os.utime(os.path.join(MEM, "interaction-ledger.json"), (old, old))
v = HV.view()
st = {r["store"]: r["state"] for r in v["stores"]}
check("live / unavailable / malformed / unsupported / quiet are told apart", st["current-wants.json"] == "live" and st["taste-vector.json"] == "unavailable" and st["belief-sediment.json"] == "malformed" and st["causal-self-model.json"] == "unsupported" and st["interaction-ledger.json"] == "quiet", st)
check("the broker is asked, and answers in the same vocabulary", v["services"]["broker"]["broker"] in ("unavailable", "unknown", "up", "live", "degraded"), v["services"]["broker"])

print("\n--- 328: one inspection of an undertaking ---")
AL = load("atelier_ledger", os.path.join(REPO, "scripts", "atelier_ledger.py")); AL.MEMORY = MEM; AL.LEDGER = os.path.join(MEM, "atelier-undertakings.json")
AL.mark("p1", "active", by="atelier-threshold")
json.dump([{"revealed_at": "t", "medium": "image", "sha256": "abc", "bytes_verified": True, "artifact": "p1_image.png"}], open(os.path.join(MEM, "atelier-reveals.json"), "w"))
open(os.path.join(MEM, "atelier-reveal-refusals.jsonl"), "w").write(json.dumps({"at": "t", "artifact": "p1_image.png", "prepared": "abc", "on_disk": "def"}) + "\n")
ins = AL.inspect("p1", base="http://127.0.0.1:1", timeout=1)
check("house state, broker (unavailable), reveals, refusals and blockers in one view", ins["house"]["state"] == "active" and "unavailable" in ins["broker"] and ins["reveals"][0]["sha256"] == "abc" and len(ins["refusals"]) == 1 and ins["blockers"] == ["1 reveal(s) refused on digest mismatch"], ins)

print("\n--- 159: the raw-versus-derived page ---")
doc = open(os.path.join(REPO, "docs", "raw-vs-derived.md")).read()
check("the page names markers per surface with backwards compatibility", all(k in doc for k in ("gloria_raw", "is_dream", "embed_failed", "invalidated_by", "bytes_verified", "her_reception", "Backwards compatibility")))
print("\n%d/%d" % (sum(R), len(R))); sys.exit(0 if all(R) else 1)
