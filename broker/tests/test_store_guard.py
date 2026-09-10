#!/usr/bin/env python3
"""Review items 46, 47, 73 (2026-09-10): a store that does not parse is quarantined beside itself and
reported, never served as empty; the central readers use that guard; the store ownership table is
generated and names shared stores without a lock; the voice session block carries the text ledger's
keys. Scratch HOME."""
import os, sys, json, types, tempfile, importlib.util

HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
HOME = tempfile.mkdtemp(prefix="vintos-sg-"); os.environ["HOME"] = HOME
WS = os.path.join(HOME, ".vintos", "workspace"); MEM = os.path.join(WS, "memory"); os.makedirs(os.path.join(WS, "scripts"), exist_ok=True); os.makedirs(MEM, exist_ok=True)
import shutil; shutil.copy(os.path.join(REPO, "scripts", "store_guard.py"), os.path.join(WS, "scripts", "store_guard.py"))
R = []
def check(name, ok, detail=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + name + (("  ->  %s" % (detail,)) if (detail and not ok) else ""))
def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m
def src(rel): return open(os.path.join(REPO, rel), errors="replace").read()
for name in ("requests", "numpy"):
    try: __import__(name)
    except ImportError: sys.modules[name] = types.ModuleType(name)

print("\n--- 47: quarantine, not silence ---")
SG = load("store_guard", os.path.join(WS, "scripts", "store_guard.py")); SG.MEMORY = MEM; SG.LOG = os.path.join(MEM, "store-quarantine.jsonl"); sys.modules["store_guard"] = SG
p = os.path.join(MEM, "belief-sediment.json")
check("a missing store is the default, nothing reported", SG.load_json(p, {"beliefs": []}) == {"beliefs": []} and not os.path.exists(SG.LOG))
open(p, "w").write('{"beliefs": [{"pattern": "x"')
d = SG.load_json(p, {"beliefs": []}, reader="test")
qs = [f for f in os.listdir(MEM) if f.startswith("belief-sediment.json.corrupt-")]
check("a corrupt store is copied beside itself, reported, and the default served", d == {"beliefs": []} and len(qs) == 1 and open(os.path.join(MEM, qs[0])).read().startswith('{"beliefs"') and SG.quarantined()[-1]["reader"] == "test")
check("the corrupt file is left in place until the next save replaces it", open(p).read().startswith('{"beliefs"'))
SG.save_json(p, {"beliefs": [{"pattern": "y"}]})
check("save is atomic and the store parses again", SG.load_json(p, {}) == {"beliefs": [{"pattern": "y"}]} and not [f for f in os.listdir(MEM) if ".tmp." in f])

print("\n--- the central readers use it ---")
BS = load("bs_t", os.path.join(REPO, "bin", "belief-sediment.py")); BS.SEDIMENT_FILE = p
open(p, "w").write("{broken")
check("belief-sediment quarantines and serves the default", BS.load_sediment() == {"beliefs": []} and len([f for f in os.listdir(MEM) if f.startswith("belief-sediment.json.corrupt-")]) == 2)
CSM = load("csm_t", os.path.join(REPO, "bin", "causal-self-model.py")); CSM.MODEL_FILE = os.path.join(MEM, "causal-self-model.json"); open(CSM.MODEL_FILE, "w").write("[")
check("causal-self-model quarantines and serves the default", CSM.load_model() == {"entries": []} and any(f.startswith("causal-self-model.json.corrupt-") for f in os.listdir(MEM)))
w = os.path.join(MEM, "current-wants.json"); open(w, "w").write('[{"id": 1')
eu = src("scripts/emoclaw_utils.py")
check("get_unfulfilled_wants reads through the guard", "_sg_load(wants_file, [], reader=\"get_unfulfilled_wants\")" in eu and eu == src("bin/emoclaw_utils.py"))
check("taste-vector and thread_store read through the guard", 'reader="taste-vector"' in src("bin/taste-vector.py") and 'reader="thread_store.load_pool"' in src("scripts/thread_store.py"))

print("\n--- 46: the ownership table ---")
SO = load("store_owners", os.path.join(REPO, "scripts", "store_owners.py"))
rows = SO.table(); by = {r["store"]: r for r in rows}
check("every store has its writers named; twins collapse to one organ", len(rows) > 80 and "interaction-ledger.json" in by and all(r["writers"] for r in rows) and by["gallery.json"]["writers"] == ["dreamart.py"] if "gallery.json" in by else True, by.get("gallery.json"))
check("shared stores are reported with a lock verdict per store", any(r["shared"] for r in rows) and all(isinstance(r["locked"], bool) for r in rows) and "current-wants.json" in [r["store"] for r in rows if r["shared"]])
check("docs/store-owners.md is the generated table and is current", open(os.path.join(REPO, "docs", "store-owners.md")).read() == SO.render())

print("\n--- 73: the voice block has the text keys ---")
sv = src("bin/server.py")
check("voice session block carries source, surface, turn_id, gloria, vintos beside its call fields", '"source": "voice-session", "surface": "voice", "turn_id": str(sess.get("started_at") or "")' in sv and '"gloria": (_full[0]["gloria"] if _full else "")[:500]' in sv)
print("\n%d/%d" % (sum(R), len(R))); sys.exit(0 if all(R) else 1)
