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
seen = {"plan_kw": []}
def _plan_stub(context, experiments, lens, instruments=None, offered_entry_ids=None, **leans):
    seen["plan_kw"].append(leans)
    return {"addressed_entry_ids": list(offered_entry_ids or []), "experiment": "fold", "parameters": {}, "shots": 512,
            "question": "what bends?", "why_this": "curiosity"}
session._plan = _plan_stub
def _reading(context, plan, result, grade=None, lens=None):
    seen["grade"] = grade; seen["verdict"] = session._verdict_block(grade)
    return {"reading": "a basin", "what_surprised_me": "its depth",
            "next_question": "what changes the shape of this basin next?"}
session._reading = _reading

# A test never reaches the world (CLAUDE.md): the Aegis instrument probes shell out to
# real tools and load real model checkpoints on the host that serves her. Replace the
# probe boundary with a pure, in-process measurement BEFORE any session.run() below, so
# no run ever spawns a subprocess or touches a real instrument. The refresh logic under
# test -- expiry, current-receipt selection, "measured once a month, not daily" -- is the
# real chemistry_probe code; only the smoke test itself is stubbed. Without this, every
# session.run() before the line-120 override reached the real instruments on Aegis, which
# is why this suite passed on a box without them and failed on the host that has them.
import chemistry_probe as probe_mod
probe_mod.AEGIS_PROBES = {"openmm": {"marker": "stepped_energy", "entry": "fake"}}
def _fake_probe_aegis(name):
    return probe_mod._receipt(name, "aegis", "smoke_passed",
                              evidence={"exercised": "test-stub"}, source="test-stub")
probe_mod.probe_aegis = _fake_probe_aegis
# Assert the isolation, so a later edit cannot quietly let a run reach a real instrument.
assert probe_mod.probe_aegis is _fake_probe_aegis
assert probe_mod.PROBES.startswith(HOME), probe_mod.PROBES

# One independently scored local finding is carried into the frontier prompt and the
# returned plan acknowledges its exact ID. Delivery and acknowledgment are separate events.
flagged = session.bridge.assess({"at": "2026-09-13T00:00:00+00:00", "source_accessions": ["P12345"],
    "factual_observation": "A sourced compact protein structure was recorded.",
    "attention": "the compact structure", "next_question": "what changes this compact structure?"},
    source_query_succeeded=True)
assert flagged["flagged_for_next_lab_session"] is True

# What he settled with dot in #vintos-dot reaches this run once (2026-10-01), from the scratch store.
import channel_lab_lean
assert channel_lab_lean.STORE.startswith(HOME), channel_lab_lean.STORE
channel_lab_lean.write("fold P02730 with ESMFold", by="gemma")
row = session.run()
assert seen["plan_kw"][-1].get("channel_lean", {}).get("direction") == "fold P02730 with ESMFold", seen["plan_kw"]
assert channel_lab_lean.pending() is None, "shown to one plan, then used"
assert row["state"] == "completed" and row["mac_run_id"] == "RUN-1"
surface = session.lab._jsonl(session.bridge.SURFACES)[-1]
assert surface["offered_entry_ids"] == [flagged["entry_id"]]
assert surface["acknowledged_entry_ids"] == [flagged["entry_id"]]
# The run completed and carries no reference, so it is graded ungradeable rather than passed.
assert row["grade"]["execution_state"] == "completed"
assert row["grade"]["aggregate_accuracy"] == "NO_GRADEABLE_POINTS", row["grade"]
assert seen["grade"] is row["grade"], "the reading is given the verdict, not left to infer it"
assert "not_biological_evidence" in row["truth_status"]
assert json.load(open(session.SESSION_STATE))["lens_index"] == 1
note = [json.loads(x) for x in open(lab.NOTEBOOK) if x.strip() and json.loads(x).get("kind") == "frontier_session"][-1]
assert note["execution_state"] == "completed" and note["aggregate_accuracy"] == "NO_GRADEABLE_POINTS"
import chemistry_spark as spark_mod
assert spark_mod.feed() and spark_mod.feed()[-1]["provenance"]["mac_run_id"] == "RUN-1", \
       "a completed session refreshes the Lab spark feed without a remembered CLI step"

# A run whose answer is worse than Hartree-Fock must reach him saying so.
mac.run = lambda experiment, parameters, shots: {"ok": True, "run_id": "RUN-2", "run": {"result": {"results": [
    {"bond_length": 0.735, "vqe_energy": -0.478030, "hartree_fock_energy": -1.116999, "exact_energy": -1.137306}]}}}
poor = session.run()
assert "channel_lean" not in seen["plan_kw"][-1], "a used channel lean does not steer the next run"
assert poor["grade"]["aggregate_accuracy"] == "ALL_WORSE_THAN_HARTREE_FOCK", poor["grade"]
assert "WORSE_THAN_HARTREE_FOCK" in seen["verdict"] and "not claimed by the bench" in seen["verdict"], seen["verdict"]
assert "+0.638969" in seen["verdict"], seen["verdict"]

# The bench owns its parameter vocabulary; this side bounds shape and records what it dropped.
kept, dropped = session._bounded_parameters({"bond_length": 0.735, "nested": {"a": 1}, "note": "x" * 500})
assert kept["bond_length"] == 0.735 and dropped == ["nested"] and len(kept["note"]) == session.PARAMETER_TEXT
assert session._bounded_parameters({"bad": float("nan")})[1] == ["bad"]
assert session._named_protein_parameters("protein", {}, "How does A1L190 fold?") == {
    "target_accession": "A1L190"}, "a named accession in prose must control the run"
assert session._named_protein_parameters("protein", {"target_accession": "P12345"}, "A1L190") == {
    "target_accession": "P12345"}, "an explicit parameter wins"
os.environ["VINTOS_CHEMISTRY_TARGET_ACCESSION"] = "A1L190"
forced = session._operator_plan(["fold", "protein"])
assert forced["experiment"] == "protein" and forced["parameters"] == {"target_accession": "A1L190"}
os.environ.pop("VINTOS_CHEMISTRY_TARGET_ACCESSION")

lab.set_enabled(False)
assert session.run()["state"] == "off"
assert mac.reading("RUN-1", "a basin")["ok"]
source = open(os.path.join(REPO, "scripts", "chemistry_session.py")).read()
assert '"action": "code"' not in source
assert "atelier_lab_lean.today()" in source, "only the explicit dated lean may steer a session"
assert "wait_s=2" not in source and 'lab.config()["turn_wait_seconds"]' in source
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
# (probe_mod / AEGIS_PROBES / probe_aegis are stubbed at the top so this reaches nothing real.)
assert "instruments_refreshed" in paid, paid.keys()
# Age the held receipt out so there is something expired to refresh; a live one must not be.
from datetime import datetime, timedelta, timezone
_now = datetime.now(timezone.utc)
# Every openmm receipt in this scratch ledger is aged out, so whichever is current is expired. Appending one aged
# row stamped "now" lost to a receipt the previous run had written in the same instant, and the suite failed on
# Aegis only (2026-10-04).
_rows = lab._jsonl(probe_mod.PROBES)
for _r in _rows:
    if _r.get("tool") == "openmm":
        _r["expires_at"] = (_now - timedelta(days=1)).isoformat()
with open(probe_mod.PROBES, "w") as _f:
    _f.write("".join(json.dumps(_r) + "\n" for _r in _rows))
_cur = probe_mod.current_receipts().get("openmm")
assert _cur and _cur["expires_at"] < _now.isoformat(), ("the current openmm receipt is expired", _cur)
before = len(lab._jsonl(probe_mod.PROBES))
again = session.run()
assert len(lab._jsonl(probe_mod.PROBES)) > before, (
    "the session refreshes expired receipts", again.get("state"), again.get("owed_reading"),
    [r for r in lab._jsonl(lab.FAULTS)][-3:], probe_mod.current_receipts().get("openmm"))
assert "openmm" in again["instruments_refreshed"], again["instruments_refreshed"]
third = session.run()
assert third["instruments_refreshed"] == [], "a fresh receipt is not re-measured daily"

# A protein plan with nothing to fold is asked again here, once, instead of failing on the Mac (2026-10-01).
planner = load("chemistry_session_plan", os.path.join(REPO, "scripts", "chemistry_session.py"))
asked = []
def answers(*replies):
    it = iter(replies)
    async def _frontier(lens, system, prompt):
        asked.append(prompt); return next(it)
    planner._frontier = _frontier
answers(json.dumps({"experiment": "protein", "parameters": {}, "question": "How does SLC7A11 fold?"}),
        json.dumps({"experiment": "protein", "parameters": {"target_accession": "Q9UPY5"}, "question": "How does Q9UPY5 fold?"}))
p2 = planner._plan("ctx", ["protein", "fold"], "grok")
assert p2["parameters"]["target_accession"] == "Q9UPY5" and len(asked) == 2, (p2, len(asked))
assert "YOUR PLAN COULD NOT RUN" in asked[1] and "YOUR PLAN COULD NOT RUN" not in asked[0]
asked.clear()
answers(json.dumps({"experiment": "protein", "parameters": {}, "question": "fold it"}),
        json.dumps({"experiment": "protein", "parameters": {}, "question": "fold it"}))
try:
    planner._plan("ctx", ["protein"], "grok"); raised = ""
except ValueError as exc:
    raised = str(exc)
assert "names no UniProt accession" in raised and len(asked) == 2, (raised, len(asked))
asked.clear()
answers(json.dumps({"experiment": "protein", "parameters": {"fragment": "villin"}}))
assert planner._plan("ctx", ["protein"], "grok")["parameters"]["fragment"] == "villin" and len(asked) == 1
answers(json.dumps({"experiment": "fold", "parameters": {}}))
assert planner._plan("ctx", ["fold"], "grok")["experiment"] == "fold", "other experiments are not asked again"

print("43/43 passed")
