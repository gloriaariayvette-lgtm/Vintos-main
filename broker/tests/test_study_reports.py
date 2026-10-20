#!/usr/bin/env python3
"""A Study fix is judged with the repository's generated docs brought up to date, and a try that could not apply its
edits says why (20 October, fault F-2c9a631f0e: SF-28d2b890 failed three tries; Dot read its log on Aegis: the third
failed test_p09_p11_closures.py because docs/untested.md was stale - the Study never regenerated it - and the first
two said only "the edits").

Scratch HOME, workspace and workbench; every command is a recorder or runs inside the scratch workbench; the writer,
the suite, the deploy, failure_watch and Slack are stubs; sockets are refused."""
import json, os, socket, sys, tempfile, types, subprocess
HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="study-reports-"); os.environ["HOME"] = HOME
os.environ["SPARK_WORKSPACE"] = os.path.join(HOME, "workspace")
os.environ["VINTOS_STUDY_WORKBENCH"] = os.path.join(HOME, "workbench")
NET = []
def _no(self, *a, **k): NET.append(a); raise OSError("this suite reaches nothing")
socket.socket.connect = _no
NOTED = []
sys.modules["failure_watch"] = types.SimpleNamespace(note=lambda *a, **k: NOTED.append(a))
sys.path.insert(0, os.path.join(REPO, "scripts"))
import study_fix as S
R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + ("" if ok else "  ->  %r" % (str(d)[:400],)))
WB = S.WORKBENCH
check("the workbench and the fix records are scratch, and failure_watch is a stub",
      WB.startswith(HOME) and S.QUEUE.startswith(HOME) and sys.modules["failure_watch"].note.__name__ == "<lambda>")

# A workbench whose report lists the scripts it finds, as untested_report.py --write does
os.makedirs(os.path.join(WB, "scripts")); os.makedirs(os.path.join(WB, "docs"))
open(os.path.join(WB, "CLAUDE.md"), "w").write("rules\n")
open(os.path.join(WB, "scripts", "untested_report.py"), "w").write(
    "import os, sys\nroot = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))\n"
    "names = sorted(f for f in os.listdir(os.path.join(root, 'scripts')) if f.endswith('.py'))\n"
    "open(os.path.join(root, 'docs', 'untested.md'), 'w').write('\\n'.join(names) + '\\n')\n")
open(os.path.join(WB, "scripts", "entry_owners.py"), "w").write("import sys\nsys.exit(0)\n")
open(os.path.join(WB, "docs", "untested.md"), "w").write("untested_report.py\n")          # stale once a module is added
def local(args, cwd=None, timeout=900, check=True):
    if args[0] == "git": return types.SimpleNamespace(returncode=0, stdout="", stderr="")
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=timeout)

done = S.regenerate_reports(WB, run=local)
check("the reports present are regenerated; one that is absent is passed over",
      done == ["untested_report.py", "entry_owners.py"], done)

# The fix adds a module. The suite checks docs/untested.md against the scripts, as test_p09_p11_closures does.
NEW = {"summary": "adds a helper", "edits": [],
       "new_files": [{"path": "scripts/helper.py", "content": "X = 1\n"},
                     {"path": "broker/tests/test_helper.py", "content": "import sys\nsys.exit(0)\n"}]}
seen = []
def suite(root):
    listed = open(os.path.join(root, "docs", "untested.md")).read().split()
    seen.append(listed)
    return [] if "helper.py" in listed else [("test_p09_p11_closures.py", "AssertionError: docs/untested.md is stale")]
def apply_new_files(plan, root=None):
    os.makedirs(os.path.join(WB, "broker", "tests"), exist_ok=True)
    for f in plan.get("new_files", []):
        open(os.path.join(WB, f["path"]), "w").write(f["content"])
    return [f["path"] for f in plan.get("new_files", [])]
S.apply_edits = apply_new_files
S.reset_workbench = lambda run=None: None
deployed = []
row = {"id": "SF-00000101", "what": "add a helper", "events": []}
S.work(row, ask=lambda s, u: json.dumps(NEW), run=local, post=lambda t: None, suite=suite,
       deploy=lambda run: deployed.append(1) or "...\n  rollback: bash %s/restore.sh\ndeploy OK\n" % HOME, send=lambda *a: None)
check("the suite sees docs/untested.md brought up to date with the fix's new module",
      seen and "helper.py" in seen[0], seen)
check("so the fix passes on its first try instead of failing three times on stale docs",
      len(seen) == 1 and row.get("state") != "failed" and deployed, (row.get("state"), len(seen)))

# A try whose edits cannot be applied says why, not only "the edits"
def bad_edits(plan, root=None): raise ValueError("an edit's old text is not in scripts/x.py (its first line is at line 12)")
S.apply_edits = bad_edits
row2 = {"id": "SF-00000102", "what": "change x", "events": []}
S.work(row2, ask=lambda s, u: json.dumps({"summary": "s", "edits": [{"path": "scripts/x.py", "old": "a", "new": "b"}]}),
       run=local, post=lambda t: None, suite=suite, deploy=lambda run: "DEPLOY OK", send=lambda *a: None)
log = " | ".join(str(e) for e in row2.get("events") or row2.get("log") or [])
check("a try that could not apply its edits records the reason", "old text is not in scripts/x.py" in log, log)
check("and it still ends after its tries, with nothing deployed", row2.get("state") == "failed")
check("nothing reached the network", not NET)
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
