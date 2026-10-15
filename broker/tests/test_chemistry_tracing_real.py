#!/usr/bin/env python3
"""Real Eliot, real emission, disposable logs (2026-10-15). Run it in an interpreter that has eliot, such as the
commissioned ESMFold venv after its prerequisites are installed:

    "$ESMFOLD_PYTHON" -B broker/tests/test_chemistry_tracing_real.py

It writes the Lab's trace and the ESMFold worker's own trace into a scratch workspace and reads them back as JSON
lines: actions, nesting, and a failure recorded as a failure. No fold, no model, no CUDA, no provider, no paid call;
torch and transformers are never imported. When eliot is not installed it says SKIP and exits 0: it then proves
nothing, so judge emission only from a run that prints its PASS lines."""
import json, os, socket, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="tracing-real-"); os.environ["HOME"] = HOME
os.environ["SPARK_WORKSPACE"] = os.path.join(HOME, ".vintos", "workspace")
os.environ.pop("VINTOS_ELIOT_REQUIRED", None)
NET = []
def _no_net(self, *a, **k):
    if self.family != socket.AF_UNIX: NET.append(a)
    raise OSError("this suite reaches nothing")
socket.socket.connect = _no_net
try:
    import eliot
except Exception as exc:
    print("SKIP: eliot is not installed in %s (%s: %s); nothing about emission was tested"
          % (sys.executable, type(exc).__name__, exc))
    sys.exit(0)
sys.path.insert(0, os.path.join(REPO, "scripts"))
import chemistry_esmfold as ESM, chemistry_lab as LAB
R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:500]) if d and not ok else ""))
check("real eliot %s in %s; logs in a scratch workspace" % (getattr(eliot, "__version__", "?"), sys.executable),
      str(ESM.ELIOT_LOG).startswith(HOME) and LAB.ELIOT_LOG.startswith(HOME))

def rows(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]

ESM._eliot_open()
with ESM._action("esmfold_job"):
    with ESM._action("parse_input"):
        pass
    try:
        with ESM._action("fold", accession="P69905", sequence_length=4):
            raise RuntimeError("a stand-in failure, not a fold")
    except RuntimeError:
        pass
got = rows(ESM.ELIOT_LOG)
job = [r for r in got if r.get("action_type") == "esmfold_job"]
kids = [r for r in got if r.get("action_type") in ("parse_input", "fold")]
check("the worker's actions are written as JSON lines", job and kids, got)
check("parse_input and fold nest under one esmfold_job task", len({r["task_uuid"] for r in job + kids}) == 1
      and all(len(r["task_level"]) > 1 for r in kids), [(r.get("action_type"), r.get("task_level")) for r in got])
check("a failure is recorded as a failure, with its reason", any(r.get("action_type") == "fold"
      and r.get("action_status") == "failed" and "stand-in failure" in str(r.get("reason")) for r in got), got)
with LAB.trace("chemistry_lab:parse_json", source="stand-in") as action:
    action.add_success_fields(keys=["a"])
lab = rows(LAB.ELIOT_LOG)
check("the Lab's parser action is written to its own log", any(r.get("action_type") == "chemistry_lab:parse_json"
      and r.get("action_status") == "succeeded" and r.get("keys") == ["a"] for r in lab), lab)
check("torch and transformers were never imported", "torch" not in sys.modules and "transformers" not in sys.modules)
check("nothing reached the network", not NET, NET)
print("%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
