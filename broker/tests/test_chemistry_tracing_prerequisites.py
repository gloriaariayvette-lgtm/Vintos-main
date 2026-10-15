#!/usr/bin/env python3
"""Eliot in both of the Lab's interpreters (2026-10-15): the read-only readiness check, VINTOS_ELIOT_REQUIRED, and
the ESMFold worker's log failures as its normal receipt.

Eliot, torch and transformers are stand-in modules on a scratch import path, so this suite means the same whether or
not the machine running it has eliot installed. Scratch HOME and SPARK_WORKSPACE: every log and probe file lands in a
throwaway folder. No fold, no model, no CUDA, no network."""
import contextlib, io, json, os, socket, subprocess, sys, tempfile, types
HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="tracing-prereq-"); os.environ["HOME"] = HOME
WS = os.path.join(HOME, ".vintos", "workspace"); os.environ["SPARK_WORKSPACE"] = WS
os.environ.pop("VINTOS_ELIOT_REQUIRED", None)
NET = []
def _no_net(self, *a, **k):
    if self.family != socket.AF_UNIX: NET.append(a)
    raise OSError("this suite reaches nothing")
socket.socket.connect = _no_net
SCRIPTS = os.path.join(REPO, "scripts"); sys.path.insert(0, SCRIPTS)
R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:500]) if d and not ok else ""))

LAB_DIR = os.path.join(WS, "memory", "chemistry-lab"); DIAG = os.path.join(LAB_DIR, "diagnostics")
os.makedirs(DIAG)
# stand-ins: an eliot with a version, a torch that marks itself imported, and an eliot that cannot be imported
WITH = os.path.join(HOME, "with-eliot"); WITHOUT = os.path.join(HOME, "without-eliot")
for d in (WITH, WITHOUT): os.makedirs(d)
open(os.path.join(WITH, "eliot.py"), "w").write("__version__ = '9.9-test'\n")
open(os.path.join(WITHOUT, "eliot.py"), "w").write("raise ImportError('no eliot in this interpreter (stand-in)')\n")
for d in (WITH, WITHOUT):
    open(os.path.join(d, "torch.py"), "w").write("LOADED = True\n")
    open(os.path.join(d, "transformers.py"), "w").write("LOADED = True\n")
check("every log and probe lands in a scratch workspace", WS.startswith(HOME) and DIAG.startswith(HOME))

import chemistry_tracing as T
def readiness(lab_path, esm_path):
    """Run the CLI as she would, each interpreter seeing only its own import path."""
    py = sys.executable
    out = {}
    for role, path in (("lab", lab_path), ("esmfold", esm_path)):
        exe = os.path.join(HOME, "python-%s-%s" % (role, os.path.basename(path)))
        open(exe, "w").write("#!/bin/sh\nPYTHONPATH=%s exec %s \"$@\"\n" % (path, py)); os.chmod(exe, 0o755)
        out[role] = exe
    done = subprocess.run([py, "-B", os.path.join(SCRIPTS, "chemistry_tracing.py"), "readiness",
                           "--lab-python", out["lab"], "--esmfold-python", out["esmfold"]],
                          capture_output=True, text=True, timeout=120)
    return done, out

print("--- readiness ---")
done, exes = readiness(WITH, WITH)
check("both interpreters ready: exit 0, each named with eliot's version, path and log", done.returncode == 0
      and "lab      ready" in done.stdout and "esmfold  ready" in done.stdout and "9.9-test" in done.stdout
      and "eliot.jsonl" in done.stdout and "eliot-esmfold.log" in done.stdout, done.stdout + done.stderr)
check("the consumer modules were imported without torch or transformers (a stand-in torch was importable)",
      "loaded torch" not in done.stdout and "loaded transformers" not in done.stdout, done.stdout)
check("nothing was left behind: no trace and no probe file", sorted(os.listdir(DIAG)) == []
      and "eliot.jsonl" not in os.listdir(LAB_DIR), (os.listdir(DIAG), os.listdir(LAB_DIR)))
done, exes = readiness(WITHOUT, WITH)
check("eliot missing in the Lab's interpreter: exit 2, naming that interpreter and the import error",
      done.returncode == 2 and "lab      NOT READY" in done.stdout and exes["lab"] in done.stdout
      and "no eliot in this interpreter (stand-in)" in done.stdout and "esmfold  ready" in done.stdout, done.stdout)
done, _ = readiness(WITH, WITHOUT)
check("eliot missing in the ESMFold interpreter: exit 2 too", done.returncode == 2 and "esmfold  NOT READY" in done.stdout)
log = os.path.join(LAB_DIR, "eliot.jsonl"); open(log, "w").write("old line\n")
st = os.stat(log)
done, _ = readiness(WITH, WITH)
check("an existing log is opened for append and not written", done.returncode == 0 and open(log).read() == "old line\n"
      and os.stat(log).st_size == st.st_size and "opened for append, nothing written" in done.stdout, done.stdout)
os.unlink(log); os.rmdir(DIAG)
done, _ = readiness(WITH, WITH)
check("a missing log folder is reported, not created", done.returncode == 2 and "does not exist" in done.stdout
      and not os.path.exists(DIAG), done.stdout)
os.makedirs(DIAG)
check("an interpreter that cannot run is reported, not raised",
      T.check(os.path.join(HOME, "no-such-python"), "lab")["ok"] is False)
check("readiness is in the deploy manifest", "chemistry_tracing.py" in open(os.path.join(SCRIPTS, "deploy-atelier.sh")).read())
req = open(os.path.join(SCRIPTS, "requirements-chemistry-tracing.txt")).read()
check("the requirements file asks for eliot alone", [l for l in req.splitlines() if l.strip() and not l.startswith("#")]
      == ["eliot>=1.14,<2"], req)

print("--- required mode, at the trace entry points ---")
sys.modules["eliot"] = None          # an import of eliot fails here, whatever this machine has installed
for name in ("chemistry_lab", "chemistry_esmfold"):
    sys.modules.pop(name, None)
import chemistry_lab as LAB, chemistry_esmfold as ESM
check("both modules record why eliot could not be imported", LAB._eliot is None and ESM._eliot is None
      and "eliot" in str(LAB._ELIOT_IMPORT_ERROR) and "eliot" in str(ESM._ELIOT_IMPORT_ERROR),
      (LAB._ELIOT_IMPORT_ERROR, ESM._ELIOT_IMPORT_ERROR))
with LAB.trace("chemistry_lab:parse_json") as a:
    pass
check("unset: tracing stays optional, the Lab carries on untraced", a is None)
os.environ["VINTOS_ELIOT_REQUIRED"] = "1"
try:
    with LAB.trace("chemistry_lab:parse_json"):
        pass
    raised = ""
except RuntimeError as exc:
    raised = str(exc)
check("required: the Lab's trace fails naming its interpreter and the original import error",
      sys.executable in raised and "VINTOS_ELIOT_REQUIRED=1" in raised and "eliot" in raised, raised)

FOLDS = []
ESM.fold = lambda body: FOLDS.append(body) or {"ok": True}
def worker(stdin='{"accession": "P69905"}'):
    out = io.StringIO(); old_in, old_out = sys.stdin, sys.stdout
    sys.stdin, sys.stdout = io.StringIO(stdin), out
    try:
        code = ESM.main()
    finally:
        sys.stdin, sys.stdout = old_in, old_out
    return code, json.loads(out.getvalue().strip().splitlines()[-1])
code, receipt = worker()
check("required, in the ESMFold worker: its normal receipt, exit 2, the interpreter named, no model run",
      code == 2 and receipt["ok"] is False and sys.executable in receipt["error"] and not FOLDS, (code, receipt, FOLDS))
os.environ.pop("VINTOS_ELIOT_REQUIRED")
code, receipt = worker()
check("unset, in the worker: the fold goes on untraced, as before", code == 0 and receipt == {"ok": True} and len(FOLDS) == 1)

print("--- a log the worker cannot open ---")
fake = types.ModuleType("eliot")
fake.to_file = lambda f: f.close()
fake.start_action = lambda **k: contextlib.nullcontext()
ESM._eliot = fake
blocked = os.path.join(HOME, "blocked"); open(blocked, "w").write("a file where the log folder should be")
ESM.ELIOT_LOG = type(ESM.ELIOT_LOG)(os.path.join(blocked, "eliot-esmfold.log"))
FOLDS.clear()
code, receipt = worker()
check("its normal receipt, exit 2, before any model is loaded", code == 2 and receipt["ok"] is False
      and "Error" in receipt["error"] and not FOLDS, (code, receipt))
src = open(os.path.join(SCRIPTS, "chemistry_esmfold.py")).read()
check("the worker's command, the fold and its receipt shape are unchanged otherwise",
      'print(json.dumps({"ok": False, "error": "%s: %s" % (type(exc).__name__, exc)})); return 2' in src)
mac = open(os.path.join(SCRIPTS, "chemistry_mac.py")).read()
check("the Lab still starts the worker the same way, with the same timeout", "subprocess.run([ESMFOLD_PYTHON, path], input=json.dumps(body), text=True," in mac
      and "timeout=900" in mac)
check("nothing reached the network", not NET, NET)
print("%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
