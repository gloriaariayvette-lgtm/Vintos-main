#!/usr/bin/env python3
"""causality_consumers.py routes as its comments say (B7). Module-level "disabled" stubs for seed_thread and
set_preoccupation were always replaced by main()'s import, so the preoccupation was set while the code claimed
it was off. The stubs are gone: setting the preoccupation is the documented, on path; seeding causality
threads stays off (a deliberate pass, Gloria 2026-07-14).

Scratch SPARK_WORKSPACE; emoclaw_utils and pearl_engine are recording stubs; every socket is refused."""
import importlib.util, json, os, shutil, socket, sys, tempfile, types
REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
HOME = tempfile.mkdtemp(prefix="vintos-cause-consumers-")
WS = os.path.join(HOME, ".vintos", "workspace"); MEM = os.path.join(WS, "memory")
os.makedirs(MEM, exist_ok=True)
os.environ["HOME"] = HOME; os.environ["SPARK_WORKSPACE"] = WS
def _no(self, *a, **k): raise OSError("this suite reaches nothing")
socket.socket.connect = _no
CALLS = {"seed": [], "preoc": [], "pearl": []}
sys.modules["emoclaw_utils"] = types.SimpleNamespace(
    seed_thread=lambda *a, **k: CALLS["seed"].append(a),
    set_preoccupation=lambda *a, **k: (CALLS["preoc"].append(a), True)[1])
sys.modules["pearl_engine"] = types.SimpleNamespace(add_candidate=lambda **k: (CALLS["pearl"].append(k), "p1")[1])

R = []
def check(name, ok, detail=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + name + ((" -> " + str(detail)[:400]) if detail and not ok else ""))

spec = importlib.util.spec_from_file_location("causality_consumers_t", os.path.join(REPO, "scripts", "causality_consumers.py"))
CC = importlib.util.module_from_spec(spec); spec.loader.exec_module(CC)
check("its stores are scratch", CC.MEMORY == MEM and CC.STATE.startswith(HOME) and CC.LEDGER.startswith(HOME))
check("no module-level stand-ins pretend to disable anything",
      not hasattr(CC, "seed_thread") and not hasattr(CC, "set_preoccupation"))

json.dump([{"time": "2026-11-06T22:00:00", "summary": "a shift", "shift": [{"dimension": "Tension", "direction": "up"}],
            "distribution": [{"cause": "emergence", "prob": 0.7}], "hypothesis": "h"},
           {"time": "2026-11-06T22:05:00", "summary": "explained", "confidence": "high",
            "distribution": [{"cause": "her message", "prob": 0.9}]}], open(CC.CAUSE, "w"))
CC.main()
check("the most unexplained shift becomes tonight's preoccupation (priority 4, causality-emergent)",
      len(CALLS["preoc"]) == 1 and CALLS["preoc"][0][1] == "causality-emergent" and CALLS["preoc"][0][2] == 4,
      CALLS["preoc"])
check("causality threads are still not seeded", CALLS["seed"] == [], CALLS["seed"])
check("the explained event sets nothing", len(CALLS["preoc"]) == 1)
CC.main()
check("a rerun does not set it again (idempotent)", len(CALLS["preoc"]) == 1, CALLS["preoc"])

shutil.rmtree(HOME, ignore_errors=True)
print(f"\n{sum(R)}/{len(R)} passed")
sys.exit(0 if all(R) else 1)
