#!/usr/bin/env python3
"""A method is never a spent subject (14 October). After the repair deploy, 29 of 58 refusals were "spent subject"
on proteins never asked before; the words a long unanswered run shared were tools and measures (AlphaFold, pLDDT),
so every question naming them was refused. Scratch HOME and workspace; no socket opens; no model is asked."""
import json, os, socket, sys, tempfile, time

HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="lab-spent-methods-"); os.environ["HOME"] = HOME
os.environ["SPARK_WORKSPACE"] = os.path.join(HOME, ".vintos", "workspace")
NET = []
def _no(self, *a, **k): NET.append(a); raise OSError("this suite reaches nothing")
socket.socket.connect = _no
sys.path.insert(0, os.path.join(REPO, "scripts"))
import chemistry_lab as C
R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:500]) if d and not ok else ""))
check("the spent store is a scratch one and sockets are refused", C.SPENT.startswith(HOME) and socket.socket.connect is _no)

# a long unanswered run whose questions all name the same tools, about different proteins
run = [{"kind": "inquiry", "inquiry": {"question": "Does the AlphaFold model of %s show a confident (pLDDT) STAS fold "
                                                   "in its ESMFold prediction?" % g}}
       for g in ("SLC26A4", "SLC26A5", "SLC26A6", "SLC26A9", "SLC26A11", "SLC26A2", "SLC26A3", "SLC26A1")]
d = C.dead_ends(run)
check("the run is long enough to be spent", d["count"] == len(run), d)
check("no tool or measure is made a spent subject", not {"AlphaFold", "pLDDT", "ESMFold"} & set(d["subjects"]), d["subjects"])

# a store that already holds method words from before this fix is read without them
os.makedirs(os.path.dirname(C.SPENT), exist_ok=True)
now = time.time()
json.dump({k.lower(): {"subject": k, "at": now} for k in ("AlphaFold", "pLDDT", "SLC26A4")}, open(C.SPENT, "w"))
check("method words already in the store are not read as spent", C.spent_subjects(now) == ["SLC26A4"], C.spent_subjects(now))

spent = {"subjects": ["AlphaFold", "pLDDT", "SLC26A4"]}
mbl = {"question": "What are the zinc-binding residues of the Pseudomonas metallo-beta-lactamase in its AlphaFold model "
                   "(pLDDT)?", "uniprot_query": 'protein_name:"metallo-beta-lactamase" AND organism_id:287'}
check("a new protein whose question names AlphaFold is not a spent retrieval", not C.spent_retrieval(mbl, spent))
pendrin = {"question": "What does UniProt say about SLC26A4 topology?", "uniprot_query": "gene:SLC26A4 AND organism_id:9606"}
check("a genuinely spent gene is still refused", C.spent_retrieval(pendrin, spent))
check("the refusal can name what matched", C.spent_matches(C._inquiry_text(pendrin), spent["subjects"]) == ["SLC26A4"])
src = open(os.path.join(REPO, "scripts", "chemistry_lab.py")).read()
check("the planner's refusal names the spent subject", 'already ended without an answer (%s)" % ", ".join(' in src)
check("nothing reached the network", not NET, NET)
print("%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
