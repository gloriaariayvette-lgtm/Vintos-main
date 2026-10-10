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
# Identity resolution is independently exercised in test_lab_gene_grounding.
def identity_stub(inquiry): return {"status": "verified", "receipt_ids": ["fixture"]}
C._ground_inquiry = identity_stub
check("identity resolution is isolated", C._ground_inquiry is identity_stub)
answers, asked, systems = [], [], []
def gemma(system, task, *a, **k):
    systems.append(system); asked.append(task); return json.dumps(answers.pop(0))
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

# Regression: 8 October's invisible 35-minute gap contained 82 refused Atlas inquiries.
refused = [{"kind": "inquiry_refused", "question": "Which regulatory features of SLC26A4 can Atlas show?",
            "why": "repeat: atlas:SLC26A4"} for _ in range(82)]
spent = C.dead_ends([{"kind": "reflection"}] + refused)
check("refused questions count toward exhausted-thread recovery", spent["count"] == 82 and "SLC26A4" in spent["subjects"], spent)
cfg = C.config(); C._atomic(C.CONFIG, dict(cfg, alphagenome_key_file=os.path.join(HOME, "fake-key")))
attempt = {"kind": "inquiry_refused", "atlas_turn": True, "inquiry": atlas}
check("a refused scheduled Atlas opportunity yields instead of pinning every pass",
      not C.atlas_turn_due([{"kind": "inquiry", "inquiry": {}}, {"kind": "inquiry", "inquiry": {}}, attempt]))
check("Atlas returns after two further accepted questions",
      C.atlas_turn_due([attempt, {"kind": "inquiry", "inquiry": {}}, {"kind": "inquiry", "inquiry": {}}]))
C._atomic(C.CONFIG, dict(cfg, alphagenome_key_file=None))
with open(C.NOTEBOOK, "w") as f:
    for row in [{"kind": "reflection"}] + refused: f.write(json.dumps(row) + "\n")
asked.clear(); answers[:] = [{"browse_lane": "microbiology", "question": "Which reviewed Bacillus subtilis catalase annotations are available?",
                             "source_query": {"source": "ncbi", "operation": "protein", "term": "Bacillus subtilis catalase"}}]
recovered = C._orient("ctx")
check("replayed refusal streak reaches the next planning prompt and accepts another subject",
      not recovered.get("refused") and "LAST 82 QUESTIONS" in asked[0] and "SPENT FOR TODAY" in asked[0]
      and "SLC26A4" in asked[0], recovered)
# Replay 9 October: the second choice rationalized revisiting the spent
# SLC26A10 question. Even the final repair must pass before a line is opened.
spent_query = {"browse_lane": "protein", "question": "What is the primary sequence and domain architecture of human SLC26A10?",
               "uniprot_query": "protein_name:SLC26A10 AND organism_id:9606 AND reviewed:true",
               "new_line": {"title": "again", "question": "What is the primary sequence of human SLC26A10?"}}
C.remember_spent(["SLC26A10"])
asked.clear(); answers[:] = [spent_query, spent_query, spent_query]
blocked = C._orient("ctx")
check("spent subject cannot escape through the second or final planner choice",
      "spent subject" in blocked.get("refused", "") and not blocked.get("line_opened"), blocked)
check("refused planning recorded no lookup", L._tail(L.LOOKUPS)[-1]["lookup"] == "")
# A genuine alternative selected on the last repair is admitted instead.
asked.clear(); answers[:] = [spent_query, spent_query, {
    "browse_lane": "microbiology", "question": "Which bacterial heme oxygenase annotations are documented?",
    "source_query": {"source": "ncbi", "operation": "protein", "term": "bacterial heme oxygenase"}}]
fresh = C._orient("ctx")
check("final repair can advance a different question", not fresh.get("refused") and "heme oxygenase" in fresh["question"], fresh)
# A new instrument measurement on that protein is allowed, but cannot run twice.
measurement = dict(spent_query, new_line=None, instrument_query={"skill": "fold_read", "operation": "structure.read",
                    "files": ["artifacts/esmfold/SLC26A10-model.pdb"], "range": [406, 541]})
asked.clear(); answers[:] = [measurement]
measured = C._orient("ctx")
check("spent retrieval does not ban a new instrument measurement", not measured.get("refused") and len(asked) == 1, measured)
answers[:] = [measurement]
again, _ = C._held_to_plan("system", "task", C._inquiry(measurement), measurement, None, None, L,
                          spent={"subjects": ["SLC26A10"]})
check("the instrument measurement itself remains deduplicated", again.get("refused", "").startswith("repeat"), again)

# A sourced structural/sequence read is a new test, not another name search.
structure = dict(spent_query, new_line=None, source_query={"source": "pdb", "entry_id": "8ABC"})
answers[:] = []
structure_read, _ = C._held_to_plan("system", "task", C._inquiry(structure), structure, None, None, L,
                                  spent={"subjects": ["SLC26A10"]})
check("new sourced structure read remains eligible on a spent subject", not structure_read.get("refused"), structure_read)
answers[:] = [structure]
structure_again, _ = C._held_to_plan("system", "task", C._inquiry(structure), structure, None, None, L,
                                   spent={"subjects": ["SLC26A10"]})
check("same structure cannot be reread to evade the guard", structure_again.get("refused", "").startswith("repeat"), structure_again)

# Same exact human query, differently spelled or routed, cannot bypass the ledger.
a = "protein_name:SLC26A10 AND organism_id:9606 AND reviewed:true"
b = "reviewed:true AND taxonomy_id:9606 AND protein_name:SLC26A10"
check("human taxonomy filter aliases share a repeat key", L.uniprot_key(a) == L.uniprot_key(b))
check("older serialized alias keys are canonicalized on read", L.canonical_lookup(
    'uniprot:[["organism_id","9606"],["protein_name","slc26a10"],["reviewed","true"]]') == L.uniprot_key(b))
check("plugin-shaped current UniProt requests use the same direct repeat key", L.lookup_key({
    "question": "human SLC26A10", "plugin_query": {"plugin": "uniprot", "tool": "uniprot_query",
    "arguments": {"query": a}}}) == L.uniprot_key(b))
check("higher taxon organism and taxonomy filters stay distinct", L.uniprot_key("organism_id:2") != L.uniprot_key("taxonomy_id:2"))
check("reviewed and unreviewed searches stay distinct", L.uniprot_key(a) != L.uniprot_key(a.replace("true", "false")))
check("OR retains its meaning", L.uniprot_key("gene:A OR gene:B") != L.uniprot_key("gene:A AND gene:B"))
# Legacy failed connector attempts must not block the first working direct read.
legacy = 'plugin_query:{"arguments":{"query":"gene:FRESH1"},"plugin":"uniprot","tool":"uniprot_query"}'
check("legacy connector attempts are not claimed as completed direct reads", L.canonical_lookup(legacy) == legacy)
L.record({"question": "Which conserved motifs define the VgrG Hcp needle interface in Vibrio species?",
          "source_query": {"source": "ncbi", "operation": "literature", "term": "Vibrio VgrG Hcp interface"}})
check("switching literature API cannot recycle the same question", bool(L.repeat({
    "question": "Which conserved motifs define the VgrG Hcp needle interface across Vibrio species?",
    "source_query": {"source": "pubmed", "term": "Vibrio VgrG Hcp motifs"}})))
C.remember_spent(["timer-test"], now=100000)
C.remember_spent(["timer-test"], now=100100)
check("reading a spent streak does not extend its cooldown every pass", C._load(C.SPENT, {})["timer-test"]["at"] == 100000)
check("sender and every relevant store remain isolated", C._ask is gemma and C._ground_inquiry is identity_stub
      and all(p.startswith(HOME) for p in (C.SPENT, C.RECEIPTS, C.ROOT, L.LOOKUPS, L.SESSIONS)))

# No provider is called: inspect the actual reading prompt passed to the stub.
answers[:] = [{"factual_observation": "No PDB cross-references in this response", "answers_question": "no"}]
C._reflect("ctx", {}, [{"accession": "O43511", "pdb_ids": []}])
check("empty cross-references are explicitly bounded in the reading prompt",
      "does NOT establish that no experimental structures exist" in systems[-1])
check("reflection remains a stub", C._ask is gemma)
check("all newly used stores are scratch", all(p.startswith(HOME) for p in (C.CONFIG, C.STATE, C.NOTEBOOK, L.ROOT)))

check("nothing reached the network", NET == [], NET)
import shutil; shutil.rmtree(HOME, ignore_errors=True)
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
