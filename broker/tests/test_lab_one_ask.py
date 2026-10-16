#!/usr/bin/env python3
"""One question asks one thing (16 October, after 17:48 UTC: 11 of 12 reviews partial, each missing a second clause
no source could return; the one complete answer asked only what its record established). The planner is told so,
a two-part question is sent back once to narrow, and if it still asks two things its first is kept.
The planner is a stub; scratch HOME; no socket."""
import json, os, socket, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="lab-one-ask-"); os.environ["HOME"] = HOME
os.environ["SPARK_WORKSPACE"] = os.path.join(HOME, ".vintos", "workspace")
NET = []
def _no(self, *a, **k): NET.append(a); raise OSError("this suite reaches nothing")
socket.socket.connect = _no
sys.path.insert(0, os.path.join(REPO, "scripts"))
import chemistry_lab as C
R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:400]) if d and not ok else ""))
check("the Lab's stores are scratch", C.ROOT.startswith(HOME))
TODAY = {
 "What are the specific structural motifs of the human Cystatin C (CST3) inhibitor domain and the Cathepsin B (CTSB) catalytic domain, and how does the fold-specific binding facilitate its role?": "and how",
 "What are the structural hallmarks of the secretion systems used by marine Vibrio species, and do these systems exhibit conserved motifs?": "and do",
 "What are the specific amino acid residues in human HMOX1 (P09601) that coordinate the heme iron, and what is their spatial arrangement in 1N3U?": "and what",
 "What are the structural hallmarks of Vibrio secretion systems compared to terrestrial secretion systems?": "compared to"}
for q, want in TODAY.items():
    check("a second ask is found: " + want, C.second_ask(q).lower().startswith(want.split()[0]) and want.split()[-1] in C.second_ask(q).lower(), C.second_ask(q))
    check("and cut away, the first ask kept whole: " + want, C.first_ask(q).endswith("?") and want not in C.first_ask(q).lower(), C.first_ask(q))
for q in ("What does the curated UniProt record for Rhodopsin (P08100) establish about its organism, sequence length, annotated domains, and membrane topology?",
          "Which residues of human HMOX1 coordinate the heme iron in 1N3U?",
          "What metal sites and ligand contacts does PDB entry 1N3U contain?"):
    check("one ask is left as it is: " + q[:40], C.second_ask(q) == "" and C.first_ask(q) == q)
check("the planner is told to ask one thing its sources answer whole",
      "Ask ONE thing its sources can answer whole" in open(os.path.join(REPO, "scripts", "chemistry_lab.py")).read())
src = open(os.path.join(REPO, "scripts", "chemistry_lab.py")).read()
block = src[src.index("    value = _plan(system, task)\n    try:\n        _already_held"):][:1800]
check("a two-part choice is sent back once, named, and kept to its first ask if it comes back two-part again",
      "REFUSED, TWO QUESTIONS IN ONE" in block and "first_ask(narrowed.get" in block and "question_narrowed" in block)
check("a question already held keeps its words, so its hold still knows it",
      "_already_held = bool(_held_question(" in src and "and not _already_held" in block)
check("nothing reached the network", not NET)
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
