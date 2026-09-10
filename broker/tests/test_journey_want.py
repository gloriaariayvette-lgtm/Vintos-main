#!/usr/bin/env python3
"""Review item 379 (2026-09-10), journey: a want -> a checkpoint pauses it -> he restarts it -> the
artifact lands with its manifest and the gallery stamps the want id -> explicit completion, proven by
the file, not the sentence. Real modules (want_checkpoints, artifact_manifest, want_artifact_guard,
emoclaw_utils.fulfill_want); scratch HOME; no model, no network."""
import os, sys, json, types, tempfile, importlib.util, time

HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
HOME = tempfile.mkdtemp(prefix="vintos-jw-"); os.environ["HOME"] = HOME
WS = os.path.join(HOME, ".vintos", "workspace"); MEM = os.path.join(WS, "memory")
os.makedirs(os.path.join(MEM, "art"), exist_ok=True); os.makedirs(os.path.join(WS, "scripts"), exist_ok=True)
R = []
def check(name, ok, detail=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + name + (("  ->  %s" % (detail,)) if (detail and not ok) else ""))
def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m
for name in ("requests", "numpy"):
    try: __import__(name)
    except ImportError: sys.modules[name] = types.ModuleType(name)
sys.path.insert(0, os.path.join(REPO, "scripts"))
CP = load("want_checkpoints", os.path.join(REPO, "scripts", "want_checkpoints.py")); CP.MEM = MEM; CP.STORE = os.path.join(MEM, "pursuit-checkpoints.json"); CP.WANTS = os.path.join(MEM, "current-wants.json")
AM = load("artifact_manifest", os.path.join(REPO, "scripts", "artifact_manifest.py"))
AG = load("want_artifact_guard", os.path.join(REPO, "scripts", "want_artifact_guard.py")); AG.MEMORY = MEM
AG.LEDGERS = [os.path.join(MEM, "art", "gallery.json")]; AG.GALLERY = AG.LEDGERS[0]; AG.ART_DIRS = [os.path.join(MEM, "art")]
# the guard fulfill_want imports by path under ~/.vintos/workspace/scripts
import shutil; shutil.copy(os.path.join(REPO, "scripts", "want_artifact_guard.py"), os.path.join(WS, "scripts", "want_artifact_guard.py"))

print("\n--- the want ---")
want = {"id": "W-379", "want": "generate an image of the fig at the table, muscadines beside it", "capability": "make_art", "multistep": True,
        "steps": [{"capability": "introspect", "status": "pending"}, {"capability": "make_art", "status": "pending"}], "current_step_index": 0,
        "fulfilled": False, "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"), "intensity": 4}
json.dump([want], open(CP.WANTS, "w"), indent=2)
check("it is artifact-class: a file must prove it", AG.is_artifact_want(want))

print("\n--- pause / restart through a checkpoint ---")
cid = CP.create(want["want"], "make_art", "blocked", "renderer offline")
check("a blocked step opens one pending checkpoint", cid and CP.pending_for(want["want"])["id"] == cid)
c = CP.decide("pause", "not tonight; the renderer is down")
w = json.load(open(CP.WANTS))[0]
check("pause: the pursuit is PAUSED with a horizon and his words on the record", c["decision"] == "pause" and w["pursuit"]["state"] == "PAUSED" and w["pursuit"]["paused_until"] > time.time() and "renderer" in c["his_words"], w.get("pursuit"))
CP.create(want["want"], "make_art", "blocked", "renderer back; resume?")
c2 = CP.decide("continue", "now")
w = json.load(open(CP.WANTS))[0]
check("restart: continue puts the pursuit back to RUNNING; the want itself never changed", c2["decision"] == "continue" and w["pursuit"]["state"] == "RUNNING" and w["want"] == want["want"] and not w["fulfilled"])

print("\n--- completion claimed before the file exists is refused ---")
src = open(os.path.join(REPO, "scripts", "emoclaw_utils.py")).read()
import ast as _ast
_tree = _ast.parse(src); _fn = next(n for n in _tree.body if isinstance(n, _ast.FunctionDef) and n.name == "fulfill_want")
ns = {"nudge_emotions": lambda *a, **k: None, "print": print}; exec(_ast.get_source_segment(src, _fn), ns)
fulfill_want = ns["fulfill_want"]
import subprocess as _sp; _sp.Popen = lambda *a, **k: None   # the ambitions-log launch is not this journey's
fulfill_want(want["want"], note="painted it", fulfilled_by="make_art", want_id="W-379")
w = json.load(open(CP.WANTS))[0]
check("no file -> not fulfilled; the unverified attempt is recorded with its reason", not w.get("fulfilled") and w.get("artifact_unverified", {}).get("why", "").startswith("artifact claimed"), w.get("artifact_unverified"))

print("\n--- the artifact lands with a manifest and the gallery stamps the want id ---")
path = os.path.join(MEM, "art", "fig-at-the-table.png")
open(path, "wb").write(b"\x89PNG\r\n\x1a\n" + b"\x00" * 64)
man = AM.build(path, "image", source_want="W-379", revision=1, shelf="gallery")
check("the manifest names the file, its hash, medium and source want", man.get("sha256") and man.get("medium") == "image" and man.get("source_want") == "W-379" and not AM.problems(man), (man, AM.problems(man)))
json.dump([{"file": os.path.basename(path), "want_id": "W-379", "manifest": man}], open(AG.GALLERY, "w"))
ok, why = AG.verify({**w, "fulfilled_at": time.strftime("%Y-%m-%dT%H:%M:%S")})
check("the guard now finds the artifact by want id in the gallery ledger", ok and "ledger:W-379" in why, why)

print("\n--- explicit completion ---")
fulfill_want(want["want"], note="painted it: fig-at-the-table.png", fulfilled_by="make_art", want_id="W-379")
arch = json.load(open(os.path.join(MEM, "fulfilled-wants.json"))) if os.path.exists(os.path.join(MEM, "fulfilled-wants.json")) else []
w = next((a for a in arch if a.get("id") == "W-379"), {})
check("fulfilled, by make_art, with the note naming the file", w.get("fulfilled") is True and w.get("fulfilled_by") == "make_art" and "fig-at-the-table" in w.get("fulfillment_note", ""), w)
check("the live list no longer carries it (moved, not marked)", json.load(open(CP.WANTS)) == [])
check("the archived want still carries its pause/restart pursuit and the earlier unverified attempt", w.get("pursuit", {}).get("state") == "RUNNING" and w.get("artifact_unverified"), w)
cps = json.load(open(CP.STORE))
check("the two checkpoints stay on the record, decided, in order", [c["decision"] for c in cps] == ["pause", "continue"])
print("\n%d/%d" % (sum(R), len(R))); sys.exit(0 if all(R) else 1)
