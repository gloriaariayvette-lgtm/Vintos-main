#!/usr/bin/env python3
"""Is Eliot ready in both of the Lab's interpreters? A read-only check (2026-10-15).

The Lab runs in the OS Python (/usr/bin/python3); an ESMFold fold runs in its own commissioned interpreter
(chemistry_mac.ESMFOLD_PYTHON, ~/.vintos/tools/chemistry-lab/esmc/bin/python unless VINTOS_ESMFOLD_PYTHON says
otherwise). Each traces itself into its own log: the Lab into chemistry-lab/eliot.jsonl, the ESMFold worker into
chemistry-lab/diagnostics/eliot-esmfold.log. The two are not one cross-process task, and this does not join them.

    python3 chemistry_tracing.py readiness --lab-python /usr/bin/python3 --esmfold-python PATH

Each interpreter is run on its own and asked: can it import eliot (its version and module path), can it import the
module that traces there (chemistry_lab, chemistry_esmfold) without importing torch or transformers, and is that
module's log destination writable? Writability is checked by creating and removing a sibling file beside the log,
or, when the log already exists, by opening it for append and closing it without writing. Nothing is traced,
nothing is folded, nothing is installed. Exit 0 when both are ready, 2 when either is not.

VINTOS_ELIOT_REQUIRED=1, in the environment of the process that traces, makes a missing eliot fail at the trace
entry points (chemistry_lab.trace, chemistry_esmfold's actions) with the interpreter and the original import error.
Unset, tracing stays optional, as it was. Setting it in another shell does not change a running service.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REQUIRED_ENV = "VINTOS_ELIOT_REQUIRED"
ROLES = {"lab": ("chemistry_lab", "ELIOT_LOG"), "esmfold": ("chemistry_esmfold", "ELIOT_LOG")}
HEAVY = ("torch", "transformers")


def _writable(log):
    """(ok, how): the log's destination can be written, checked without writing a trace."""
    log = os.path.abspath(str(log))
    folder = os.path.dirname(log)
    if not os.path.isdir(folder):
        return False, "destination folder does not exist: %s" % folder
    if os.path.exists(log):
        try:
            with open(log, "ab"):
                pass
            return True, "existing log opened for append, nothing written"
        except OSError as exc:
            return False, "existing log cannot be opened for append: %s" % exc
    try:
        fd, probe = tempfile.mkstemp(prefix=".eliot-writable-", dir=folder)
        os.close(fd)
        os.unlink(probe)
        return True, "a sibling file was created and removed"
    except OSError as exc:
        return False, "destination folder is not writable: %s" % exc


def probe(role):
    """Run inside the interpreter being checked. Returns its report; prints nothing itself."""
    module_name, log_attr = ROLES[role]
    out = {"role": role, "python": sys.executable, "ok": False}
    try:
        import eliot
        out["eliot_version"] = getattr(eliot, "__version__", "unknown")
        out["eliot_path"] = getattr(eliot, "__file__", "")
    except Exception as exc:
        out["error"] = "eliot cannot be imported by %s: %s: %s" % (sys.executable, type(exc).__name__, exc)
        return out
    if HERE not in sys.path:
        sys.path.insert(0, HERE)
    try:
        module = __import__(module_name)
    except Exception as exc:
        out["error"] = "%s cannot be imported by %s: %s: %s" % (module_name, sys.executable, type(exc).__name__, exc)
        return out
    heavy = [m for m in HEAVY if m in sys.modules]
    if heavy:
        out["error"] = "importing %s loaded %s; the check must not" % (module_name, ", ".join(heavy))
        return out
    out["module"] = module_name
    log = getattr(module, log_attr, "")
    out["log"] = str(log)
    ok, how = _writable(log)
    out["log_writable"] = how
    if not ok:
        out["error"] = how
        return out
    out["ok"] = True
    return out


def check(python, role, timeout=120):
    """Ask one interpreter about itself, in a process of its own."""
    try:
        done = subprocess.run([python, "-B", os.path.abspath(__file__), "_probe", role], capture_output=True,
                              text=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"role": role, "python": python, "ok": False, "error": "could not run: %s" % exc}
    try:
        report = json.loads(done.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        return {"role": role, "python": python, "ok": False,
                "error": "no report (exit %s): %s" % (done.returncode, (done.stderr or done.stdout).strip()[-400:])}
    report["python_requested"] = python
    return report


def readiness(lab_python, esmfold_python):
    return [check(lab_python, "lab"), check(esmfold_python, "esmfold")]


def main(argv):
    if argv[:1] == ["_probe"] and len(argv) == 2 and argv[1] in ROLES:
        print(json.dumps(probe(argv[1])))
        return 0
    parser = argparse.ArgumentParser(description="Is Eliot ready in both of the Lab's interpreters? (read only)")
    sub = parser.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("readiness")
    r.add_argument("--lab-python", required=True)
    r.add_argument("--esmfold-python", required=True)
    args = parser.parse_args(argv)
    reports = readiness(args.lab_python, args.esmfold_python)
    for rep in reports:
        if rep.get("ok"):
            print("%-8s ready   %s  eliot %s (%s)\n         log %s: %s" % (
                rep["role"], rep["python"], rep.get("eliot_version"), rep.get("eliot_path"),
                rep.get("log"), rep.get("log_writable")))
        else:
            print("%-8s NOT READY  %s\n         %s" % (rep["role"], rep.get("python_requested") or rep.get("python"),
                                                  rep.get("error")))
    print("required mode (%s) in this shell: %s; it only matters in the environment of the process that traces"
          % (REQUIRED_ENV, os.environ.get(REQUIRED_ENV) == "1"))
    return 0 if all(r.get("ok") for r in reports) else 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
