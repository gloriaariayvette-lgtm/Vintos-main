#!/usr/bin/env python3
"""His predicted structure checked against a real one (Grok Bot, 2026-10-06: pendrin's STAS against pig 8SGW).
A made-up model and a made-up entry stand in: the entry is the same chain numbered five higher with a loop left
out, as 8SGW is to his O43511 model. Scratch HOME; RCSB is a stub; no socket opens. The comparison runs where it
runs on Aegis (the Lab's own Python, with tmtools), or in this Python when that is where tmtools is."""
import json, math, os, socket, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="ref-compare-"); os.environ["HOME"] = HOME
WS = os.path.join(HOME, ".vintos", "workspace"); os.environ["SPARK_WORKSPACE"] = WS
NET = []
def _no(self, *a, **k): NET.append(a); raise OSError("this suite reaches nothing")
socket.socket.connect = _no
sys.path.insert(0, os.path.join(REPO, "scripts"))
import chemistry_reference_compare as C
import lab_instruments as L
R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:600]) if d and not ok else ""))
check("every path is a scratch one", str(C.ARTIFACTS).startswith(HOME) and str(L.LAB).startswith(HOME), C.ARTIFACTS)

AA = "ACDEFGHIKLMNPQRSTVWY"
SEQ = "".join(AA[(i * 7) % 20] for i in range(60))          # his model: 60 residues numbered 1..60
def ca(i): return (2.3 * math.cos(i * 1.75), 2.3 * math.sin(i * 1.75), 1.5 * i)   # a helix-like trace
THREE = {"A": "ALA", "C": "CYS", "D": "ASP", "E": "GLU", "F": "PHE", "G": "GLY", "H": "HIS", "I": "ILE", "K": "LYS",
         "L": "LEU", "M": "MET", "N": "ASN", "P": "PRO", "Q": "GLN", "R": "ARG", "S": "SER", "T": "THR", "V": "VAL",
         "W": "TRP", "Y": "TYR"}
os.makedirs(C.MODELS); os.makedirs(C.REFERENCES)
with open(os.path.join(C.MODELS, "O43511-abc123.pdb"), "w") as f:
    for i, a in enumerate(SEQ, 1):
        x, y, z = ca(i)
        f.write("ATOM  %5d  CA  %3s A%4d    %8.3f%8.3f%8.3f  1.00 90.00           C\n" % (i, THREE[a], i, x, y, z))
    f.write("END\n")
# the entry: the same residues numbered +5, residues 31-40 of the model left out (no density), and moved in space;
# written by BioPython's own mmCIF writer, then given the helix and strand loops an RCSB entry carries
_tmp = os.path.join(HOME, "entry.pdb")
with open(_tmp, "w") as f:
    for i, a in enumerate(SEQ, 1):
        if 31 <= i <= 40: continue
        x, y, z = ca(i)
        f.write("ATOM  %5d  CA  %3s A%4d    %8.3f%8.3f%8.3f  1.00 50.00           C\n" % (i, THREE[a], i + 5, x + 10, y - 4, z + 7))
    f.write("END\n")
venv = os.environ.get("VINTOS_TEST_LAB_PYTHON") or os.path.expanduser("~gloria/.vintos/tools/chemistry-lab/esmc/bin/python")
python = venv if os.path.isfile(venv) else sys.executable
subprocess.run([python, "-c", "import sys; from Bio.PDB import PDBParser, MMCIFIO; io = MMCIFIO(); "
                "io.set_structure(PDBParser(QUIET=True).get_structure('TEST', sys.argv[1])); io.save(sys.argv[2])",
                _tmp, os.path.join(C.REFERENCES, "9ZZZ.cif")], check=True, timeout=120)
CIF = open(os.path.join(C.REFERENCES, "9ZZZ.cif")).read() + (
       "loop_\n_struct_conf.conf_type_id\n_struct_conf.id\n_struct_conf.beg_auth_seq_id\n"
       "_struct_conf.end_auth_seq_id\n_struct_conf.beg_auth_asym_id\nHELX_P HELX_P1 10 25 A\nHELX_P HELX_P2 50 60 A\n"
       "#\nloop_\n_struct_sheet_range.sheet_id\n_struct_sheet_range.id\n_struct_sheet_range.beg_auth_seq_id\n"
       "_struct_sheet_range.end_auth_seq_id\n_struct_sheet_range.beg_auth_asym_id\nAA1 1 33 38 A\n#\n")
open(os.path.join(C.REFERENCES, "9ZZZ.cif"), "w").write(CIF)

# --- the request is checked before anything runs ------------------------------------------------------
for bad, why in (({"model": "O43511", "reference": "8SGW!", "ref_span": [6, 65]}, "a bad PDB id"),
                 ({"model": "O43511", "reference": "8SGW", "ref_span": [65, 6]}, "a span backwards"),
                 ({"model": "../../etc/passwd.pdb", "reference": "8SGW", "ref_span": [6, 65]}, "a model outside the Lab"),
                 ({"model": "P99999", "reference": "8SGW", "ref_span": [6, 65]}, "an accession with no model")):
    try: C.validate(bad); ok = False
    except ValueError: ok = True
    check("refused: " + why, ok)
check("an accession names its newest model", C.validate({"model": "O43511", "reference": "9zzz", "ref_span": [6, 65]})[0].name
      == "O43511-abc123.pdb")

# --- RCSB is fetched once, and only a structure is kept -----------------------------------------------
got = []
p = C.fetch_reference("1ABC", get=lambda url: (got.append(url), b"data_1ABC\nloop_\n_atom_site.id\n1\n")[1])
check("an entry is fetched from RCSB and kept", got == ["https://files.rcsb.org/download/1ABC.cif"] and p.is_file(), got)
C.fetch_reference("1ABC", get=lambda url: got.append(url))
check("and not fetched again", len(got) == 1, got)
try: C.fetch_reference("2ABC", get=lambda url: b"<html>not found</html>"); ok = False
except RuntimeError: ok = True
check("a page that is not a structure is refused", ok and not (C.REFERENCES / "2ABC.cif").exists())

# --- the comparison, where it runs on Aegis -----------------------------------------------------------
body = {"model": "O43511", "reference": "9ZZZ", "chain": "A", "ref_span": [6, 65], "offset": -5}
done = subprocess.run([python, os.path.join(REPO, "scripts", "chemistry_reference_compare.py")], input=json.dumps(body),
                      text=True, capture_output=True, timeout=300, env=dict(os.environ, no_proxy="*", http_proxy="http://0.0.0.0:9",
                      https_proxy="http://0.0.0.0:9"))
try: out = json.loads(done.stdout.strip().splitlines()[-1])
except Exception: out = {"ok": False, "error": done.stdout[-300:] + done.stderr[-300:]}
r = out.get("result") or {}
check("the comparison runs (" + python + ")", out.get("ok"), out.get("error"))
check("the left-out loop is not compared: 50 of 60 residues", r.get("compared") == 50, r.get("compared"))
check("the five-residue shift is undone by the alignment: same chain, TM-score 1", r.get("tm_fixed", [0])[0] > 0.99
      and r.get("rmsd_A", 9) < 0.01, (r.get("tm_fixed"), r.get("rmsd_A")))
check("the gap is named in his numbering", r.get("missing_in_entry") == [[31, 40]], r.get("missing_in_entry"))
els = {(e["kind"], tuple(e["protein"])): e for e in r.get("elements", [])}
check("the entry's helices and strand are given in his numbering", set(els) == {("helix", (5, 20)), ("helix", (45, 55)),
      ("strand", (28, 33))}, sorted(els))
check("a strand half in the left-out loop is compared only where both have it", els.get(("strand", (28, 33)), {}).get("compared") == 3,
      els.get(("strand", (28, 33))))
check("it says what it is not", "not_proof" in r.get("truth_status", ""))
check("the Lab's other files are untouched", sorted(os.listdir(C.REFERENCES)) == ["1ABC.cif", "9ZZZ.cif"], os.listdir(C.REFERENCES))

# --- the Lab offers it, and runs it on Aegis, not through the relay ------------------------------------
check("offered in the Lab's menu with his model", "reference_compare" in L.menu_block()
      and "artifacts/esmfold/O43511-abc123.pdb" in L.menu_block(), L.menu_block())
req = {"skill": "reference_compare", "operation": "structure.compare", "files": ["artifacts/esmfold/O43511-abc123.pdb"],
       "question": "does my STAS model match pig pendrin?", "reference": "9ZZZ", "chain": "A", "ref_span": [6, 65], "offset": -5}
import plugin_gateway
plugin_gateway.run_skill = lambda *a, **k: (_ for _ in ()).throw(AssertionError("the relay was used"))
calls = []
def fake_run(cmd, **kw):
    calls.append((cmd, json.loads(kw["input"])))
    return subprocess.CompletedProcess(cmd, 0, json.dumps({"ok": True, "result": {"reference": "9ZZZ", "display": ["line one"]}}), "")
_real = L._compare_runner
L._compare_runner = lambda q: _real(q, run=fake_run)
got = L.run(req)
check("the Lab runs it in its own Python with the model and the entry", calls and calls[0][1]["model"] ==
      "artifacts/esmfold/O43511-abc123.pdb" and calls[0][1]["ref_span"] == [6, 65] and calls[0][0][1].endswith(
      "chemistry_reference_compare.py"), calls)
check("and keeps what it found as Lab provenance", got["receipt"]["records"][0]["summary"] == "line one"
      and got["receipt"]["source"] == "instrument:reference_compare", got)
try: L.validate(dict(req, files=["artifacts/sequences/x.fasta"])); ok = False
except ValueError: ok = True
check("only an ESMFold model the Lab made is compared", ok)

check("nothing reached the network", NET == [], NET)
import shutil; shutil.rmtree(HOME, ignore_errors=True)
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
