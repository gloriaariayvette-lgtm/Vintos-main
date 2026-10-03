#!/usr/bin/env python3
"""A fold that dies without a word says why (2026-10-03: four protein runs failed as "local ESMFold failed: " and
nothing else). The real fold is never run: a stub process exits by a signal. Scratch HOME; no network."""
import os, sys, tempfile, types
HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="esmfold-death-"); os.environ["HOME"] = HOME
os.environ["SPARK_WORKSPACE"] = os.path.join(HOME, ".vintos", "workspace")
sys.path.insert(0, os.path.join(REPO, "scripts"))
import chemistry_mac as M
R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:300]) if d and not ok else ""))
check("killed: named, with the likely cause and the length", "SIGKILL (exit -9) on a 640-residue sequence" in M._death(-9, 640)
      and "out of memory" in M._death(-9, 640), M._death(-9, 640))
check("a native crash is named as one", "SIGSEGV" in M._death(-11, 300) and "native code" in M._death(-11, 300))
check("a plain exit with no message says so", M._death(3, 120) == "exit 3 with no message on a 120-residue sequence")
real_run = M.subprocess.run
M.subprocess.run = lambda *a, **k: types.SimpleNamespace(returncode=-9, stdout="", stderr="")
try:
    out = M._run_esmfold({}, {"requested_accession": "A1L190", "sequence": "M" * 640, "source": {}, "hp_mapping": []})
finally:
    M.subprocess.run = real_run
check("the Lab's record carries it instead of an empty reason",
      out["ok"] is False and out["error"].startswith("local ESMFold failed: SIGKILL (exit -9) on a 640-residue sequence"), out)
import shutil; shutil.rmtree(HOME, ignore_errors=True)
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
