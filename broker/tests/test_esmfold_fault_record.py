#!/usr/bin/env python3
"""A fold that fails leaves what it left behind in the record (2026-10-03: four protein runs were filed as
"local ESMFold failed: " and the child's stdout, stderr, exit code and input identity were gone). The real fold is
never run: subprocess.run is a stub that fails, and the Gemma unload path is a stub. Scratch HOME, scratch config,
scratch interpreter path; no network; nothing sends."""
import hashlib, json, os, sys, tempfile, types
HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="esmfold-fault-"); os.environ["HOME"] = HOME
os.environ["SPARK_WORKSPACE"] = os.path.join(HOME, ".vintos", "workspace")
os.environ["VINTOS_CHEMISTRY_MAC_CONFIG"] = os.path.join(HOME, ".vintos", "chemistry-mac.json")
os.environ["VINTOS_ESMFOLD_PYTHON"] = os.path.join(HOME, "no-such-python")
sys.path.insert(0, os.path.join(REPO, "scripts"))
import chemistry_mac as M
R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + ((("  ->  " + str(d)[:300]) if d and not ok else "")))
check("every path the module writes or runs points at scratch",
      M.CONFIG.startswith(HOME) and M.ESMFOLD_PYTHON.startswith(HOME), (M.CONFIG, M.ESMFOLD_PYTHON))
calls = []
def failing_run(cmd, *a, **k):
    calls.append((cmd, k.get("input")))
    return types.SimpleNamespace(returncode=1, stdout="partial line\n",
                                 stderr="Traceback (most recent call last):\nModuleNotFoundError: No module named 'esm'\n")
def killed_run(cmd, *a, **k):
    calls.append((cmd, k.get("input")))
    return types.SimpleNamespace(returncode=-9, stdout="", stderr="")
real_run, real_gemma = M.subprocess.run, M._with_gemma_unloaded
M.subprocess.run = failing_run
M._with_gemma_unloaded = lambda run: None   # never reaches LM Studio; the first failure stands
contract = {"requested_accession": "P02794", "sequence": "M" * 183, "source": {"provider": "UniProtKB"}, "hp_mapping": []}
try:
    check("the process runner and the Gemma unload are stubs",
          M.subprocess.run is failing_run and M._with_gemma_unloaded(None) is None)
    out = M._run_esmfold({"protein_backend": "esmfold"}, contract)
    M.subprocess.run = killed_run
    dead = M._run_esmfold({"protein_backend": "esmfold"}, contract)
finally:
    M.subprocess.run, M._with_gemma_unloaded = real_run, real_gemma
check("the stub ran, with the scratch interpreter only",
      len(calls) == 2 and all(c[0][0].startswith(HOME) for c in calls), calls)
check("it still fails with the child's message",
      out["ok"] is False and out["error"].startswith("local ESMFold failed:") and "No module named 'esm'" in out["error"], out)
fault = out.get("fault") or {}
check("the child's stderr lands whole", "ModuleNotFoundError: No module named 'esm'" in fault.get("stderr", ""), fault)
check("the child's stdout lands", fault.get("stdout") == "partial line\n", fault)
check("the exit code lands, and no signal for a plain exit", fault.get("exit_code") == 1 and fault.get("signal") is None, fault)
sent = calls[0][1]
check("the input identity lands: accession, length, and the hash of exactly what was sent",
      fault.get("accession") == "P02794" and fault.get("sequence_length") == 183
      and fault.get("input_sha256") == hashlib.sha256(json.dumps(json.loads(sent), sort_keys=True).encode()).hexdigest()
      and fault.get("python") == M.ESMFOLD_PYTHON, fault)
dead_fault = dead.get("fault") or {}
check("a killed fold records the signal by name beside the exit code",
      dead["ok"] is False and dead_fault.get("exit_code") == -9 and dead_fault.get("signal") == "SIGKILL", dead)
session_source = open(os.path.join(REPO, "scripts", "chemistry_session.py"), encoding="utf-8").read()
check("the session files the whole failed result in the held_fault row, so the fault block reaches the record",
      'row["mac_result"] = result' in session_source)
import shutil; shutil.rmtree(HOME, ignore_errors=True)
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
