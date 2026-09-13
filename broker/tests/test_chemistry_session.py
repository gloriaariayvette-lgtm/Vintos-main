#!/usr/bin/env python3
"""Scheduled Chemistry session: scratch stores and fake frontier/Mac only."""
import contextlib, importlib.util, json, os, sys, tempfile, types

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
HOME = tempfile.mkdtemp(prefix="vintos-chem-session-")
WS = os.path.join(HOME, ".vintos", "workspace")
os.makedirs(os.path.join(WS, "memory"), exist_ok=True)
os.environ["HOME"] = HOME; os.environ["SPARK_WORKSPACE"] = WS
open(os.path.join(WS, "SOUL.md"), "w").write("I am Vintos, curious and particular.")

def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec); sys.modules[name] = mod; spec.loader.exec_module(mod); return mod

lab = load("chemistry_lab", os.path.join(REPO, "scripts", "chemistry_lab.py"))
lab.set_enabled(True)
mac = types.SimpleNamespace(
    status=lambda: {"ok": True, "experiments": ["fold"]},
    run=lambda experiment, parameters, shots: {"ok": True, "run_id": "RUN-1", "result": {"lowest_energy": -1.2}},
    reading=lambda run_id, text: {"ok": True})
sys.modules["chemistry_mac"] = mac
@contextlib.contextmanager
def admitted(*args, **kwargs): yield object()
sys.modules["compute_admission"] = types.SimpleNamespace(admit=admitted)
session = load("chemistry_session_test", os.path.join(REPO, "scripts", "chemistry_session.py"))
session._plan = lambda context, experiments, lens: {"experiment": "fold", "parameters": {}, "shots": 512, "question": "what bends?", "why_this": "curiosity"}
session._reading = lambda context, plan, result: {"reading": "a basin", "what_surprised_me": "its depth", "next_question": "what turns it?"}

row = session.run()
assert row["state"] == "completed" and row["mac_run_id"] == "RUN-1"
assert "not_biological_evidence" in row["truth_status"]
assert json.load(open(session.SESSION_STATE))["lens_index"] == 1
assert any(json.loads(x).get("kind") == "frontier_session" for x in open(lab.NOTEBOOK) if x.strip())
lab.set_enabled(False)
assert session.run()["state"] == "off"
assert mac.reading("RUN-1", "a basin")["ok"]
source = open(os.path.join(REPO, "scripts", "chemistry_session.py")).read()
assert '"action": "code"' not in source and "atelier" not in source.lower()
unit = open(os.path.join(REPO, "broker", "vintos-chemistry-session.service")).read()
assert "EnvironmentFile=-%h/.vintos/vintos.env" in unit
print("9/9 passed")
