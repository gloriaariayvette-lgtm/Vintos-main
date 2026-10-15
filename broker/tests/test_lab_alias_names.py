#!/usr/bin/env python3
"""A one-word name the question gives a gene must be on that gene's record (15 October). "The human SLC26A1 (pendrin)
protein" was answered from SLC26A1's record, sulfate anion transporter 1; pendrin is SLC26A4. A record not listing a
name is not proof it is wrong, so it is an unverified premise, never a contradiction. Also: the replay tool's
`missing` view reads the notebook and writes nothing. Scratch HOME; no socket; no model."""
import json, os, socket, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="lab-alias-names-"); os.environ["HOME"] = HOME
os.environ["SPARK_WORKSPACE"] = os.path.join(HOME, ".vintos", "workspace")
NET = []
def _no(self, *a, **k): NET.append(a); raise OSError("this suite reaches nothing")
socket.socket.connect = _no
sys.path.insert(0, os.path.join(REPO, "scripts"))
import chemistry_lab as C, lab_claim_evidence as LCE, lab_claim_replay as RP
R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:500]) if d and not ok else ""))
check("the Lab's store is scratch and sockets are refused", C.ROOT.startswith(HOME) and RP.NOTEBOOK.startswith(HOME)
      and socket.socket.connect is _no)

def rec(acc, gene, syn=(), name="", alt=()):
    return {"accession": acc, "protein_name": name, "protein_aliases": list(alt), "taxon_id": 9606,
            "genes": [{"geneName": {"value": gene}, "synonyms": [{"value": x} for x in syn]}]}
sat1 = rec("Q9H2B4", "SLC26A1", ("SAT1",), "Sulfate anion transporter 1")
got = C._alias_issues("What is the structural organization of the human SLC26A1 (pendrin) protein?", [sat1])
check("a name the record does not carry is named, with the record that was fetched",
      len(got) == 1 and "pendrin" in got[0] and "Q9H2B4" in got[0] and "contradict" not in got[0], got)
ok = [("the human SLC26A4 (pendrin) protein", rec("O43511", "SLC26A4", ("PDS",), "Pendrin")),
      ("human SLC30A8 (ZnT8)", rec("Q8IWU4", "SLC30A8", ("ZNT8",), "Proton-coupled zinc antiporter SLC30A8")),
      ("human FBN1 (fibrillin-1) domains", rec("P35555", "FBN1", ("FBN",), "Fibrillin-1")),
      ("human GCK (glucokinase)", rec("P35557", "GCK", ("HK4",), "Hexokinase-4", ("Glucokinase",))),
      ("human SLC26A3 (DRA) protein", rec("P40879", "SLC26A3", ("DRA",), "Chloride anion exchanger")),
      ("COL4A1 (collagen type IV alpha 1)", rec("P02462", "COL4A1", (), "Collagen alpha-1(IV) chain")),
      ("human TP53 (residues 1-50)", rec("P04637", "TP53", ("P53",), "Cellular tumor antigen p53"))]
for q, r in ok:
    check("not flagged: %s" % q, C._alias_issues(q, [r]) == [], C._alias_issues(q, [r]))

review = C.reflect_on_evidence if hasattr(C, "reflect_on_evidence") else None
row = {"premise_check": {"issues": got, "outcome": "unverified_premise"}}
check("it is reported as an unverified premise", LCE.outcome(row)[0] == "unverified_premise", LCE.outcome(row))
src = open(os.path.join(REPO, "scripts", "chemistry_lab.py")).read()
check("the check runs before the review, on the established records",
      "_aliases = _alias_issues(inquiry.get('question'), _established)" in src
      and src.index("_aliases = _alias_issues") < src.index("prepared = _coverage_request(inquiry, records)"))

print("--- the replay tool's missing view ---")
os.makedirs(os.path.dirname(RP.NOTEBOOK), exist_ok=True)
rows = [{"kind": "reflection", "at": "2026-10-15T09:00:00+00:00",
         "inquiry": {"question": "Q one", "uniprot_query": "gene:SLC26A3"},
         "coverage_check": {"answered": False, "missing": ["primary amino acid sequence"], "supports": [{"q": 1}]},
         "review_outcome": "partially_supported", "source_accessions": ["P40879"]},
        {"kind": "reflection", "at": "2026-10-15T09:01:00+00:00", "inquiry": {"question": "Q two"},
         "review_outcome": "answered"}]
open(RP.NOTEBOOK, "w").write("\n".join(json.dumps(r) for r in rows) + "\n")
before = open(RP.NOTEBOOK).read()
got = RP.missing(since="2026-10-15T00:00:00+00:00")
check("each partially supported question is listed with what it lacked and its sources",
      len(got) == 1 and got[0]["missing"] == ["primary amino acid sequence"] and got[0]["sources"] == ["P40879"], got)
check("the notebook is unchanged", open(RP.NOTEBOOK).read() == before)
check("nothing reached the network", not NET, NET)
print("%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
