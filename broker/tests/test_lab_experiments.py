#!/usr/bin/env python3
"""The Lab's quantum experiments are offered in the shape the door reads, and a planner's request for one runs.

27 October: QPanda (pyqpanda3 on Gloria's Mac) runs the bench's fold, titrate and molecule, but the investigation
menu showed their parameters flat ({molecule:H2,bond_lengths:[...]}) while the door read request.parameters, a
{"titrate": {...}} request was refused as experiment None, molecule was never chosen, and a completed QPanda run never
renewed QPanda's receipt (the bench names it by the key "pyqpanda3", not under "instruments"), so it has read
receipt_stale since 13 October.

Scratch HOME and Lab stores; the Mac door's transport is a stub returning a bench-shaped reply; every socket is
refused. Nothing reaches the Mac, and no quantum job is started."""
import importlib.util, json, os, socket, sys, tempfile

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
HOME = tempfile.mkdtemp(prefix="vintos-lab-experiments-")
WS = os.path.join(HOME, ".vintos", "workspace")
os.makedirs(os.path.join(WS, "memory"), exist_ok=True)
os.environ["HOME"] = HOME; os.environ["SPARK_WORKSPACE"] = WS
os.environ["VINTOS_CHEMISTRY_MAC_CONFIG"] = os.path.join(HOME, "chemistry-mac.json")
open(os.path.join(WS, "SOUL.md"), "w").write("I am Vintos.")
sys.path.insert(0, os.path.join(REPO, "scripts"))

NET = []
def _no(sock, *a, **k):
    if sock.family != socket.AF_UNIX: NET.append(a)
    raise OSError("this suite reaches nothing")
socket.socket.connect = _no

R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:400]) if d and not ok else ""))

import lab_experiments as E
import chemistry_lab as lab
import chemistry_mac as mac
import chemistry_probe as probe
import lab_tool_calls
import lab_investigations as LI

check("every store is scratch", lab.ROOT.startswith(HOME) and probe.PROBES.startswith(HOME)
      and mac.CONFIG.startswith(HOME), (lab.ROOT, probe.PROBES, mac.CONFIG))

# ---- 1. one definition, agreeing with the door
check("its limits are the door's own", E.MAX_HP_LATTICE_RESIDUES == mac.MAX_HP_LATTICE_RESIDUES
      and E.ESMFOLD_MAX == mac.ESMFOLD_MAX and set(E.EXPERIMENT_PARAMETERS["protein"]) == mac.ESMFOLD_PARAMETERS)
check("it names exactly the experiments the planner may route to", set(E.EXPERIMENTS) == set(LI.EXPERIMENTS),
      (tuple(E.EXPERIMENTS), LI.EXPERIMENTS))
for name, spec in E.EXPERIMENTS.items():
    req = spec["request"]
    check("%s is shown as the request the door reads" % name, req["experiment"] == name
          and isinstance(req["parameters"], dict)
          and set(req["parameters"]) <= set(E.EXPERIMENT_PARAMETERS[name]), req)
check("the quantum ones say what they run on, and it is local", all(
      "pyqpanda3" in E.EXPERIMENTS[n]["runs_on"] and "free" in E.EXPERIMENTS[n]["runs_on"] for n in E.QPANDA_EXPERIMENTS))
check("molecule states its molecules and its bond-length limit", all(
      w in E.EXPERIMENTS["molecule"]["limits"] for w in ("H2", "HeH+", "LiH", "9 bond lengths", "180 s")))

# ---- 2. the investigation planner's menu, before any receipt and after an expired one
menu = LI._menu()["experiments"]
check("the planner's menu offers molecule with its exact request and limits",
      menu["molecule"]["request"] == E.EXPERIMENTS["molecule"]["request"] and menu["molecule"]["limits"]
      and menu["molecule"]["shots"] == "256..16384", menu.get("molecule"))
check("with no receipt, QPanda's state is said, and the experiment is still offered",
      menu["molecule"]["qpanda_receipt"] == "not_measured" and menu["fold"]["qpanda_receipt"] == "not_measured", menu)
check("protein carries no QPanda state", "qpanda_receipt" not in menu["protein"], menu["protein"])
# the Mac's last commissioning receipt, as it stands in her ledger: measured 13 September, held a month
lab._append(probe.PROBES, {"receipt_id": "CP-old", "tool": "qpanda", "host": "mac", "probe_version": probe.PROBE_VERSION,
                           "measured_at": "2026-09-13T08:49:09+00:00", "expires_at": "2026-10-13T08:49:09+00:00",
                           "outcome": "proved_by_run", "evidence_sha256": "a" * 64, "evidence": {"x": 1},
                           "failure": None, "source": "mac_run", "truth_status": "test"})
check("an expired receipt reads receipt_stale in the menu", LI._menu()["experiments"]["titrate"]["qpanda_receipt"]
      == "receipt_stale", LI._menu()["experiments"]["titrate"])

# ---- 3. requests in the shapes planners wrote them reach the door's shape
flat = lab_tool_calls.normalize_request("experiment", {"experiment": "molecule", "molecule": "HeH+",
                                                       "bond_lengths": [0.6, 0.9], "shots": 2048, "why": "w"})
check("flat molecule parameters move under parameters; shots and other keys stay",
      flat == {"experiment": "molecule", "parameters": {"molecule": "HeH+", "bond_lengths": [0.6, 0.9]},
               "shots": 2048, "why": "w"}, flat)
keyed = lab_tool_calls.normalize_request("experiment", {"titrate": {"dial": "chain_stiffness", "from": 0, "to": 0.8,
                                                                    "points": 5, "sequence": "HPHPPHHP"}})
check("{\"titrate\": {...}} (25 October, refused as experiment None) is the titrate experiment",
      keyed == {"experiment": "titrate", "parameters": {"dial": "chain_stiffness", "from": 0, "to": 0.8, "points": 5,
                                                         "sequence": "HPHPPHHP"}}, keyed)
check("and is offered", LI._offer_problem("experiment", keyed) is None, LI._offer_problem("experiment", keyed))
both = E.experiment_request({"experiment": "fold", "sequence": "HHPP", "parameters": {"sequence": "HPHP"}})
check("what is already under parameters wins", both["parameters"] == {"sequence": "HPHP"}, both)
same = {"experiment": "fold", "parameters": {"sequence": "HPHP"}, "shots": 512}
check("a request already in shape is unchanged", E.experiment_request(same) == same)
check("shots are held to the bench's range", (E.bounded_shots(10), E.bounded_shots(10 ** 9), E.bounded_shots("x"))
      == (256, 16384, 4096))

# ---- 4. it runs: the door sends the parameters, and the completed run renews QPanda's receipt
SENT = []
def bench(body, timeout=600):
    SENT.append(body)
    # the shape bench_remote.py returns for a run (checked against the Mac's 24 October titrate run)
    return {"ok": True, "configured": True, "run_id": "20261027-000000-test", "pyqpanda3": "0.4.1",
            "run_file": "/Users/kevin/qlab/bench/runs/20261027-000000-test-molecule.json",
            "run": {"experiment": body["experiment"], "parameters": body["parameters"], "shots": body["shots"],
                    "source_sha256": "b" * 64, "run_id": "20261027-000000-test",
                    "result": {"molecule": "HeH+", "results": [{"bond_length": 0.6, "vqe": -2.8, "exact": -2.85,
                                                                "hartree_fock": -2.84}]}}}
mac.request = bench
LI._gate = lambda inquiry: {}          # the repeat and identity checks have their own suites
result = LI.dispatch("experiment", flat, "how far is VQE from exact across the HeH+ bond?", [])
check("the molecule request is sent as asked", SENT and SENT[-1]["action"] == "run"
      and SENT[-1]["experiment"] == "molecule"
      and SENT[-1]["parameters"] == {"molecule": "HeH+", "bond_lengths": [0.6, 0.9]} and SENT[-1]["shots"] == 2048,
      SENT[-1:])
check("and its result comes back", result.get("ok") and result.get("run_id") == "20261027-000000-test", result)
qp = lab.tools_status()["qpanda"]
check("the completed QPanda run renews QPanda's receipt", qp["available"] is True
      and qp["receipt_outcome"] == "proved_by_run" and qp["version"] == "0.4.1", qp)
check("and the planner's menu now says so", LI._menu()["experiments"]["molecule"]["qpanda_receipt"] == "measured")
check("it proves QPanda only: VQNet and pyChemiQ are not named by the bench",
      lab.tools_status()["vqnet"]["available"] is False and lab.tools_status()["quantum_chemistry"]["available"] is False)

# ---- 5. what does not prove QPanda
before = len(lab._jsonl(probe.PROBES))
probe.record_run_attestation("P", {"ok": True, "pyqpanda3": "0.4.1",
                                   "run": {"experiment": "protein", "source_sha256": "c" * 64, "result": {}}})
probe.record_run_attestation("F", {"ok": False, "pyqpanda3": "0.4.1",
                                   "run": {"experiment": "fold", "source_sha256": "c" * 64, "result": {}}})
probe.record_run_attestation("U", {"ok": True, "pyqpanda3": "unavailable",
                                   "run": {"experiment": "fold", "source_sha256": "c" * 64, "result": {}}})
probe.record_run_attestation("N", {"ok": True, "pyqpanda3": "0.4.1",
                                   "run": {"experiment": "fold", "source_sha256": "c" * 64}})
check("a protein run, a failed run, an unavailable version or a run with no result names nothing",
      len(lab._jsonl(probe.PROBES)) == before, lab._jsonl(probe.PROBES)[before:])
probe.record_host_report({"ok": True, "pyqpanda3": "0.4.1", "experiments": ["fold", "molecule"]})
check("the Mac's status reply is still not a measurement", len(lab._jsonl(probe.PROBES)) == before
      and lab.tools_status()["qpanda"]["available"] is True, lab._jsonl(probe.PROBES)[before:])

# ---- 6. the daily session is shown the same shapes
src = open(os.path.join(REPO, "scripts", "chemistry_session.py")).read()
check("the daily session prompt carries the experiments' exact requests and limits",
      "THEIR EXACT REQUESTS AND LIMITS" in src and "lab_experiments.EXPERIMENTS" in src)

check("nothing left this host", NET == [], NET)
print("\n%d/%d passed" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
