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
check("every store has its writers named; twins collapse to one organ", len(rows) > 80 and "interaction-ledger.json" in by and all(r["writers"] for r in rows) and "dreamart.py" in by.get("gallery.json", {}).get("writers", []), by.get("gallery.json"))
check("shared stores are reported with a lock verdict per store", any(r["shared"] for r in rows) and all(isinstance(r["locked"], bool) for r in rows) and "current-wants.json" in [r["store"] for r in rows if r["shared"]])
check("docs/store-owners.md is the generated table and is current", open(os.path.join(REPO, "docs", "store-owners.md")).read() == SO.render())

print("\n--- 73: the voice block has the text keys ---")
sv = src("bin/server.py")
check("voice session block carries source, surface, turn_id, gloria, vintos beside its call fields", '"source": "voice-session", "surface": "voice", "turn_id": str(sess.get("started_at") or "")' in sv and '"gloria": (_full[0]["gloria"] if _full else "")[:500]' in sv)

# --- review 46 (2026-09-10): concurrency control on the shared stores ------------------------------
print("\n--- 46: every shared store's writers take one lock ---")
import importlib
_SO = importlib.import_module("store_owners") if "store_owners" in sys.modules else load("store_owners", os.path.join(REPO, "scripts", "store_owners.py"))
_rows = _SO.table(); _shared = [r for r in _rows if r["shared"]]; _un = [r for r in _shared if not r["locked"]]
check("more than twenty stores are shared, and at most one writer anywhere is still unlocked", len(_shared) >= 20 and len(_un) <= 1, [(r["store"], r["unlocked_writers"]) for r in _un])
check("the locked ones say how they are locked", all(r["how"] for r in _shared if r["locked"]))
_SG2 = load("sg2", os.path.join(REPO, "scripts", "store_guard.py")); _SG2.MEMORY = MEM; _SG2.LOG = os.path.join(MEM, "store-quarantine.jsonl")
_p2 = os.path.join(MEM, "shared.json"); json.dump({"n": 0}, open(_p2, "w"))
_SG2.locked_update(_p2, lambda cur: {"n": cur["n"] + 1}); _SG2.locked_update(_p2, lambda cur: {"n": cur["n"] + 1})
check("locked_update is read-modify-write under the lock", json.load(open(_p2)) == {"n": 2} and os.path.exists(_p2 + ".lock"))
check("a mutate that returns None writes nothing", _SG2.locked_update(_p2, lambda cur: None) == {"n": 2} and json.load(open(_p2)) == {"n": 2})
_SG2.write_json(_p2, {"n": 9}, reader="test")
check("write_json locks and replaces", json.load(open(_p2)) == {"n": 9})

print("\n--- recovered domain writers share the complete transaction ---")
import ast, asyncio, concurrent.futures
assert os.path.commonpath([MEM, HOME]) == HOME
source = src("bin/server_domains/humor_wants.py")
tree = ast.parse(source)
selected = []
for node in tree.body:
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in ("_atomic_json", "add_want_step"):
        node.decorator_list = []; selected.append(node)
    if isinstance(node, ast.AsyncFunctionDef):
        for block in ast.walk(node):
            if isinstance(block, ast.With) and any("transactions" in ast.unparse(i.context_expr) for i in block.items):
                assert not any(isinstance(x, ast.Await) for x in ast.walk(block)), node.name
namespace = dict(os=os, json=json, MEMORY=MEM, APP_SECRET="fixture", Request=object,
                 transactions=SG.transactions, write_json=SG.write_json, _want_event=lambda *a: None)
exec(compile(ast.Module(body=selected, type_ignores=[]), "domain-fixture", "exec"), namespace)
wants_path = os.path.join(MEM, "current-wants.json")
SG.write_json(wants_path, [{"id":"w", "steps":[]}])
class RequestFixture:
    headers = {"X-Vintos-Secret":"fixture"}
    async def json(self):
        # Reading a slow body must never hold a store lock.
        assert not getattr(SG._state, "held", set())
        await asyncio.sleep(.001)
        return {"capability":"read_memory"}
def append_step(_):
    return asyncio.run(namespace["add_want_step"]("w", RequestFixture()))
with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
    results = list(pool.map(append_step, range(40)))
check("concurrent API mutations retain all forty steps", all(x.get("success") for x in results) and len(json.load(open(wants_path))[0]["steps"]) == 40)
from unittest.mock import patch
with patch.object(SG, "transaction", side_effect=OSError("lock unavailable")):
    refused = append_step(None)
check("lock failure refuses mutation without fallback truncation", not refused["success"] and len(json.load(open(wants_path))[0]["steps"]) == 40)

# Long inference must not overwrite a newer snapshot or malformed evidence.
p3 = os.path.join(MEM, "derived.json")
SG.write_json(p3, {"window": 1})
expected = json.load(open(p3))
SG.write_json(p3, {"window": 2, "correction": True})
check("stale inference is refused without overwriting concurrent changes",
      not SG.compare_and_swap(p3, expected, {"window": 1, "prose": "obsolete"})
      and json.load(open(p3)) == {"window": 2, "correction": True})
check("current inference commits atomically", SG.compare_and_swap(
      p3, {"window": 2, "correction": True}, {"window": 2, "prose": "current"}))
open(p3, "w").write("{bad")
try:
    SG.compare_and_swap(p3, {}, {"overwritten": True}, default={})
    rejected = False
except ValueError:
    rejected = True
check("malformed store cannot be replaced by a derived default", rejected and open(p3).read() == "{bad")
# Exercise the real drift entrypoint with a provider fixture that changes the
# input during inference. Neither provider calls nor inherited-home writes occur.
DR = load("drift_fixture", os.path.join(REPO, "scripts", "drift_reason.py"))
DR.DRIFT = os.path.join(MEM, "drift.json")
assert os.path.commonpath([DR.DRIFT, HOME]) == HOME
DR.load_engine = lambda: types.SimpleNamespace()
SG.write_json(DR.DRIFT, {"to_self": "before", "drift": 1})
def reason_fixture(*args):
    assert not getattr(SG._state, "held", set())
    SG.write_json(DR.DRIFT, {"to_self": "after", "drift": 2})
    return '{"characterization":"obsolete"}', ""
DR.call_llm = reason_fixture
DR.main()
check("drift reasoning refuses obsolete geometry after provider returns",
      json.load(open(DR.DRIFT)) == {"to_self": "after", "drift": 2})
# Extract the real pure mutation door; the legacy CLI has top-level execution.
cal_tree = ast.parse(src("scripts/opposition_calibration.py"))
cal_ns = {"OUT": os.path.join(MEM, "opposition-calibration.json"), "locked_update": SG.locked_update}
assert os.path.commonpath([cal_ns["OUT"], HOME]) == HOME
exec(compile(ast.Module(body=[n for n in cal_tree.body if isinstance(n, ast.FunctionDef) and n.name == "save_calibration"], type_ignores=[]), "calibration-fixture", "exec"), cal_ns)
misuse = {"events": [{"trial_id": "t1"}], "cleared": ["t2"], "state": "warning"}
SG.write_json(cal_ns["OUT"], {"ledgers": {"facts": {"license_level": 2, "misuse": misuse}}, "misuse_scan_at": 123})
cal_ns["save_calibration"]({"ledgers": {"facts": {"license_level": 3, "misuse": {}}}})
latest = json.load(open(cal_ns["OUT"]))
check("calibration refresh preserves detector history and metadata",
      latest["ledgers"]["facts"]["misuse"] == misuse and latest["misuse_scan_at"] == 123)
cal_ns["save_calibration"]({"ledgers": {}})
latest = json.load(open(cal_ns["OUT"]))
check("removed terrain loses license without erasing misuse evidence",
      latest["ledgers"]["facts"]["license_level"] == 0 and latest["ledgers"]["facts"]["misuse"] == misuse)

AC = load("ambition_check_fixture", os.path.join(REPO, "bin", "ambition-check.py"))
AC.AMB = os.path.join(MEM, "ambitions.json")
assert os.path.commonpath([AC.AMB, HOME]) == HOME
AC.gather_evidence = lambda: "fixture evidence"
AC.grok_note = lambda *args: "fixture mark"
old_goal = {"goal": "fixture ambition", "progress": "active"}
SG.write_json(AC.AMB, {"goals": [old_goal]})
def completion_fixture(*args):
    assert not getattr(SG._state, "held", set())
    SG.write_json(AC.AMB, {"goals": [old_goal, {"goal": "new ambition"}]})
    return {"completed": True, "evidence": "fixture"}
AC.gemma_check = completion_fixture
AC.main()
check("ambition classifier preserves concurrent goal creation",
      len(json.load(open(AC.AMB))["goals"]) == 2
      and json.load(open(AC.AMB))["goals"][0]["progress"] == "active")
OM = load("opposition_misuse_fixture", os.path.join(REPO, "scripts", "opposition_misuse.py"))
OM.MEM = MEM; OM.OC = cal_ns["OUT"]
assert os.path.commonpath([OM.OC, HOME]) == HOME
SG.write_json(OM.OC, {"ledgers": {"facts": {"license_level": 2, "misuse": misuse}}})
SG.write_json(os.path.join(MEM, "claim-hold-trials.json"), {"trials": [
    {"id": "t2", "terrain": "facts", "outcome": {"verdict": "CORRECTED"}}]})
with patch.object(OM.requests, "post", side_effect=AssertionError("live provider forbidden")):
    OM.main()
check("cleared misuse trials are not sent to the provider again",
      json.load(open(OM.OC))["ledgers"]["facts"]["misuse"]["cleared"] == ["t2"])

print("\n%d/%d" % (sum(R), len(R))); sys.exit(0 if all(R) else 1)
