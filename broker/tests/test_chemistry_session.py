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
session._plan = lambda context, experiments, lens, instruments=None: {"experiment": "fold", "parameters": {}, "shots": 512, "question": "what bends?", "why_this": "curiosity"}
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
# Instrument states ride with the session, and nothing is available without a receipt.
assert row["instrument_states"]["qpanda"] == "not_measured", row["instrument_states"]
assert row["instrument_states"]["foundry"] == "not_measured"
# An owed reading that could not be paid stops the session before the bench is touched.
lab.set_enabled(True)
import chemistry_reading as owed_mod
touched = []
mac.status = lambda: touched.append("status") or {"ok": True, "experiments": ["fold"]}
owed_mod.owe("CHEM-HELD", "claude", {"experiment": "fold"}, {"ok": True, "run_id": "RUN-H"})
def _held_reader(debt): raise TimeoutError("foreground live")
owed_mod.default_reader = _held_reader
held_row = session.run()
assert held_row["state"] == "held_reading_owed", held_row
assert held_row["owed_reading"] == "STILL_HELD", held_row
assert touched == [], "the bench must not be touched while a reading is owed"
assert json.load(open(session.SESSION_STATE))["lens_index"] == 2, "a held session does not spend a lens"
def _broken_reader(debt): raise ValueError("model returned nothing")
owed_mod.default_reader = _broken_reader
refused_row = session.run()
assert refused_row["state"] == "held_reading_owed" and refused_row["owed_reading"] == "REFUSED", refused_row
assert touched == [], "a refused reading also stops the session"
assert session.HOLDS_THE_SESSION == ("STILL_HELD", "REFUSED")
# Once it is paid, the bench is reachable again.
owed_mod.default_reader = lambda debt: {"reading": "read at last", "what_surprised_me": "", "next_question": ""}
paid = session.run()
assert paid["state"] == "completed" and touched == ["status"], (paid["state"], touched)
assert paid["owed_reading"] == "READ", paid["owed_reading"]

# The instrument refresh is actually connected, and only touches expired receipts.
assert "instruments_refreshed" in paid, paid.keys()
import chemistry_probe as probe_mod
calls = []
probe_mod.AEGIS_PROBES = {"openmm": {"argv": [sys.executable, "-c", "print('stepped_energy 1.0')"],
                                     "marker": "stepped_energy", "entry": "fake"}}
# Age the held receipt out so there is something expired to refresh; a live one must not be.
from datetime import datetime, timedelta, timezone
_now = datetime.now(timezone.utc)
lab._append(probe_mod.PROBES, {"receipt_id": "CP-aged", "tool": "openmm", "host": "aegis",
                               "outcome": "not_configured", "probe_version": "x",
                               "measured_at": _now.isoformat(),
                               "expires_at": (_now - timedelta(days=1)).isoformat()})
before = len(lab._jsonl(probe_mod.PROBES))
again = session.run()
assert len(lab._jsonl(probe_mod.PROBES)) > before, "the session refreshes expired receipts"
assert "openmm" in again["instruments_refreshed"], again["instruments_refreshed"]
third = session.run()
assert third["instruments_refreshed"] == [], "a fresh receipt is not re-measured daily"

print("35/35 passed")
