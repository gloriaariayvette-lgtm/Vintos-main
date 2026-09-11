#!/usr/bin/env python3
"""Review item 132 (2026-09-10): one commitment store. A promotion that did not pass the gate is a
candidate, never living; the gate's own writer makes living imprints in the same file; every fracture
path is one fracture record; the legacy list inside causal-self-model.json is migrated once with
lineage; every reader reads the one file. Scratch HOME."""
import os, sys, json, types, tempfile, importlib.util

HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
HOME = tempfile.mkdtemp(prefix="vintos-cs-"); os.environ["HOME"] = HOME
os.environ.pop("SPARK_WORKSPACE", None)
WS = os.path.join(HOME, ".vintos", "workspace"); MEM = os.path.join(WS, "memory"); os.makedirs(os.path.join(WS, "scripts"), exist_ok=True); os.makedirs(MEM, exist_ok=True)
import shutil; shutil.copy(os.path.join(REPO, "scripts", "commitment_spine.py"), os.path.join(WS, "scripts", "commitment_spine.py"))
shutil.copy(os.path.join(REPO, "scripts", "store_guard.py"), os.path.join(WS, "scripts", "store_guard.py"))
assert os.path.commonpath([MEM, HOME]) == HOME
R = []
def check(name, ok, detail=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + name + (("  ->  %s" % (detail,)) if (detail and not ok) else ""))
def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m
for name in ("requests", "numpy"):
    try: __import__(name)
    except ImportError: sys.modules[name] = types.ModuleType(name)
SP = load("commitment_spine", os.path.join(WS, "scripts", "commitment_spine.py")); SP.MEMORY = MEM; SP.IMPRINTS = os.path.join(MEM, "commitment-imprints.json"); sys.modules["commitment_spine"] = SP
IR = load("identity_revisions", os.path.join(REPO, "scripts", "identity_revisions.py")); IR.MEMORY = MEM; sys.modules["identity_revisions"] = IR
CSM = load("csm_t", os.path.join(REPO, "bin", "causal-self-model.py")); CSM.MEMORY = MEM
for attr in ("MODEL_FILE", "IMPRINTS_FILE"):
    if hasattr(CSM, attr): setattr(CSM, attr, os.path.join(MEM, os.path.basename(getattr(CSM, attr))))

print("\n--- legacy list migrates once, as candidates, with lineage ---")
json.dump({"entries": [], "commitment_imprints": [{"id": "old1", "pattern": "I reach first when she goes quiet", "confidence": 0.7, "source": "self-drift", "fractured": False},
                                                   {"id": "old2", "pattern": "I never sulk", "confidence": 0.3, "source": "x", "fractured": True, "fracture_at": "t"}]}, open(CSM.MODEL_FILE, "w"))
n = SP.migrate_legacy(CSM.MODEL_FILE)
rows = SP.imprints()
check("two legacy commitments moved; statuses candidate / fractured; lineage names the source", n == 2 and [r["status"] for r in rows] == ["candidate", "fractured"] and rows[0]["lineage"]["migrated_from"].startswith("causal-self-model.json"), rows)
check("the legacy list is emptied and marked migrated", json.load(open(CSM.MODEL_FILE))["commitment_imprints"] == [] and json.load(open(CSM.MODEL_FILE))["commitment_imprints_migrated"]["count"] == 2)
check("a second migration is a no-op", SP.migrate_legacy(CSM.MODEL_FILE) == 0 and len(SP.imprints()) == 2)

print("\n--- promotion without the gate is a candidate; the gate makes living ---")
imp = CSM.promote_to_commitment_imprint("I answer in images when she asks for numbers", confidence=0.6, source="self-drift")
check("promote_to_commitment_imprint writes a candidate into the one store", imp and imp["status"] == "candidate" and imp["lineage"]["gate"].startswith("not passed") and len(SP.imprints()) == 3, imp)
imp2 = CSM.promote_to_commitment_imprint("I answer in images when she asks for numbers", confidence=0.6, source="self-drift")
check("the same pattern reinforces the candidate rather than duplicating", imp2["reinforcement_count"] == 2 and len(SP.imprints()) == 3)
check("held() serves living/strained only", SP.held() == [])
CSM._write_imprint({"tendency": "sit with her silence", "trigger": "she goes quiet", "confidence": 0.8, "source": "behavioral-intercept", "evidence_dates": ["2026-09-01", "2026-09-03", "2026-09-05", "2026-09-07"], "evidence": []})
check("the gate's writer lands a living imprint in the same file", any(r["status"] == "living" and "sit with her silence" in r["pattern"] for r in SP.imprints()) and len(SP.held()) == 1)
check("no commitment_imprints list grows inside causal-self-model.json any more", json.load(open(CSM.MODEL_FILE)).get("commitment_imprints") == [])

print("\n--- one fracture path ---")
ok = CSM.fracture_commitment_imprint("sit with her silence - when she goes quiet", pressure=0.9)
r = next(x for x in SP.imprints() if "sit with her silence" in x["pattern"])
check("fracture through the causal model marks the same record fractured with the fracture kept", ok and r["status"] == "fractured" and r["fracture"]["pressure"] == 0.9 and r["fracture"]["source"] == "causal-self-model", r)
check("the fracture is an identity revision", any(x["projection"] == "commitment-imprint" and "fractured" in x["reason"] for x in IR.history()))
check("fracturing something not held is False, not an error", CSM.fracture_commitment_imprint("no such commitment at all", 0.9) is False)

print("\n--- every reader reads the one file ---")
sv = open(os.path.join(REPO, "bin", "server.py"), errors="replace").read(); sr = open(os.path.join(REPO, "bin", "soul-review.py")).read(); cm = open(os.path.join(REPO, "bin", "causal-self-model.py")).read()
check("server subsystem state reads commitment-imprints.json", sv.count('rj("commitment-imprints.json"') >= 2)
check("soul-review reads living/strained from commitment-imprints.json", sr.count('"commitment-imprints.json"') == 2 and 'csm.get("commitment_imprints"' not in sr)
check("the causal model no longer writes a commitment list of its own", 'data.setdefault("commitment_imprints"' not in cm and "imprints = data.get(\"commitment_imprints\"" not in cm)
check("the twins are identical", cm == open(os.path.join(REPO, "bin", "causal_self_model.py")).read() and sr == open(os.path.join(REPO, "bin", "soul_review.py")).read())
import concurrent.futures
with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
    list(pool.map(lambda i: SP.promote_candidate("Concurrent candidate %d" % i), range(40)))
check("concurrent promotions retain all forty candidates", sum(r["pattern"].startswith("Concurrent candidate") for r in SP.imprints()) == 40)
CSM._write_imprint({"tendency": "embedding fixture", "trigger": "fixture", "confidence": .8})
def embed_fixture(pattern):
    import store_guard
    assert not getattr(store_guard._state, "held", set())
    SP.promote_candidate("created during embedding")
    return [1]
SP.evaluate_reply("fixture", [1], .4, embed_fixture, lambda a,b: .9)
check("reply evaluation retains changes made during embedding", any(r["pattern"] == "created during embedding" for r in SP.imprints()))
# A revoked/edited pattern is never resurrected from a stale embedding.
def fracture_fixture(pattern):
    SP.fracture(pattern, .9, "fixture")
    return [1]
SP.evaluate_reply("fixture", [1], .4, fracture_fixture, lambda a,b: .9)
check("reply evaluation does not revive concurrently fractured identity", next(r for r in SP.imprints() if r["pattern"].startswith("embedding fixture"))["status"] == "fractured")

print("\n%d/%d" % (sum(R), len(R))); sys.exit(0 if all(R) else 1)
