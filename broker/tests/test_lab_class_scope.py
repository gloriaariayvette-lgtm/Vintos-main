#!/usr/bin/env python3
"""A question about a kind of protein is adjudicated as its retrieved members, with the scope said out loud
(T-b5c8e6c1; Chat's review, 2026-10-14: requiring a kind to resolve to one record is a category error). 51 of the
130 distinct questions on 14 October were refused this way and produced nothing. No record is ever allowed to
stand for the kind. Scratch HOME and workspace; sockets refused; the model is a stub."""
import json, os, socket, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="lab-class-scope-"); os.environ["HOME"] = HOME
os.environ["SPARK_WORKSPACE"] = os.path.join(HOME, ".vintos", "workspace")
NET = []
def _no(self, *a, **k): NET.append(a); raise OSError("this suite reaches nothing")
socket.socket.connect = _no
sys.path.insert(0, os.path.join(REPO, "scripts"))
import chemistry_lab as C, lab_claim_evidence as LCE
R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:400]) if d and not ok else ""))
check("the Lab's store is scratch and sockets are refused", C.ROOT.startswith(HOME) and socket.socket.connect is _no)

print("--- which questions are about a kind ---")
for q, want in (("What are the SH3 domains in human Src family kinases?", True),
                ("What are the genomic neighborhoods of bacteriophage reverse transcriptases?", True),
                ("What are the siderophore receptors in Bacillus subtilis?", True),
                ("What are the structural motifs of the Lipopolysaccharide transport system?", True),
                ("Which residues coordinate iron in human FTH1?", False),
                ("What is the topology of human SLC26A4 (pendrin)?", False)):
    check("class question %r -> %s" % (q[:46], want), C.class_question(q) is want, C.class_question(q))

def rec(acc, name, gene="X"):
    return {"accession": acc, "protein_name": name, "taxon_id": 9606, "organism": "Homo sapiens",
            "genes": [{"geneName": {"value": gene}}], "function": "A kinase of the Src family with an SH3 domain.",
            "features_named": ["Domain: SH3"], "sequence": "MKV", "length": 3}
MEMBERS = [rec("P12931", "Proto-oncogene tyrosine-protein kinase Src", "SRC"),
           rec("P06241", "Tyrosine-protein kinase Fyn", "FYN")]
Q = "What are the specific structural features of the SH3 domain in human Src family kinases, and their binding motifs?"
INQ = {"question": Q, "uniprot_query": 'protein_name:"Src family kinases" AND organism_id:9606'}

seen = {}
def ask(system, prompt, **k):
    seen.setdefault("prompts", []).append((system, prompt))
    return json.dumps({"answers_question": "no", "attention": "a", "factual_observation": "o",
                       "speculative_reading": "", "next_question": "n", "instrument_gap": ""})
COVER = {"answered": True, "missing": [],
         "supports": [{"requirement": "SH3 domain", "quote": "SH3", "source_citation": "UniProt P12931"}],
         "original_question": Q}
saved = (C._ask, C._coverage_check)
C._ask, C._coverage_check = ask, (lambda inquiry, *a, **k: seen.update(checker_inquiry=inquiry) or dict(COVER))
try:
    out = C._reflect("", INQ, {"records": MEMBERS})
finally:
    C._ask, C._coverage_check = saved
check("the question is reviewed instead of refused for naming a kind", out.get("coverage_check"), out.get("answers_question"))
check("the members are named by their own accessions",
      out["entity_context_check"].get("class_members") == ["P12931", "P06241"], out["entity_context_check"])
check("the question itself is unchanged", json.loads(seen["prompts"][0][1].split("QUESTION:\n", 1)[1].split("\n\nEXACT", 1)[0])["question"] == Q)
reader = seen["prompts"][0][1]
check("the reader is told these are members, and how many", "NAMES A KIND OF PROTEIN" in reader and "2 retrieved members" in reader, reader[:200])
check("and told a finding holds only for the members it is quoted from", "and for no others" in reader)
check("and that every member examined is not the same as characteristic of the kind",
      "NOT the same as characteristic of the kind" in reader and "says nothing about how common" in reader)
check("the checker is given the same scope", (seen.get("checker_inquiry") or {}).get("class_members") == ["P12931", "P06241"])
prepared = C._coverage_request(dict(INQ, class_members=["P12931", "P06241"]), {"records": MEMBERS, "LITERATURE": []})
check("and it reaches the checker's own instructions", "NAMES A KIND OF PROTEIN" in prepared[3][0], prepared[3][0][-200:])
check("an answer is labelled as supported for the members examined, not as answered",
      LCE.outcome(out)[0] == "supported_for_examined_members", LCE.outcome(out))
check("and that label says the kind itself is not established", "the kind itself is not established" in LCE.outcome(out)[1])
check("it is still a research outcome, not a target refusal", LCE.outcome(out)[0] in LCE.RESEARCH)

print("--- what is still refused ---")
def refuse(records, question, uq):
    s2 = (C._ask, C._coverage_check); C._ask = ask; C._coverage_check = lambda *a, **k: dict(COVER)
    try: return C._reflect("", {"question": question, "uniprot_query": uq}, {"records": records})
    finally: C._ask, C._coverage_check = s2
glut1 = rec("P11166", "Solute carrier family 2, facilitated glucose transporter member 1", "SLC2A1")
glut1["genes"][0]["synonyms"] = [{"value": "GLUT1"}]
one = refuse([rec("P43005", "Excitatory amino acid transporter 3", "SLC1A1"), glut1],
             "What are the extracellular loops of the human GLUT1 (SLC1A1) transporter family?",
             "(gene:SLC1A1 OR gene:GLUT1) AND taxonomy_id:9606")
check("a contradicted alias is still refused, kind or not", str(one["answers_question"]).startswith("no: ")
      and not one.get("coverage_check"), one["answers_question"][:140])
none = refuse([], "What are the siderophore receptors in Bacillus subtilis?", 'protein_name:"siderophore receptor"')
check("a kind with no retrieved member is still refused", str(none["answers_question"]).startswith("no: "), none["answers_question"][:100])
check("nothing reached the network", not NET, NET)
print("%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
