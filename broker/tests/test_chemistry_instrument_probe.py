#!/usr/bin/env python3
"""Fixed Aegis instrument probes: bounded calls, real-artifact criteria, no host writes."""
import importlib.util
import json
import os
import pathlib
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
HOME = tempfile.mkdtemp(prefix="vintos-instrument-probe-")
os.environ["HOME"] = HOME; os.environ["CHEM_LAB_TOOLS"] = os.path.join(HOME, "tools")
spec = importlib.util.spec_from_file_location("instrument_probe", os.path.join(
    REPO, "scripts", "chemistry_instrument_probe.py"))
P = importlib.util.module_from_spec(spec); spec.loader.exec_module(P)

R = []
def check(name, ok, detail=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + name + ((" -> " + str(detail)[:160]) if detail and not ok else ""))

check("test paths are scratch or read-only source paths", str(P.TOOLS).startswith(HOME))
check("only four fixed probes exist", set(P.COMMANDS) == {
      "protein_mpnn", "structure_prediction", "rfdiffusion", "protein_design_mcp"})
source = pathlib.Path(P.__file__).read_text()
check("probe is not a general command runner", "shell=True" not in source and "eval(" not in source and "exec(" not in source)
check("ProteinMPNN requires a FASTA artifact", "artifact_absent" in source and "fasta_records" in source)
check("RFD3 requires metadata and structure artifacts", "json_artifacts" in source and "structure_artifacts" in source)
check("ESMFold names the dependency failure", "dependency_unavailable" in source and "OpenFold" in source)
check("MCP probe dispatches a tool", 'call_tool("get_design_status"' in source)

captured = []
P._emit = lambda value: captured.append(value)
code = P._failure("x", "fixed", failure_type="artifact_absent", detail="no artifact")
check("failures are typed and nonzero", code == 2 and captured[-1]["failure"]["type"] == "artifact_absent")
check("failures digest their diagnostic", len(captured[-1]["failure"]["traceback_sha256"]) == 64)
check("probe writes no Lab, memory, or network state", "urlopen" not in source and "requests" not in source
      and "memory/" not in source and "atelier" not in source.lower())

print("\n%d/%d" % (sum(R), len(R)))
raise SystemExit(0 if all(R) else 1)
