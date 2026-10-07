#!/usr/bin/env python3
"""What is in one of his ESMFold models reaches him (Gloria, 2026-10-07): confidence per residue and helix/strand
from the model's own coordinates; the result shown to his reading leads with it and names the settings ESMFold
ignored; a plan's lattice settings are set aside. A made-up model stands in (a helix, a two-strand hairpin and a
loose loop); torch and the folding model are stubs. Scratch HOME; no socket opens."""
import json, math, os, socket, subprocess, sys, tempfile, types

HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="fold-read-"); os.environ["HOME"] = HOME
WS = os.path.join(HOME, ".vintos", "workspace"); os.environ["SPARK_WORKSPACE"] = WS
NET = []
def _no(self, *a, **k): NET.append(a); raise OSError("this suite reaches nothing")
socket.socket.connect = _no
sys.path.insert(0, os.path.join(REPO, "scripts"))
import chemistry_fold_read as F
R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:500]) if d and not ok else ""))

# 1-15 helix, 16-23 strand, 24-25 turn, 26-33 strand back, 34-38 loose loop
CA = [(2.3 * math.cos(math.radians(100 * i)), 2.3 * math.sin(math.radians(100 * i)), 1.5 * i) for i in range(15)]
CA += [(30 + 3.3 * i, 0.9 if i % 2 else -0.9, 0) for i in range(8)] + [(30 + 3.3 * 7 + 3.0, 1.2, 0), (30 + 3.3 * 7 + 3.0, 3.6, 0)]
CA += [(30 + 3.3 * (7 - j), 4.8 + (0.9 if (7 - j) % 2 else -0.9), 0) for j in range(8)]
CA += [(80 + 3.8 * i, 20 + 3 * i, 5 * i) for i in range(5)]
CONF = [0.95] * 15 + [0.8] * 18 + [0.3] * 5                     # ESMFold's 0..1 scale
def pdb(ca, conf, first=1):
    return "".join("ATOM  %5d  CA  ALA A%4d    %8.3f%8.3f%8.3f  1.00%6.2f           C\n" % (i + 1, first + i, x, y, z, b)
                   for i, ((x, y, z), b) in enumerate(zip(ca, conf))) + "END\n"
TEXT = pdb(CA, CONF)

read = F.read_pdb(TEXT)
check("helix, both strands and the loose loop are called from the coordinates", read["ss"] ==
      "H" * 15 + "E" * 8 + "--" + "E" * 8 + "-" * 5, read["ss"])
s = F.summary(read)
check("as ranges in the protein's numbering", s["helices"] == [[1, 15]] and s["strands"] == [[16, 23], [26, 33]], s)
check("confidence per residue, on the 0-100 scale", s["plddt_by_residue"][0] == 95.0 and s["plddt_by_residue"][-1] == 30.0)
check("and as bands", [b[0] for b in s["confidence_bands"]] == ["very high", "confident", "very low"], s["confidence_bands"])
w = F.summary(F.read_pdb(pdb(CA, CONF, first=535)), 550, 560)
check("a range he names, in his numbering", w["range"] == [550, 560] and w["helices"] == []
      and w["strands"] == [[550, 557], [560, 560]], w)
check("it says what it is", "not DSSP" in s["method"])

print("\n--- an ESMFold run carries it (torch and the model are stubs) ---")
class T:
    def __init__(self, v): self.v = v
    def mean(self): return T(sum(CONF) / len(CONF))
    def cpu(self): return self
    def __float__(self): return float(self.v)
    def half(self): return self
    def cuda(self): return self
class Model:
    esm = T(0); trunk = types.SimpleNamespace(set_chunk_size=lambda n: None)
    def cuda(self): return self
    def eval(self): return self
    def __call__(self, x): return types.SimpleNamespace(plddt=T(0))
    def output_to_pdb(self, out): return [TEXT]
import contextlib
sys.modules["torch"] = types.SimpleNamespace(cuda=types.SimpleNamespace(is_available=lambda: True), no_grad=contextlib.nullcontext)
sys.modules["transformers"] = types.SimpleNamespace(
    AutoTokenizer=types.SimpleNamespace(from_pretrained=lambda *a, **k: (lambda seqs, **kw: {"input_ids": T(0)})),
    EsmForProteinFolding=types.SimpleNamespace(from_pretrained=lambda *a, **k: Model()))
import chemistry_esmfold as E
SEQ = "A" * len(CA)
out = E.fold({"accession": "P99999", "sequence": SEQ, "sequence_source": {"accession": "P99999"},
              "hp_mapping": [{"position": i + 1, "residue": "A", "hp": "H"} for i in range(len(SEQ))]})["result"]
sr = out.get("structure_read") or {}
check("the fold result holds the model's helix and strand ranges and its confidence bands",
      sr.get("helices") == [[1, 15]] and sr.get("strands") == [[16, 23], [26, 33]] and sr.get("confidence_bands"), sr)
check("and says them in its display", any("helices: 1-15" in l for l in out["display"]), out["display"])
check("the model file is in the scratch Lab", out["structure_artifact"].startswith("memory/chemistry-lab/artifacts/esmfold/"))

print("\n--- what his reading sees ---")
import chemistry_session as S
LONG = "M" * 780
result = {"ok": True, "run_id": "ESMFOLD-x", "sequence_check": {"outcome": "SEQUENCE_ACCESSION_MATCH", "modeled_sequence": LONG},
          "sequence_request": {"sequence": LONG, "hp_mapping": [{"hp": "H"}] * 780},
          "run": {"parameters": {"target_accession": "O43511", "ignored_parameters": ["chain_stiffness", "hydrophobic_pull"]},
                  "result": {"title": "Folding O43511 (780 aa): " + LONG, "requested_accession": "O43511", "modeled_sequence": LONG,
                             "real_sequence": LONG, "hp_mapping": [{"position": i, "residue": "M", "hp": "H" if i % 2 else "P"} for i in range(780)],
                             "mean_plddt": 81.2, "structure_read": dict(sr, plddt_by_residue=[80.0] * 780), "backend": "facebook/esmfold_v1"}}}
v = json.dumps(S._result_view(result))
check("a 780-residue result fits whole inside what the reading is shown", len(v) < 12000 and v.count(LONG) == 1, len(v))
check("it leads with what the model holds, and the mean pLDDT is there", '"structure_read"' in v and "81.2" in v)
check("the HP labels are counted and said to come from the sequence, not the fold", "from the SEQUENCE alone" in v and '"position"' not in v)
check("the settings ESMFold ignored are named as changing nothing", "chain_stiffness, hydrophobic_pull" in v and "changed nothing" in v)
check("a result of another shape is shown as it was", S._result_view({"ok": True, "points": [1]}) == {"ok": True, "points": [1]})

print("\n--- a plan's lattice settings are set aside for ESMFold ---")
import chemistry_mac as M
record = {"primaryAccession": "O43511", "sequence": {"value": LONG, "length": 780}, "genes": [{"geneName": {"value": "SLC26A4"}}]}
prep = M.prepare_protein({"target_accession": "O43511", "protein_name": "SLC26A4", "chain_stiffness": 0.7, "hydrophobic_pull": 0.6},
                         resolver=lambda acc: (record, {"provider": "UniProtKB", "accession": acc, "receipt_id": "r"}))
p = prep.get("parameters") or {}
check("they are not passed to the fold, and are named", prep.get("ok") and "chain_stiffness" not in p
      and p.get("ignored_parameters") == ["chain_stiffness", "hydrophobic_pull"] and p.get("protein_backend") == "esmfold", prep)

print("\n--- the Lab can read a model it already has ---")
import lab_instruments as L
os.makedirs(os.path.join(L.LAB, "artifacts", "esmfold"), exist_ok=True)
open(os.path.join(L.LAB, "artifacts", "esmfold", "O43511-abc.pdb"), "w").write(pdb(CA, CONF, first=535))
check("offered in the menu", "fold_read" in L.menu_block() and "artifacts/esmfold/O43511-abc.pdb" in L.menu_block(), L.menu_block())
got = L.run({"skill": "fold_read", "operation": "structure.read", "files": ["artifacts/esmfold/O43511-abc.pdb"],
             "question": "which residues of the STAS window are strand?", "range": [535, 560]})
summary = got["receipt"]["records"][0]["summary"]
check("run on Aegis in the Lab's own Python, over the range he named", "residues 535-560" in summary and "helices: 535-549" in summary, summary)

check("nothing reached the network", NET == [], NET)
import shutil; shutil.rmtree(HOME, ignore_errors=True)
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
