#!/usr/bin/env python3
"""A long protein's embedding covers the whole chain (Gloria, 2026-10-07: pendrin's stopped at residue 350 of 780,
so its STAS domain was never in it). ESM-C is a stub whose vector for a residue depends only on its letter, so the
pooled vector says which residues were read. Runs in the Lab's own Python (numpy), as the adapter does on Aegis.
Scratch workspace; nothing is downloaded."""
import json, os, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="esmc-windows-")
venv = os.path.expanduser("~gloria/.vintos/tools/chemistry-lab/esmc/bin/python")
python = venv if os.path.isfile(venv) else sys.executable
R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:500]) if d and not ok else ""))

RUN = r'''
import sys, types, json, contextlib, io
import numpy as np
calls = []
class FT:
    def __init__(self, a): self.a = a
    def __getitem__(self, i): return FT(self.a[i])
    def float(self): return self
    def cpu(self): return self
    def numpy(self): return self.a
class Model:
    def to(self, d): return self
    def eval(self): return self
    def encode(self, p): calls.append(len(p.sequence)); return p
    def logits(self, p, cfg):
        rows = [[1.0, 0.0] if c == "A" else [0.0, 1.0] for c in p.sequence]
        return types.SimpleNamespace(embeddings=FT(np.array([[[0.0, 0.0]] + rows + [[0.0, 0.0]]])))
sys.modules["torch"] = types.SimpleNamespace(cuda=types.SimpleNamespace(is_available=lambda: False),
    backends=types.SimpleNamespace(mps=types.SimpleNamespace(is_available=lambda: False)), inference_mode=contextlib.nullcontext)
sys.modules["esm"] = types.ModuleType("esm"); sys.modules["esm.models"] = types.ModuleType("esm.models")
sys.modules["esm.models.esmc"] = types.SimpleNamespace(ESMC=types.SimpleNamespace(from_pretrained=lambda m: Model()))
sys.modules["esm.sdk"] = types.ModuleType("esm.sdk")
sys.modules["esm.sdk.api"] = types.SimpleNamespace(ESMProtein=lambda sequence: types.SimpleNamespace(sequence=sequence),
                                                   LogitsConfig=lambda **k: None)
sys.path.insert(0, sys.argv[1])
import chemistry_esmc as C
seqs = [{"accession": "O43511", "sequence": "A" * 400 + "C" * 380}, {"accession": "SHORT1", "sequence": "A" * 100 + "C" * 100}]
sys.stdin = io.StringIO(json.dumps({"records": seqs})); out = io.StringIO(); sys.stdout = out
C.main(); sys.stdout = sys.__stdout__
res = json.loads(out.getvalue())
vecs = [np.load(C.WS / e["artifact"]).tolist() for e in res["embeddings"]]
print(json.dumps({"res": res, "vecs": vecs, "calls": calls, "windows": C.windows(780), "ws": str(C.WS)}))
'''
done = subprocess.run([python, "-c", RUN, os.path.join(REPO, "scripts")], capture_output=True, text=True, timeout=120,
                      env=dict(os.environ, SPARK_WORKSPACE=os.path.join(HOME, "ws"), HOME=HOME))
try:
    got = json.loads(done.stdout.strip().splitlines()[-1])
except Exception:
    got = {}
    print(done.stdout[-500:], done.stderr[-1500:])
check("the adapter writes only in the scratch workspace", got.get("ws", "").startswith(HOME), got.get("ws"))
e = (got.get("res") or {}).get("embeddings") or [{}, {}]
v = got.get("vecs") or [[0, 0], [0, 0]]
check("a 780-residue protein is read whole: the vector is 400/780 A, not all A",
      abs(v[0][0] - 400 / 780) < 1e-4 and e[0].get("sequence_length") == 780, (v[0], e[0]))
check("in windows no longer than before (350), overlapping, covering 1-780", got.get("windows") == [[0, 350], [300, 650], [430, 780]]
      and max(got.get("calls") or [999]) <= 350 and e[0].get("windows") == [[1, 350], [301, 650], [431, 780]], (got.get("windows"), got.get("calls")))
check("a protein of 350 or fewer is read in one pass as before", abs(v[1][0] - 0.5) < 1e-6 and e[1].get("windows") == [[1, 200]], e[1])
import shutil; shutil.rmtree(HOME, ignore_errors=True)
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
