#!/usr/bin/env python3
"""One question asks one thing (16 October, after 17:48 UTC: 11 of 12 reviews partial, each missing a second clause
no source could return; the one complete answer asked only what its record established). The planner is told so,
a two-part question is sent back once to narrow, and if it still asks two things its first is kept.
The planner is a stub; scratch HOME; no socket."""
import json, os, socket, sys, tempfile, types
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
print("--- every planner answer passes the narrowing, on every path ---")
C._ask = lambda system, prompt, **k: json.dumps({"browse_lane": "protein", "question":
    "What are the structural features of Tryptophan synthase in Streptomyces coelicolor, and how do the active site geometries facilitate catalysis?"})
v = C._plan("Return JSON only.", "TASK\n\nREFUSED, IT IS A REPEAT: x.")
check("a replan's two-part answer is cut to its first ask", v["question"].endswith("Streptomyces coelicolor?"), v["question"])
faults = [json.loads(l) for l in open(C.FAULTS)]
check("and the cut is written down with what was kept", any(f["stage"] == "question_narrowed" and f.get("kept") for f in faults))
held_q = "What are the structural features of the CFTR R-domain and how does AKAP influence gating?"
C._question_holds = lambda: [{"question": held_q}]
C._held_question = lambda inquiry: {"question": held_q}   # a paraphrase or same-lookup match: not a reason to keep two asks
C._ask = lambda system, prompt, **k: json.dumps({"browse_lane": "protein", "question": held_q})
check("a question already held keeps its exact words", C._plan("x", "TASK")["question"] == held_q)
near = "What are the structural features of the CFTR R-domain, and how does PKA phosphorylation open the channel?"
C._ask = lambda system, prompt, **k: json.dumps({"browse_lane": "protein", "question": near})
check("a question that only resembles a held one is still cut to one ask (17 October: 124 of 146 incomplete)",
      "CFTR R-domain" in C._plan("x", "TASK")["question"] and "PKA" not in C._plan("x", "TASK")["question"],
      C._plan("x", "TASK")["question"])
src = open(os.path.join(REPO, "scripts", "chemistry_lab.py")).read()
_note = src[src.index('"kind": "structure_read"'):][:1600]
check("a structure read writes what it found into the notebook", '"metal_sites": [' in _note and '"chains":' in _note)
print("--- a structure already read is reused, and written once ---")
from datetime import datetime as _d, timezone as _tz, timedelta as _td
def _rcpt(entry, days_ago, metals=True):
    rec = {"entry_id": entry}
    if metals: rec["metal_sites"] = [{"element": "FE", "residue": "HEM", "residue_number": 300, "chain": "A"}]
    return {"source": "pdb", "query": {"source": "pdb", "entry_id": entry, "operation": "structure_evidence"},
            "records": [rec], "retrieved_at": (_d.now(_tz.utc) - _td(days=days_ago)).isoformat(), "receipt_id": entry + str(days_ago)}
RCPT = os.path.join(C.ROOT, "source-receipts.jsonl"); os.makedirs(C.ROOT, exist_ok=True)
with open(RCPT, "a") as f:
    for r in (_rcpt("1N3U", 2), _rcpt("7LGU", 45), _rcpt("9NOR", 1, metals=False)):
        f.write(json.dumps(r) + "\n")
hit = C._structure_cached("1n3u")
check("an entry read in the last 30 days is reused", hit and hit["receipt"]["receipt_id"] == "1N3U2", hit)
check("an older read is fetched fresh", C._structure_cached("7LGU") is None)
check("a read from before metal sites were recorded is fetched fresh", C._structure_cached("9NOR") is None)
check("an entry never read is fetched", C._structure_cached("2SHP") is None)
_phase = src[src.index('elif phase in ("embed", "reflect") and _structure_pending(state):'):][:2600]
check("the structure step asks the cache before the source", "sourced = cached or chemistry_sources.query(" in _phase)
check("and no longer writes a receipt the source layer already wrote", '_append(os.path.join(ROOT, "source-receipts.jsonl"), receipt_row)' not in _phase)
print("--- the hallmarks template is asked the way a record answers it ---")
hq = "What are the specific structural hallmarks of the human sodium-chloride symporter (SLC12A3)?"
cq = C.concrete_ask(hq)
check("'structural hallmarks of X' becomes what the record lists", cq.startswith("Which domains, binding sites and annotated residues")
      and "SLC12A3" in cq and C.second_ask(cq) == "" and C._STRUCTURAL.search(cq), cq)
check("a hallmarks question with its own clause is left alone",
      C.concrete_ask("What are the structural features of the pore that gate ion flow in KcsA?").startswith("What are"))
check("any other question passes unchanged", C.concrete_ask("What is the fold of human ISCU?") == "What is the fold of human ISCU?")
C._ask = lambda system, prompt, **k: json.dumps({"browse_lane": "protein", "question":
    "What are the specific structural hallmarks and localization of the human thioredoxin (TXN) protein, and how do they work?"})
_held_saved = C._question_holds; C._question_holds = lambda: []
v = C._plan("x", "TASK")
check("narrowing and the rewrite both run on a planner answer", v["question"].startswith("Which domains") and "thioredoxin" in v["question"], v)
C._question_holds = _held_saved
faults = [json.loads(l) for l in open(C.FAULTS)]
check("the rewrite is written down", any(f["stage"] == "question_made_concrete" for f in faults))

print("--- the checker's size estimate is set from a measurement ---")
req = ("s" * 1000, "p" * 9000, 800)
check("by default every byte still counts as a token", C._coverage_budget(req)["conservative_total"] == 10000 + 1024 + 800)
json.dump({"coverage_tokens_per_byte": 0.35, "coverage_context_tokens": 32768}, open(C.CONFIG, "w"))
b = C._coverage_budget(req)
check("a measured ratio and context replace the guess", b["conservative_total"] == 3500 + 1024 + 800 and b["context_budget"] == 32768, b)
json.dump({"coverage_tokens_per_byte": "nonsense"}, open(C.CONFIG, "w"))
check("a broken setting falls back to one token per byte", C._coverage_budget(req)["tokens_per_byte"] == 1.0)
os.remove(C.CONFIG)
sys.path.insert(0, os.path.join(REPO, "scripts"))
import lab_token_measure as M
check("the measurement takes the worst ratio seen, with 15% margin", M.recommend([(1000, 300, None), (2000, 800, None), (500, None, "x")]) == round(0.4 * 1.15, 4))
sent = []
def fake_post(url, body, timeout=300):
    sent.append(body); return {"usage": {"prompt_tokens": 1234}}
snap = os.path.join(C.ROOT, "snap.json")
json.dump({"inquiry": {"question": "What is the fold of human ISCU?"}, "observations": {"records": [{"accession": "Q9H1K1"}]}}, open(snap, "w"))
rows = M.measure([snap], post=fake_post)
check("each saved review is replayed for one token, to the Lab's own model", sent and sent[0]["max_tokens"] == 1
      and sent[0]["model"] == C.LLM_MODEL and rows[0][1] == 1234, (rows, sent[:1]))

print("--- a refused pass falls back to a fresh real protein, holds or not ---")
_saved = (C._plan, C._held_to_plan, C._held_question, C.spent_retrieval, C._question_holds, C._existing_model_read)
C._plan = lambda system, prompt: {"browse_lane": "protein", "question": "What are the structural hallmarks of human SLC26A19?"}
C._existing_model_read = lambda inq: inq
C._question_holds = lambda: [{"question": "something else entirely"}]   # something is always held
C._held_question = lambda inq: {"refused": "held"} if "myoglobin" in str(inq.get("uniprot_query") or "").lower() else None
C.spent_retrieval = lambda inq, spent: False
def _h2p(system, task, inq, value, lean, step, repeats, spent=None, replan=True):
    return ((dict(inq, refused="repeat") if "SLC26A19" in str(inq.get("question")) else inq), value)
C._held_to_plan = _h2p
rep = types.SimpleNamespace(repeat=lambda inq: None)
got = C._fresh_free_inquiry(rep, {"subjects": []})
check("three refused picks no longer end the pass while any hold exists", got is not None and not got.get("refused"), got)
check("a held fallback is skipped, the next real protein is taken", got and "lysozyme" in str(got.get("uniprot_query")).lower(), got)
check("the fallback list is real, varied proteins and long enough to outlast a week of holds", len(C._FRESH_PROTEINS) >= 30)
check("the planner is told not to walk a gene family by number", "Do not walk a gene family by number" in src)
_o = src[src.index("def _orient("):src.index("lean_text = ((")]
check("the free pass after a refusal is not switched off by unrelated holds", "and not waiting and not _question_holds()" not in _o)
(C._plan, C._held_to_plan, C._held_question, C.spent_retrieval, C._question_holds, C._existing_model_read) = _saved
_outside = src.replace(src[src.index("def _narrow("):src.index("def _compact_names(")], "")
check("no planner call bypasses the narrowing", "_json_object(_ask(system," not in _outside and "_plan_raw(" not in _outside)
check("nothing reached the network", not NET)
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
