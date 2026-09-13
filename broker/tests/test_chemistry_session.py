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
seen = {}
def _reading(context, plan, result, grade=None):
    seen["grade"] = grade; seen["verdict"] = session._verdict_block(grade)
    return {"reading": "a basin", "what_surprised_me": "its depth", "next_question": "what turns it?"}
session._reading = _reading

row = session.run()
assert row["state"] == "completed" and row["mac_run_id"] == "RUN-1"
# The run completed and carries no reference, so it is graded ungradeable rather than passed.
assert row["grade"]["execution_state"] == "completed"
assert row["grade"]["aggregate_accuracy"] == "NO_GRADEABLE_POINTS", row["grade"]
assert seen["grade"] is row["grade"], "the reading is given the verdict, not left to infer it"
assert "not_biological_evidence" in row["truth_status"]
assert json.load(open(session.SESSION_STATE))["lens_index"] == 1
note = [json.loads(x) for x in open(lab.NOTEBOOK) if x.strip() and json.loads(x).get("kind") == "frontier_session"][-1]
assert note["execution_state"] == "completed" and note["aggregate_accuracy"] == "NO_GRADEABLE_POINTS"

# A run whose answer is worse than Hartree-Fock must reach him saying so.
mac.run = lambda experiment, parameters, shots: {"ok": True, "run_id": "RUN-2", "run": {"result": {"results": [
    {"bond_length": 0.735, "vqe_energy": -0.478030, "hartree_fock_energy": -1.116999, "exact_energy": -1.137306}]}}}
poor = session.run()
assert poor["grade"]["aggregate_accuracy"] == "ALL_WORSE_THAN_HARTREE_FOCK", poor["grade"]
assert "WORSE_THAN_HARTREE_FOCK" in seen["verdict"] and "not claimed by the bench" in seen["verdict"], seen["verdict"]
assert "+0.638969" in seen["verdict"], seen["verdict"]

# The bench owns its parameter vocabulary; this side bounds shape and records what it dropped.
kept, dropped = session._bounded_parameters({"bond_length": 0.735, "nested": {"a": 1}, "note": "x" * 500})
assert kept["bond_length"] == 0.735 and dropped == ["nested"] and len(kept["note"]) == session.PARAMETER_TEXT
assert session._bounded_parameters({"bad": float("nan")})[1] == ["bad"]

lab.set_enabled(False)
assert session.run()["state"] == "off"
assert mac.reading("RUN-1", "a basin")["ok"]
source = open(os.path.join(REPO, "scripts", "chemistry_session.py")).read()
assert '"action": "code"' not in source and "atelier" not in source.lower()
# The far door is wider than this one; the near side refuses explicitly rather than by omission.
door = open(os.path.join(REPO, "scripts", "chemistry_mac.py")).read()
assert 'ALLOWED_ACTIONS = ("status", "ledger", "run", "reading")' in door
sys.modules.pop("chemistry_mac")
real_mac = load("chemistry_mac_real", os.path.join(REPO, "scripts", "chemistry_mac.py"))
assert real_mac.request({"action": "code", "source": "print(1)"})["refused"] == "action_not_allowed"
unit = open(os.path.join(REPO, "broker", "vintos-chemistry-session.service")).read()
assert "EnvironmentFile=-%h/.vintos/vintos.env" in unit
print("21/21 passed")
