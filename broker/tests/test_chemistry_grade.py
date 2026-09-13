#!/usr/bin/env python3
"""Chemistry Lab grading: ran and good are different facts. Scratch HOME only; no model or network."""
import importlib.util
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
HOME = tempfile.mkdtemp(prefix="vintos-chem-grade-")
WS = os.path.join(HOME, ".vintos", "workspace")
os.makedirs(os.path.join(WS, "memory"), exist_ok=True)
os.environ["HOME"] = HOME; os.environ["SPARK_WORKSPACE"] = WS

sys.path.insert(0, os.path.join(REPO, "scripts"))
def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec); sys.modules[name] = module
    spec.loader.exec_module(module); return module
lab = load("chemistry_lab", os.path.join(REPO, "scripts", "chemistry_lab.py"))
G = load("chemistry_grade", os.path.join(REPO, "scripts", "chemistry_grade.py"))

R = []
def check(name, ok, detail=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + name + ((" -> " + str(detail)[:200]) if detail and not ok else ""))

check("test is in a scratch workspace",
      lab.WS == WS and HOME in lab.ROOT and HOME in G.GRADES and not lab.ROOT.startswith("/home/gloria"), G.GRADES)
check("the grader sends nothing", not hasattr(G, "request") and "urllib" not in dir(G) and "subprocess" not in dir(G))

def reply(points, ok=True, isolation=None, **extra):
    run = {"result": {"results": points}}
    if isolation is not None: run["isolation"] = isolation
    value = {"ok": ok, "run": run}; value.update(extra); return value

# --- the run that started this: operational, and not good --------------------------------
REAL = [{"bond_length": 0.735, "vqe_energy": -0.478030, "hartree_fock_energy": -1.116999,
         "exact_energy": -1.137306, "error": 0.659276, "recovered_correlation": -31.4654,
         "converged": True, "iterations": 57}]
ISO = {"isolation": "OS-enforced", "network": False, "writes": "scratch only", "receipt_owner": "parent"}
row = G.grade("RUN-H2", "molecule", reply(REAL, isolation=ISO), {"experiment": "molecule", "shots": 4096})
point = row["points"][0]
check("the poor H2 run grades as worse than Hartree-Fock",
      point["accuracy_outcome"] == "WORSE_THAN_HARTREE_FOCK" and row["aggregate_accuracy"] == "ALL_WORSE_THAN_HARTREE_FOCK", row["aggregate_accuracy"])
check("execution state is recorded separately from accuracy",
      row["execution_state"] == "completed" and "execution_state" in row and "aggregate_accuracy" in row, row["execution_state"])
check("the energy gap matches the reported numbers", abs(point["energy_above_hartree_fock"] - 0.638969) < 1e-9, point["energy_above_hartree_fock"])
check("negative recovered correlation is a reading, not a fault",
      point["correlation_recovered"] is not None and abs(point["correlation_recovered"] + 31.4654) < 1e-3
      and point["counts_as"] == "accuracy", point["correlation_recovered"])
check("the nested doorway shape is parsed and named", row["points_path"] == "run.result.results", row["points_path"])
check("the resolved field names are auditable", row["field_map"]["vqe"] == "vqe_energy" and row["field_map"]["exact"] == "exact_energy", row["field_map"])
check("the bench's own error and correlation are kept as host_reported only",
      point["host_reported"].get("recovered_correlation") == -31.4654
      and "recovered_correlation" not in row, point["host_reported"])

# --- the bench's real reply shape: isolation lives at run.execution -----------------------
DB99249 = {"ok": True, "run_id": "RUN-REAL", "configured": True,
           "run": {"experiment": "molecule", "shots": 4096,
                   "source_sha256": "d" * 64,
                   "execution": {"isolation": "OS-enforced", "network": False,
                                 "home": False, "writes": "scratch only",
                                 "receipt_owner": "parent"},
                   "result": {"molecule": "H2", "basis": "sto-3g",
                              "results": [{"bond_length": 0.735, "vqe_energy": -0.478030,
                                           "hartree_fock_energy": -1.116999,
                                           "exact_energy": -1.137306, "error": 0.659276,
                                           "recovered_correlation": -31.4654}]}}}
real = G.grade("RUN-REAL", "molecule", DB99249)
check("the bench's real isolation receipt at run.execution is found",
      real["isolation_receipted"] is True and real["isolation_attestation"] == "host_attested"
      and real["isolation"]["network"] is False, real["isolation_attestation"])
check("the real reply still grades as worse than Hartree-Fock",
      real["aggregate_accuracy"] == "ALL_WORSE_THAN_HARTREE_FOCK" and real["execution_state"] == "completed", real)
nested = G.grade("RUN-NESTED", "molecule", {"ok": True, "run": {"execution": {"isolation": {
    "network": False, "writes": "scratch only"}}, "result": {"results": [{"vqe_energy": -1.0}]}}})
check("an isolation block nested under execution is found too", nested["isolation_receipted"] is True, nested)
notiso = G.grade("RUN-NOTISO", "molecule", {"ok": True, "run": {"execution": {"host": "mac", "seconds": 4},
                                                                "result": {"results": [{"vqe_energy": -1.0}]}}})
check("an execution block that says nothing about isolation is not read as one",
      notiso["isolation_receipted"] is False, notiso["isolation_attestation"])

# --- isolation is attested, never proven -------------------------------------------------
check("isolation is host-attested", row["isolation_receipted"] is True and row["isolation_attestation"] == "host_attested", row["isolation_attestation"])
bare = G.grade("RUN-BARE", "molecule", reply(REAL))
check("a result with no isolation block says so", bare["isolation_receipted"] is False and bare["isolation_attestation"] == "absent")
check("no row ever claims isolation was verified here",
      all("verified" not in json.dumps(r.get("isolation_attestation")) for r in G.history(50)))

# --- ordering: a variational violation is never a success --------------------------------
bad = G.grade("RUN-BELOW", "molecule", reply([{"vqe_energy": -2.0, "hartree_fock_energy": -1.116999, "exact_energy": -1.137306}]))
check("below the exact ground state is INVALID, not BETTER",
      bad["points"][0]["accuracy_outcome"] == "INVALID_BELOW_EXACT" and bad["points"][0]["counts_as"] == "nothing", bad["points"][0]["accuracy_outcome"])
check("one invalid point names the whole curve", bad["aggregate_accuracy"] == "ANY_INVALID_BELOW_EXACT", bad["aggregate_accuracy"])

# --- the ungradeable ---------------------------------------------------------------------
noref = G.grade("RUN-NOREF", "molecule", reply([{"vqe_energy": -1.0}]))
check("no Hartree-Fock reference means ungraded, not passed",
      noref["points"][0]["accuracy_outcome"] == "UNGRADED_NO_REFERENCE" and noref["points"][0]["counts_as"] == "nothing"
      and noref["aggregate_accuracy"] == "NO_GRADEABLE_POINTS", noref["aggregate_accuracy"])
junk = G.grade("RUN-JUNK", "molecule", reply([{"vqe_energy": "not-a-number", "hartree_fock_energy": float("inf")}]))
check("non-finite and non-numeric energies are unreadable",
      junk["points"][0]["accuracy_outcome"] == "UNGRADED_UNREADABLE" and junk["execution_state"] == "completed_with_unreadable_points", junk["execution_state"])
failed = G.grade("RUN-FAILED", "molecule", {"ok": False, "error": "bench unreachable"})
check("a failed run is a failed execution with nothing graded",
      failed["execution_state"] == "failed" and failed["aggregate_accuracy"] == "NO_GRADEABLE_POINTS")
timeout = G.grade("RUN-TIMEOUT", "molecule", {"ok": False, "state": "unknown_after_timeout"})
check("an unknown outcome stays unknown", timeout["execution_state"] == "unknown_after_timeout")

# --- every curve point is graded ---------------------------------------------------------
curve = G.grade("RUN-CURVE", "molecule", reply([
    {"r": 0.5, "vqe": -1.05, "hf": -1.04, "fci": -1.06},
    {"r": 0.735, "vqe": -1.10, "hf": -1.117, "fci": -1.137},
    {"r": 1.0, "vqe": -1.00, "hf": -1.00, "fci": -1.02}]))
check("every point on the curve is graded", curve["total_points"] == 3 and curve["graded_points"] == 3, curve)
check("a mixed curve is named mixed, not averaged into a pass", curve["aggregate_accuracy"] == "MIXED", curve["aggregate_accuracy"])
check("alternate field names resolve", curve["field_map"]["hartree_fock"] == "hf" and curve["field_map"]["exact"] == "fci", curve["field_map"])
check("each point keeps its own verdict",
      [p["accuracy_outcome"] for p in curve["points"]] ==
      ["BETTER_THAN_HARTREE_FOCK", "WORSE_THAN_HARTREE_FOCK", "AT_HARTREE_FOCK"],
      [p["accuracy_outcome"] for p in curve["points"]])

# --- idempotence on (run_id, grader_version) ---------------------------------------------
again = G.grade("RUN-H2", "molecule", reply(REAL, isolation=ISO))
check("a second grade by the same grader is refused", isinstance(again, dict) and again.get("refused"), again)
saved, G.GRADER_VERSION = G.GRADER_VERSION, "chemistry_grade/test-2"
regrade = G.grade("RUN-H2", "molecule", reply(REAL, isolation=ISO))
G.GRADER_VERSION = saved
check("a new grader version may re-grade the same run",
      not regrade.get("refused") and regrade["grader_version"] == "chemistry_grade/test-2", regrade.get("refused"))
check("both grades survive; neither erases the other",
      len([r for r in G.history(50) if r.get("run_id") == "RUN-H2"]) == 2)
check("a run without an id cannot be graded", G.grade("", "molecule", reply(REAL)).get("refused"))

# --- the context block --------------------------------------------------------------------
block = G.summary_block(8)
check("the context block separates instrument from answer",
      "execution" in block and "accuracy" in block and "ALL_WORSE_THAN_HARTREE_FOCK" in block, block[:200])
check("an invalid point is never advertised as the best one", "-0.883" not in block and "best point" in block, block[:300])

# --- the store stays inside the Lab --------------------------------------------------------
check("grades are written beside the Lab, never into general memory",
      G.GRADES.startswith(lab.ROOT) and not os.path.exists(os.path.join(WS, "memory", "prediction-grades.jsonl")))
check("every row carries its truth status and standing",
      all(r.get("truth_status") and r.get("evidence_standing") for r in G.history(50)))
check("the grader never writes the Atelier", "atelier" not in open(os.path.join(REPO, "scripts", "chemistry_grade.py")).read().lower())

source = open(os.path.join(REPO, "scripts", "chemistry_session.py")).read()
check("the session grades before it asks for reading compute",
      source.index("grading.grade(") < source.index('stage="reading"'))
check("the reading is given the verdict", "_reading(context, plan, result, grade)" in source and "_verdict_block" in source)
check("the session still cannot submit code", '"action": "code"' not in source)

mac_source = open(os.path.join(REPO, "scripts", "chemistry_mac.py")).read()
check("the doorway refuses any action outside the named allowlist",
      'ALLOWED_ACTIONS = ("status", "ledger", "run", "reading")' in mac_source and "action_not_allowed" in mac_source)

print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
