#!/usr/bin/env python3
"""The ESMFold script traces itself: one eliot task "esmfold_job" with "parse_input" and "fold" nested under it,
so eliot-tree can print a fold as one tree (Vintos, 2026-10-08: tracing chemistry_mac and the Lab's parser spanned
two processes and never nested).

Eliot, torch and transformers are faked in memory: no model, no CUDA, no real log destination, no network.
Scratch HOME and SPARK_WORKSPACE, so the artifact store and the eliot file land in a throwaway folder."""
import io, json, os, shutil, socket, sys, tempfile, types, uuid
HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="esmfold-eliot-"); os.environ["HOME"] = HOME
os.environ["SPARK_WORKSPACE"] = os.path.join(HOME, ".vintos", "workspace")
os.environ["VINTOS_CHEMISTRY_MODEL_CACHE"] = os.path.join(HOME, "model-cache")
sys.path.insert(0, os.path.join(REPO, "scripts"))

NET = []
def _no_net(self, *a, **k):
    if self.family != socket.AF_UNIX: NET.append(a)
    raise OSError("this suite reaches nothing")
socket.socket.connect = _no_net

# --- a fake eliot: records actions with their parent, nests task_uuid like the real one, writes nowhere --------
LOG, FILES = [], []
class Action:
    _stack = []
    def __init__(self, action_type, task_uuid, fields, parent):
        self.action_type, self.task_uuid, self.fields, self.parent = action_type, task_uuid, fields, parent
    def __enter__(self): Action._stack.append(self); LOG.append(self); return self
    def __exit__(self, *exc): Action._stack.pop(); return False
def start_action(action_type=None, **fields):
    parent = Action._stack[-1] if Action._stack else None
    return Action(action_type, parent.task_uuid if parent else uuid.uuid4().hex, fields, parent)
def to_file(f): FILES.append(f.name); f.close()
fake = types.ModuleType("eliot")
fake.Action, fake.start_action, fake.to_file = Action, start_action, to_file
sys.modules["eliot"] = fake

# --- a fake torch and transformers: no CUDA, no model weights, one canned PDB ----------------------------------
PDB = "ATOM      1  CA  MET A   1       0.000   0.000   0.000  1.00 90.00           C\nEND\n"
class _NoGrad:
    def __enter__(self): return self
    def __exit__(self, *exc): return False
torch = types.ModuleType("torch")
torch.cuda = types.SimpleNamespace(is_available=lambda: True)
torch.no_grad = _NoGrad
sys.modules["torch"] = torch
class _Tensor:
    def cuda(self): return self
    def mean(self): return self
    def cpu(self): return 0.9
class _Tokenizer:
    @classmethod
    def from_pretrained(cls, *a, **k): return cls()
    def __call__(self, *a, **k): return {"input_ids": _Tensor()}
class _Model:
    @classmethod
    def from_pretrained(cls, *a, **k): return cls()
    def __init__(self):
        self.esm = types.SimpleNamespace(half=lambda: None)
        self.trunk = types.SimpleNamespace(set_chunk_size=lambda n: None)
    def cuda(self): return self
    def eval(self): return self
    def __call__(self, inputs): return types.SimpleNamespace(plddt=_Tensor())
    def output_to_pdb(self, output): return [PDB]
transformers = types.ModuleType("transformers")
transformers.AutoTokenizer, transformers.EsmForProteinFolding = _Tokenizer, _Model
sys.modules["transformers"] = transformers

import chemistry_esmfold as E

R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:300]) if d and not ok else ""))

check("every path the script writes points at scratch",
      str(E.ARTIFACTS).startswith(HOME) and str(E.ELIOT_LOG).startswith(HOME), (E.ARTIFACTS, E.ELIOT_LOG))
check("eliot, torch and transformers are the fakes",
      E._eliot is fake and sys.modules["torch"] is torch and sys.modules["transformers"] is transformers)
check("the eliot file goes below the Lab's diagnostics folder",
      E.ELIOT_LOG.name == "eliot-esmfold.log" and E.ELIOT_LOG.parent.name == "diagnostics", E.ELIOT_LOG)

seq = "MKVLA"
req = {"accession": "P02794", "sequence": seq, "sequence_source": {"accession": "P02794"},
       "hp_mapping": [{"residue": c} for c in seq]}
real_in, real_out = sys.stdin, sys.stdout
sys.stdin, sys.stdout = io.StringIO(json.dumps(req)), io.StringIO()
try:
    code = E.main()
    printed = sys.stdout.getvalue()
finally:
    sys.stdin, sys.stdout = real_in, real_out

receipt = json.loads(printed.strip().splitlines()[-1]) if printed.strip() else {}
check("the fake fold ran through main and answered a receipt", code == 0 and receipt.get("ok") is True, (code, printed))
check("the log destination was opened once, in scratch", FILES == [str(E.ELIOT_LOG)], FILES)
types_seen = [a.action_type for a in LOG]
check("one job, then parse_input, then fold", types_seen == ["esmfold_job", "parse_input", "fold"], types_seen)
job = [a for a in LOG if a.action_type == "esmfold_job"]
children = [a for a in LOG if a.action_type in ("parse_input", "fold")]
check("the job has no parent; both children nest directly under it",
      len(job) == 1 and job[0].parent is None and all(a.parent is job[0] for a in children), [(a.action_type, a.parent) for a in LOG])
check("one task_uuid holds the whole tree", len({a.task_uuid for a in LOG}) == 1, [(a.action_type, a.task_uuid) for a in LOG])
fold = [a for a in LOG if a.action_type == "fold"]
check("the fold action names the accession and the length",
      fold and fold[0].fields.get("accession") == "P02794" and fold[0].fields.get("sequence_length") == 5, fold and fold[0].fields)
check("the PDB landed in the scratch artifact store",
      str(E.ARTIFACTS).startswith(HOME) and any(p.suffix == ".pdb" for p in E.ARTIFACTS.iterdir()), list(E.ARTIFACTS.iterdir()))
check("nothing left the machine", not NET, NET)
shutil.rmtree(HOME, ignore_errors=True)
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
