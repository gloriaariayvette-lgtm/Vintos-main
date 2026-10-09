#!/usr/bin/env python3
"""A RUN: line that names one of his ESMFold models by its full Aegis path (.../memory/chemistry-lab/artifacts/
esmfold/X.pdb) is the Lab's own file, not an accession; it is cut down to artifacts/... and checked against the
artifact list like any other file. Scratch HOME; the relay runner is a stub; nothing reaches the network."""
import importlib.util, os, sys, tempfile, types

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
HOME = tempfile.mkdtemp(prefix="vintos-fold-read-abs-")
os.environ["HOME"] = HOME; os.environ["SPARK_WORKSPACE"] = os.path.join(HOME, ".vintos", "workspace")
def no_network(*a, **k): raise AssertionError("a test must never reach the network")
sys.modules["requests"] = types.SimpleNamespace(get=no_network, post=no_network)
sys.modules["plugin_gateway"] = types.SimpleNamespace(run_skill=no_network, call=no_network)
spec = importlib.util.spec_from_file_location("lab_instruments", os.path.join(REPO, "scripts", "lab_instruments.py"))
L = importlib.util.module_from_spec(spec); spec.loader.exec_module(L)
R = []
def check(name, ok, detail=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + name + ((" -> " + str(detail)[:400]) if detail and not ok else ""))
check("the Lab, its artifacts and its ledger are in the scratch workspace",
      str(L.LAB).startswith(HOME) and str(L.ARTIFACTS).startswith(HOME) and str(L.LEDGER).startswith(HOME))
check("the relay is a stub", sys.modules["plugin_gateway"].run_skill is no_network)
(L.ARTIFACTS / "esmfold").mkdir(parents=True, exist_ok=True)
model = L.ARTIFACTS / "esmfold" / "O43511-20261007.pdb"
model.write_text("ATOM      1  CA  MET A   1       0.000   0.000   0.000  1.00 90.00           C\n")
calls = []
def runner(surface, skill, question, operation=None, input_files=()):
    calls.append((surface, skill, operation, list(input_files))); return {"receipt": {"receipt_id": "r1"}, "summary": "helices: none", "files": []}
absolute = str(model)          # the scratch twin of /home/gloria/.vintos/workspace/memory/chemistry-lab/artifacts/esmfold/X.pdb
check("the test path has the Aegis shape", "memory/chemistry-lab/artifacts/esmfold/" in absolute, absolute)
out, words = L.from_slack({"skill": "fold_read", "model": absolute, "range": [1, 1]}, runner=runner)
check("an absolute Aegis path to a model the Lab has runs fold_read on that file",
      out is not None and "no ESMFold model" not in words and calls and calls[0][1] == "fold_read"
      and calls[0][3] == [str(model)] and out["receipt"]["records"][0]["inputs"] == ["artifacts/esmfold/O43511-20261007.pdb"], words)
out, words = L.from_slack({"skill": "fold_read", "model": str(L.ARTIFACTS / "esmfold" / "P99999-nope.pdb"), "range": [1, 1]}, runner=runner)
check("an absolute path to a model the Lab does not hold is still refused by the artifact list",
      out is None and "artifacts the Lab listed" in words and len(calls) == 1, words)
check("nothing was written outside the scratch workspace", str(L.LEDGER).startswith(HOME) and os.path.isfile(L.LEDGER))
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
