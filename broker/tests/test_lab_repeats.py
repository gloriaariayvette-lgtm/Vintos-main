#!/usr/bin/env python3
"""Gemma does not repeat herself and works the frontier session's plan (Gloria, 2026-10-07: "We need Gemma to stop
making repeats. Period."). Gemma is a stub that answers in turn; scratch HOME and workspace; no socket opens."""
import json, os, socket, sys, tempfile
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="lab-repeats-"); os.environ["HOME"] = HOME
os.environ["SPARK_WORKSPACE"] = os.path.join(HOME, ".vintos", "workspace")
NET = []
def _no(self, *a, **k): NET.append(a); raise OSError("this suite reaches nothing")
socket.socket.connect = _no
sys.path.insert(0, os.path.join(REPO, "scripts"))
import lab_repeats as L
R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:500]) if d and not ok else ""))
check("its ledger and the sessions it reads are scratch ones", L.LOOKUPS.startswith(HOME) and L.SESSIONS.startswith(HOME))
NOW = datetime(2026, 10, 7, 12, 0, tzinfo=timezone.utc)

print("--- repeats ---")
atlas = {"question": "Does SLC26A4 harbor distal enhancers?", "source_query": {"source": "atlas", "gene": "SLC26A4"}}
check("an Atlas read is the same lookup whatever case the gene is written in",
      L.lookup_key(atlas) == L.lookup_key({"source_query": {"source": "atlas", "gene": "slc26a4"}}) == "atlas:SLC26A4")
L.record(atlas, now=NOW - timedelta(days=1))
check("the same Atlas gene a day later is refused, and she is told when", "2026-10-06" in L.repeat(
    {"question": "What regulatory motifs sit at the pendrin promoter?", "source_query": {"source": "atlas", "gene": "SLC26A4"}}, now=NOW))
check("another gene is not a repeat", L.repeat({"question": "What is at the GLUT4 promoter?", "source_query": {"source": "atlas", "gene": "SLC2A4"}}, now=NOW) == "")
check("a week and more later it may be read again", L.repeat(atlas, now=NOW + timedelta(days=7)) == "")
L.record({"question": "Which hydrophobic residues in TM14 of SLC26A4 form the inter-protomer interface?"}, now=NOW - timedelta(hours=2))
check("the same question in other words is refused", "in other words" in L.repeat(
    {"question": "Which TM14 hydrophobic residues of SLC26A4 form its inter-protomer interface?"}, now=NOW))
check("a different question is not", L.repeat({"question": "Where does the STAS domain of O43511 hold its strands?"}, now=NOW) == "")
L.record({"question": "x", "source_query": {"source": "pdb", "entry_id": "8SGW"}}, now=NOW, refused="repeat: test")
check("a refused cycle ran nothing, so it makes nothing a repeat", L.repeat({"question": "y", "source_query": {"source": "pdb", "entry_id": "8SGW"}}, now=NOW) == "")

print("--- the frontier session's plan ---")
os.makedirs(os.path.dirname(L.SESSIONS), exist_ok=True)
at = datetime.now(timezone.utc).isoformat()
with open(L.SESSIONS, "w") as f:
    f.write(json.dumps({"session_id": "CHEM-8a5b496f87da", "state": "completed", "lens": "claude", "at": at,
                        "plan": {"question": "Where does the STAS domain begin?", "parameters": {"target_accession": "O43511", "protein_name": "SLC26A4"}},
                        "reading": {"next_question": "What is the secondary structure of O43511 over 535-729 in the stored ESMFold model?",
                                    "keep": "the 486-534 linker"}}) + "\n")
step = L.frontier_step()
check("the latest session's next step is hers, with its subjects", step and step["session_id"] == "CHEM-8a5b496f87da"
      and {"O43511", "SLC26A4"} <= set(step["subjects"]) and step["left"] == L.FRONTIER_CYCLES, step)
check("E. coli taxonomy is not a step on it", not L.on_frontier({"question": "Where is the DRT3 locus in Escherichia coli?",
      "source_query": {"source": "ncbi", "operation": "taxonomy", "term": "Escherichia coli"}}, step))
check("reading the O43511 model is", L.on_frontier({"question": "Which residues of the STAS window are strand?",
      "instrument_query": {"skill": "fold_read", "files": ["artifacts/esmfold/O43511-abc.pdb"]}}, step))

print("--- Gemma's question step ---")
import chemistry_lab as C
answers, asked = [], []
def gemma(system, task, *a, **k):
    asked.append(task); return json.dumps(answers.pop(0))
C._ask = gemma
OFF = {"browse_lane": "genome_mining", "question": "Where is the DRT3 locus in Escherichia coli?",
       "source_query": {"source": "ncbi", "operation": "taxonomy", "term": "Escherichia coli"}}
ON = {"browse_lane": "protein", "question": "Which residues of O43511's STAS window does the model call strand?",
      "uniprot_query": "reviewed:true AND (gene:SLC26A4 AND organism_id:9606)",
      "instrument_query": {"skill": "fold_read", "operation": "structure.read", "files": ["artifacts/esmfold/O43511-abc.pdb"], "range": [535, 729]}}
answers[:] = [OFF, ON]
inq = C._orient("ctx")
check("she is shown the session's next step", "YOUR FRONTIER SESSION" in asked[0] and "535-729" in asked[0])
check("an off-plan question is sent back with the step, and the on-plan one is taken", not inq.get("refused") and
      inq.get("frontier_session") == "CHEM-8a5b496f87da" and "REFUSED: this cycle is a step" in asked[1], inq)
asked.clear(); answers[:] = [ON, ON]
inq = C._orient("ctx")
check("the same step again is a repeat: sent back once, then the cycle is refused", inq.get("refused", "").startswith("repeat")
      and "REFUSED, IT IS A REPEAT" in asked[1] and len(asked) == 2, (inq.get("refused"), len(asked)))
asked.clear(); answers[:] = [OFF, OFF]
inq = C._orient("ctx")
check("off the plan twice: refused, nothing runs", inq.get("refused", "").startswith("off the frontier") and len(asked) == 2, inq.get("refused"))
check("the week's lookups are in front of her", "LOOKUPS YOU ALREADY RAN THIS WEEK" in asked[0] and "atlas:SLC26A4" in asked[0])
check("what an Atlas record is, in her question step and her reading", "ONE fixed window" in C._atlas_text()
      and "_atlas_text() + _atlas_scorer_hint()" in open(os.path.join(REPO, "scripts", "chemistry_lab.py")).read()
      and '"instructions. " + _atlas_text()' in open(os.path.join(REPO, "scripts", "chemistry_lab.py")).read())
for _ in range(L.FRONTIER_CYCLES):
    L.record({"question": "spent"}, refused="test")
check("after %d cycles the step is done, refused ones included" % L.FRONTIER_CYCLES, L.frontier_step() is None)

check("nothing reached the network", NET == [], NET)
import shutil; shutil.rmtree(HOME, ignore_errors=True)
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
