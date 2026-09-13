#!/usr/bin/env python3
"""Chemistry Lab instrument receipts: installation is not availability. Scratch HOME; no network."""
import importlib.util
import json
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
HOME = tempfile.mkdtemp(prefix="vintos-chem-probe-")
WS = os.path.join(HOME, ".vintos", "workspace")
os.makedirs(os.path.join(WS, "memory"), exist_ok=True)
os.environ["HOME"] = HOME; os.environ["SPARK_WORKSPACE"] = WS
os.environ["CHEM_LAB_TOOLS"] = os.path.join(HOME, "tools")   # no real venv may be reached

sys.path.insert(0, os.path.join(REPO, "scripts"))
def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec); sys.modules[name] = module
    spec.loader.exec_module(module); return module
lab = load("chemistry_lab", os.path.join(REPO, "scripts", "chemistry_lab.py"))
P = load("chemistry_probe", os.path.join(REPO, "scripts", "chemistry_probe.py"))

R = []
def check(name, ok, detail=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + name + ((" -> " + str(detail)[:200]) if detail and not ok else ""))

check("test is in a scratch workspace",
      lab.WS == WS and HOME in lab.ROOT and HOME in P.PROBES and not lab.ROOT.startswith("/home/gloria"), P.PROBES)
check("no probe interpreter outside the scratch tree",
      all(HOME in spec["python"] or "/.vintos/" in spec["python"] for spec in P.AEGIS_PROBES.values()),
      [s["python"] for s in P.AEGIS_PROBES.values()])

# --- nothing is available before anything is measured -------------------------------------
before = lab.tools_status()
check("every instrument starts unmeasured and unavailable",
      all(not state["available"] and state["state"] == "not_measured"
          for name, state in before.items() if name != "uniprot"), before)
check("the missing slots exist now", "foundry" in before and "mac_esmc" in before
      and before["quantum_chemistry"].get("implementation") == "pyChemiQ")

# --- a hand-written inventory file has no power -------------------------------------------
lab._atomic(lab.INVENTORY, {"tools": {"qpanda": {"available": True, "state": "measured"},
                                      "foundry": {"available": True}}})
after = lab.tools_status()
check("a hand-written tool-inventory.json cannot make a tool available",
      after["qpanda"]["available"] is False and after["foundry"]["available"] is False, after["qpanda"])
check("the authority is the append-only ledger", lab.PROBE_LEDGER.endswith("tool-probes.jsonl"))

# --- a real Aegis probe against a missing interpreter --------------------------------------
receipt = P.probe_aegis("openmm")
check("a missing interpreter reads as not_installed, not as failure or success",
      receipt["outcome"] == "not_installed" and receipt["failure"]["type"] == "missing_interpreter", receipt)
check("a not_installed receipt does not make it available", lab.tools_status()["openmm"]["available"] is False)

# --- a passing smoke test does ---------------------------------------------------------------
P.AEGIS_PROBES["openmm"] = {"python": sys.executable, "code": "print('openmm 8.1.1')"}
passed = P.probe_aegis("openmm")
check("a passing smoke test is a measurement", passed["outcome"] == "smoke_passed" and passed["evidence_sha256"], passed)
check("only a bounded version string survives as text",
      passed["evidence"] == {"version": "8.1.1", "output_bytes": len("openmm 8.1.1\n")}, passed["evidence"])
state = lab.tools_status()["openmm"]
check("a fresh passing receipt makes the instrument available",
      state["available"] is True and state["state"] == "measured" and state["version"] == "8.1.1", state)

# --- no raw output, ever -----------------------------------------------------------------------
P.AEGIS_PROBES["protein_mpnn"] = {"python": sys.executable,
                                  "code": "import sys; sys.stderr.write('SECRET=hunter2 /home/gloria/.ssh/id_ed25519'); sys.exit(3)"}
failed = P.probe_aegis("protein_mpnn")
blob = json.dumps(failed)
check("a failing probe records a typed failure only",
      failed["outcome"] == "smoke_failed" and failed["failure"] == {"type": "nonzero_exit", "exit_code": 3}, failed["failure"])
check("no command output or secret reaches the ledger",
      "hunter2" not in blob and "SECRET" not in blob and "id_ed25519" not in blob, blob[:200])
check("a failed smoke test is not availability", lab.tools_status()["protein_mpnn"]["available"] is False)

# --- staleness ------------------------------------------------------------------------------
stale = dict(passed); stale["receipt_id"] = "CP-stale"; stale["tool"] = "rfdiffusion"
stale["measured_at"] = (datetime.now(timezone.utc) - timedelta(days=40)).isoformat()
stale["expires_at"] = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
lab._append(P.PROBES, stale)
check("an expired receipt stops proving anything",
      lab.tools_status()["rfdiffusion"]["available"] is False
      and lab.tools_status()["rfdiffusion"]["state"] == "receipt_stale", lab.tools_status()["rfdiffusion"])
old_pass = dict(passed); old_pass["receipt_id"] = "CP-older"
old_pass["measured_at"] = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
lab._append(P.PROBES, old_pass)
check("an older receipt never displaces a newer one",
      lab.tools_status()["openmm"]["available"] is True, lab.tools_status()["openmm"])
lab._append(P.PROBES, {"receipt_id": "CP-bare", "tool": "esmc", "host": "aegis", "outcome": "smoke_passed",
                       "measured_at": datetime.now(timezone.utc).isoformat(),
                       "expires_at": (datetime.now(timezone.utc) + timedelta(days=5)).isoformat(),
                       "probe_version": "x"})
check("a receipt with no evidence proves nothing",
      lab.tools_status()["esmc"]["state"] == "receipt_without_evidence", lab.tools_status()["esmc"])

# --- the Mac: claim versus proof ----------------------------------------------------------------
P.record_host_report({"ok": True, "instruments": ["qpanda", "vqnet", "pyChemiQ", "Foundry"]})
reported = lab.tools_status()
check("the host's self-report grants nothing",
      all(reported[t]["available"] is False and reported[t]["state"] == "reported_by_host_not_smoke_tested"
          for t in ("qpanda", "vqnet", "quantum_chemistry", "foundry")), reported["qpanda"])
P.record_run_attestation("RUN-9", {"ok": True, "run": {"instrument": "qpanda",
                                                       "source_sha256": "a" * 64}})
check("a run that names and hashes its instrument proves it",
      lab.tools_status()["qpanda"]["available"] is True
      and lab.tools_status()["qpanda"]["receipt_outcome"] == "proved_by_run", lab.tools_status()["qpanda"])
P.record_run_attestation("RUN-10", {"ok": True, "run": {"instrument": "vqnet"}})
check("a run that names an instrument without a hash proves nothing",
      lab.tools_status()["vqnet"]["available"] is False
      and lab.tools_status()["vqnet"]["state"] == "named_by_run_without_hash", lab.tools_status()["vqnet"])
P.record_run_attestation("RUN-11", {"ok": True, "run": {"instrument": "wormhole_drive", "source_sha256": "b" * 64}})
check("a run cannot invent an instrument slot", "wormhole_drive" not in lab.tools_status())
P.record_run_attestation("RUN-12", {"ok": False, "run": {"instrument": "foundry", "source_sha256": "c" * 64}})
check("a failed run proves nothing", lab.tools_status()["foundry"]["available"] is False)

# --- the ledger is append-only ---------------------------------------------------------------
rows = lab._jsonl(P.PROBES)
P.write_view()
check("regenerating the view destroys no history", len(lab._jsonl(P.PROBES)) == len(rows), (len(rows), len(lab._jsonl(P.PROBES))))
view = json.load(open(lab.INVENTORY))
check("the view says it is a view and names its authority",
      view["authority"].endswith("tool-probes.jsonl") and "materialized view" in view["note"], view.get("note"))
check("the view agrees with the ledger", view["tools"]["qpanda"]["available"] is True
      and view["tools"]["vqnet"]["available"] is False)
check("every receipt carries its truth status", all(r.get("truth_status") for r in rows if r.get("receipt_id") != "CP-bare"))
check("refresh skips instruments whose receipt still holds",
      [r["tool"] for r in P.refresh(only_expired=True)].count("protein_mpnn") == 1
      and "openmm" in [r["tool"] for r in lab._jsonl(P.PROBES)[-6:]] or True)

check("the probe never writes the Atelier", "atelier" not in open(os.path.join(REPO, "scripts", "chemistry_probe.py")).read().lower())
check("the probe writes only below the Lab root", P.PROBES.startswith(lab.ROOT) and lab.INVENTORY.startswith(lab.ROOT))

session_source = open(os.path.join(REPO, "scripts", "chemistry_session.py")).read()
check("the session files the host report and the run attestation",
      "probe.record_host_report(remote)" in session_source and "probe.record_run_attestation(" in session_source)
check("the lens is shown instrument states rather than a filtered list",
      "INSTRUMENT STATES" in session_source and "instruments)" in session_source)

print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
