#!/usr/bin/env python3
"""The Lab's parser and the ESMFold invoke each run under an eliot action, the parser nested under the latest fold,
so one task_uuid holds both and eliot-tree can print a run (Vintos, 2026-10-08).

Eliot itself is faked in memory: no real log destination, no real fold (subprocess is a stub), no network. Scratch
HOME and SPARK_WORKSPACE, so the Lab's eliot file lands in a throwaway folder."""
import os, shutil, socket, sys, tempfile, types, uuid
HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="lab-eliot-"); os.environ["HOME"] = HOME
os.environ["SPARK_WORKSPACE"] = os.path.join(HOME, ".vintos", "workspace")
sys.path.insert(0, os.path.join(REPO, "scripts"))

NET = []
def _no_net(self, *a, **k):
    if self.family != socket.AF_UNIX: NET.append(a)
    raise OSError("this suite reaches nothing")
socket.socket.connect = _no_net

# --- a fake eliot: records actions, nests task_uuid like the real one, never writes anywhere ----------------
LOG, FILES = [], []
class Action:
    _stack = []
    def __init__(self, action_type, task_uuid, fields):
        self.action_type, self.task_uuid, self.fields, self.success = action_type, task_uuid, fields, {}
    def __enter__(self): Action._stack.append(self); LOG.append(self); return self
    def __exit__(self, *exc): Action._stack.pop(); return False
    def serialize_task_id(self): return (self.task_uuid + "@/1").encode()
    def add_success_fields(self, **f): self.success.update(f)
    @classmethod
    def continue_task(cls, task_id=None): return cls("continued", task_id.decode().split("@")[0], {})
def start_action(action_type=None, **fields):
    parent = Action._stack[-1] if Action._stack else None
    return Action(action_type, parent.task_uuid if parent else uuid.uuid4().hex, fields)
def current_action(): return Action._stack[-1] if Action._stack else None
def to_file(f): FILES.append(f.name); f.close()
fake = types.ModuleType("eliot")
fake.Action, fake.start_action, fake.current_action, fake.to_file = Action, start_action, current_action, to_file
sys.modules["eliot"] = fake

import chemistry_lab as LAB
import chemistry_mac as M

R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:300]) if d and not ok else ""))

check("the Lab writes only in the scratch workspace", LAB.ROOT.startswith(HOME) and LAB.ELIOT_LOG.startswith(HOME), LAB.ROOT)
check("eliot is the fake", LAB._eliot is fake)

# a parse before any fold is its own task
LAB._json_object('{"a": 1}')
alone = [a for a in LOG if a.action_type == "chemistry_lab:json_object"]
check("the parser runs under an eliot action", len(alone) == 1 and alone[0].success.get("keys") == ["a"], LOG)
check("the log goes below the Lab's own folder", FILES and FILES[0] == LAB.ELIOT_LOG, FILES)

# a fold: the real subprocess is replaced by a stub that answers at once
CALLS = []
real_run = M.subprocess.run
def stub(*a, **k):
    CALLS.append(a); return types.SimpleNamespace(returncode=0, stdout='{"ok": false, "error": "stub"}', stderr="")
M.subprocess.run = stub
try:
    out = M._run_esmfold({}, {"requested_accession": "P02794", "sequence": "M" * 40, "source": {}, "hp_mapping": []})
finally:
    M.subprocess.run = real_run
check("the fold ran the stub, not ESMFold", len(CALLS) == 1 and out.get("error") == "stub", out)
folds = [a for a in LOG if a.action_type == "chemistry_mac:esmfold"]
check("the ESMFold invoke runs under an eliot action naming the accession",
      len(folds) == 1 and folds[0].fields.get("accession") == "P02794" and folds[0].success.get("exit_code") == 0, LOG)

# the parse that reads the fold nests under the fold's task
LAB._json_object('{"reading": "x"}')
parses = [a for a in LOG if a.action_type == "chemistry_lab:json_object"]
check("parser after the fold shares the fold's task_uuid", len(parses) == 2 and folds and parses[1].task_uuid == folds[0].task_uuid,
      [(a.action_type, a.task_uuid) for a in LOG])
check("parser before the fold did not", parses[0].task_uuid != folds[0].task_uuid)
check("nothing left the machine", not NET, NET)
shutil.rmtree(HOME, ignore_errors=True)
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
