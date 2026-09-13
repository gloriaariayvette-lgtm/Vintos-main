#!/usr/bin/env python3
"""Mac Chemistry commissioning surface: fixed tools, bounded receipts, no bench widening."""
import ast
import importlib.util
import os
import pathlib
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
HOME = tempfile.mkdtemp(prefix="vintos-mac-probe-")
os.environ["HOME"] = HOME; os.environ["VINTOS_QLAB"] = os.path.join(HOME, "qlab")
path = os.path.join(REPO, "bin", "chemistry_mac_probe.py")
spec = importlib.util.spec_from_file_location("mac_probe", path)
P = importlib.util.module_from_spec(spec); spec.loader.exec_module(P)

R = []
def check(name, ok, detail=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + name + ((" -> " + str(detail)[:160]) if detail and not ok else ""))

check("test points every execution environment at scratch", all(str(p).startswith(HOME) for p in P.PYTHONS.values()))
check("the five named Mac instruments are fixed", set(P.PYTHONS) == {
      "qpanda", "vqnet", "quantum_chemistry", "mac_esmc", "foundry"})
source = pathlib.Path(path).read_text()
tree = ast.parse(source)
dangerous = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
             and isinstance(node.func, ast.Name) and node.func.id in ("eval", "exec")]
check("surface accepts no supplied code or paths", "shell=True" not in source and not dangerous)
check("QPanda checks forbidden Bell outcomes", "forbidden_counts" in source)
check("VQNet performs tensor arithmetic", "QTensor" in source and "[2.0, 5.0, 10.0]" in source)
check("pyChemiQ compares VQE against Hartree-Fock", "vqe_hartree" in source and "hartree_fock" in source)
check("Mac ESMC records its actual device", 'device = "mps"' in source)
check("Foundry requires real artifacts", "json_artifacts" in source and "structure_artifacts" in source)
row = P._record("qpanda", True, "ran", {"shots": 1000}, entry_point="Bell")
check("a success is hash-bound and receiptable", row["ok"] and len(row["source_sha256"]) == 64
      and row["receipt"]["output"]["shots"] == 1000)
check("the probe does not write the bench or Lab stores", "bench/runs" not in source and "chemistry-lab" not in source)

print("\n%d/%d" % (sum(R), len(R)))
raise SystemExit(0 if all(R) else 1)
