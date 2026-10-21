#!/usr/bin/env python3
"""Scheduled Chemistry session: scratch stores and fake frontier/Mac only."""
import contextlib, importlib.util, json, os, sys, tempfile, types, socket

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
HOME = tempfile.mkdtemp(prefix="vintos-chem-session-")
WS = os.path.join(HOME, ".vintos", "workspace")
os.makedirs(os.path.join(WS, "memory"), exist_ok=True)
os.environ["HOME"] = HOME; os.environ["SPARK_WORKSPACE"] = WS
open(os.path.join(WS, "SOUL.md"), "w").write("I am Vintos, curious and particular.")

def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec); sys.modules[name] = mod; spec.loader.exec_module(mod); return mod

network_attempts = []
def no_network(sock, *args, **kwargs):
    if sock.family != socket.AF_UNIX: network_attempts.append(args)
    raise OSError("test network forbidden")
socket.socket.connect = no_network
sys.modules["line_prospect"] = types.SimpleNamespace(prospect=lambda: None)
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

# 22 October: the whole session stopped on "held_mac_unavailable" whenever the Mac was away, though ESMFold runs
# here on Aegis; he rarely had a folded model, so fold_read and reference_compare had nothing to read.
offered, ran = [], []
mac.status = lambda: {"ok": False, "error": "ssh: connect to host timed out"}
mac.run = lambda experiment, parameters, shots: ran.append((experiment, parameters)) or {
    "ok": True, "result": {"backend": "esmfold", "mean_plddt": 81.2}}
def _plan_protein(context, experiments, lens, instruments=None, offered_entry_ids=None, **leans):
    offered.append(list(experiments))
    return {"addressed_entry_ids": list(offered_entry_ids or []), "experiment": "protein",
            "parameters": {"target_accession": "O43511"}, "shots": 1, "question": "fold pendrin's STAS",
            "why_this": "the ZBTB16 site"}
session._plan = _plan_protein
row = session.run()
R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + ("" if ok else "  ->  %r" % (str(d)[:300],)))
check("its stores are scratch and the Mac is a stub", session.SESSIONS.startswith(HOME) and sys.modules["chemistry_mac"] is mac)
check("with the Mac away, the session is not held: protein is offered", offered == [["protein"]] and row["state"] != "held_mac_unavailable",
      (offered, row.get("state")))
check("and the fold runs, for the sourced protein", ran and ran[0] == ("protein", {"target_accession": "O43511"}), ran)
check("it can be switched back off", hasattr(session, "MAC_AWAY_PROTEIN"))
session.MAC_AWAY_PROTEIN = False
check("nothing reached the network", not network_attempts, network_attempts)
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
