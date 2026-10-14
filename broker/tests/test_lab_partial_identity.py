#!/usr/bin/env python3
"""The target that WAS established is reviewed; the one that was not is named (14 October). A comparison whose
other protein never came back lost the whole pass: TFR2=Q9UP52 was established, TFR1 absent, and nothing was
reviewed. Scratch HOME and workspace; sockets refused; the model and the checker are stubs."""
import json, os, socket, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="lab-partial-identity-"); os.environ["HOME"] = HOME
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

def rec(acc, gene, name, syn=()):
    return {"accession": acc, "protein_name": name, "taxon_id": 9606, "organism": "Homo sapiens",
            "genes": [{"geneName": {"value": gene}, "synonyms": [{"value": x} for x in syn]}],
            "features_named": ["Binding site: Fe cation"], "function": "binds transferrin", "sequence": "MKV", "length": 3}
Q = "What are the metal-binding geometries of human Transferrin Receptor 2 (TFR2) compared with TFR1?"
INQ = {"question": Q, "uniprot_query": "(gene:TFR2 OR gene:TFR1) AND taxonomy_id:9606 AND reviewed:true"}
TFR2 = rec("Q9UP52", "TFR2", "Transferrin receptor protein 2")
COVER = {"answered": False, "missing": ["the geometry of the second receptor"],
         "supports": [{"requirement": "iron site", "quote": "Fe cation", "source_citation": "UniProt Q9UP52"}],
         "original_question": Q}
seen = {}
def ask(system, prompt, **k):
    seen["prompt"] = prompt
    return json.dumps({"answers_question": "no", "attention": "a", "factual_observation": "o",
                       "speculative_reading": "", "next_question": "n", "instrument_gap": ""})
saved = (C._ask, C._coverage_check)
C._ask, C._coverage_check = ask, (lambda *a, **k: dict(COVER))
try:
    out = C._reflect("", INQ, {"records": [TFR2]})
finally:
    C._ask, C._coverage_check = saved
check("the established target is reviewed instead of the pass being lost", out.get("coverage_check") and out["coverage_check"]["supports"], out.get("answers_question"))
check("the absent target is named in what is missing", out.get("unestablished_targets") == ["TFR1"]
      and "no retrieved record establishes TFR1" in out["missing_evidence"], out.get("missing_evidence"))
check("the reader is told which targets are established, and not to let one answer for the other",
      "ONLY THESE TARGETS ARE ESTABLISHED" in seen["prompt"] and "TFR1" in seen["prompt"]
      and "never let an established protein answer for it" in seen["prompt"])
check("the question is unchanged", json.loads(seen["prompt"].split("QUESTION:\n", 1)[1].split("\n\nEXACT", 1)[0])["question"] == Q)
check("the review is not answered on a half-established comparison", not out["answers_question"].startswith("yes"))
check("its outcome is a research one, not a target refusal", LCE.outcome(out)[0] == "partially_supported", LCE.outcome(out))

print("--- what still stops the pass ---")
def refuses(records, question=Q, uq=INQ["uniprot_query"]):
    C2 = (C._ask, C._coverage_check); C._ask = ask; C._coverage_check = lambda *a, **k: dict(COVER)
    try:
        return C._reflect("", {"question": question, "uniprot_query": uq}, {"records": records})
    finally:
        C._ask, C._coverage_check = C2
wrong = refuses([rec("P02786", "TFRC", "Transferrin receptor protein 1")],
                "What are the metal-binding geometries of the human GLUT1 (SLC1A1) transporter?",
                "gene:SLC1A1 AND organism_id:9606")
check("a contradicted alias still stops the pass", wrong["answers_question"].startswith("no: ")
      and not wrong.get("coverage_check"), wrong["answers_question"][:120])
none = refuses([rec("P12345", "XXX", "Something else entirely")],
               "What are the motifs of the human UbcH5c protein?", 'protein_name:"UbcH5c" AND organism_id:9606')
check("a target nothing establishes still stops the pass", none["answers_question"].startswith("no: "), none["answers_question"][:120])
check("nothing reached the network", not NET, NET)
print("%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
