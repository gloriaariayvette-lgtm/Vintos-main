#!/usr/bin/env python3
"""What the Lab may ask the Forge to build (Gloria, 2026-10-08: "We need to improve what the Forge is suggesting").
The four Forge projects open on 7 October, by their own titles: three she cancelled, one she kept. Scratch
workspace; no model is asked and nothing reaches the network or the Forge."""
import importlib.util, os, socket, sys, tempfile, types

HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="forge-gaps-"); os.environ["HOME"] = HOME
WS = os.path.join(HOME, ".vintos", "workspace"); os.makedirs(os.path.join(WS, "memory")); os.environ["SPARK_WORKSPACE"] = WS
NET = []
def _no(self, *a, **k): NET.append(a); raise OSError("this suite reaches nothing")
socket.socket.connect = _no
sys.path.insert(0, os.path.join(REPO, "scripts"))
import forge_gaps as G
spec = importlib.util.spec_from_file_location("chemistry_lab", os.path.join(REPO, "scripts", "chemistry_lab.py"))
L = importlib.util.module_from_spec(spec); sys.modules["chemistry_lab"] = L; spec.loader.exec_module(L)
R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:400]) if d and not ok else ""))
check("the Lab's stores are scratch ones", L.GAPS.startswith(HOME), L.GAPS)

ATLAS = "A regulatory genomics database containing the specific Atlas ATAC-seq and AVI_SCORE fields for the SLC26A4 window"
MD = "A molecular dynamics (MD) simulator capable of calculating the free energy profile of water and ions through the pore"
H723R = "A high-resolution transcript-specific mapping tool to correlate the p.H723R mutation to a specific SLC26A4 transcript"
NCBI = "A sequence retrieval tool for the NCBI Protein database or a specialized phage database is required"
v = G.judge(ATLAS, "what does Atlas say about SLC26A4")
check("Atlas 'AVI_SCORE fields': a misreading of his own source, not sent", not v["send"] and v["kind"] == "own_source"
      and "Atlas" in v["why"], v)
v = G.judge(NCBI, "find a phage protein")
check("NCBI protein / phage retrieval: he already has it, not sent", not v["send"] and v["kind"] == "already_have"
      and "NCBI" in v["why"], v)
v = G.judge(MD, "how does water move through pendrin")
check("a molecular dynamics simulator from one question: large, kept for Gloria to ask for", not v["send"] and v["kind"] == "large", v)
v = G.judge(H723R, "where does H723R sit in pendrin's STAS")
check("the p.H723R transcript mapping (the one she kept): specific, on his work, sent", v["send"], v)
check("a gap that names nothing to run on is vague", G.judge("a better tool for proteins in general", "something interesting")["kind"] == "vague")
v = G.judge("A docking-free binding predictor for H723R pendrin against bicarbonate",
            "H723R", declined=["Missing Lab instrument: A binding predictor for pendrin H723R against bicarbonate"])
check("one like a project she cancelled is not sent again", not v["send"] and v["kind"] == "declined", v)
check("secondary structure is not claimed as had (PyDSSP is still owed; fold_read is not DSSP)",
      G.have("DSSP secondary structure assignment for my O43511 model") == "")

L._keep_gap_verdict(MD, G.judge(MD, "q"))
txt = L._gap_text()
check("his next reflection is told what the Lab has, and why his last gap was kept", "THIS LAB ALREADY HAS" in txt
      and "NCBI" in txt and "Atlas" in txt and "molecular dynamics" in txt and "large build" in txt, txt[:600])
src = open(os.path.join(REPO, "scripts", "chemistry_lab.py")).read()
check("the Lab asks forge_gaps before offering a report", "forge_gaps.judge(" in src and 'verdict["send"] and receipts' in src)
check("forge_gaps is in the deploy manifest", "forge_gaps.py" in open(os.path.join(REPO, "scripts", "deploy-atelier.sh")).read())
check("nothing reached the network", not NET, NET)
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
