#!/usr/bin/env python3
"""A premise the target's own record does not list is named before review, and a coordinate question reads its PDB
entry (T-f212a423, 2026-10-14). The replay of 20 failed questions found NEUROD1 'zinc finger domains', ANT 'metal-
binding geometries' and XYZ-coordinate questions sent to literature, none of which papers could rescue.
Scratch HOME and workspace; sockets refused; the model is a stub that must not be asked."""
import os, socket, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="lab-premise-"); os.environ["HOME"] = HOME
os.environ["SPARK_WORKSPACE"] = os.path.join(HOME, ".vintos", "workspace")
NET = []
def _no(self, *a, **k): NET.append(a); raise OSError("this suite reaches nothing")
socket.socket.connect = _no
sys.path.insert(0, os.path.join(REPO, "scripts"))
import chemistry_lab as C, lab_claim_evidence as LCE, lab_claim_replay as RP
R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:400]) if d and not ok else ""))
check("the Lab's store is scratch and sockets are refused", C.ROOT.startswith(HOME) and socket.socket.connect is _no)

feats = [{"type": "Domain", "description": "bHLH"}, {"type": "Binding site", "ligand": {"name": "Fe cation"}},
         {"type": "Zinc finger", "description": "C2H2-type 1"}, {"type": "Signal", "description": "x"}]
named = C._features_named(feats)
check("named features keep domains, zinc fingers and binding sites by ligand", named == ["Domain: bHLH", "Binding site: Fe cation", "Zinc finger: C2H2-type 1"], named)
src = open(os.path.join(REPO, "scripts", "chemistry_lab.py")).read()
check("UniProt is asked for the features and cofactors a question may claim", "ft_zn_fing,ft_binding" in src and "cc_cofactor" in src)

def rec(acc, gene, name, function="", features=(), domains=()):
    return {"accession": acc, "protein_name": name, "taxon_id": 9606, "organism": "Homo sapiens",
            "genes": [{"geneName": {"value": gene}}], "function": function, "features_named": list(features),
            "domains": [{"description": d} for d in domains]}
neurod = rec("Q13562", "NEUROD1", "Neurogenic differentiation factor 1", "Acts as a transcriptional activator",
             ["Domain: bHLH"], ["bHLH"])
ant = rec("P12235", "SLC25A4", "ADP/ATP translocase 1", "Catalyzes the exchange of ADP and ATP across the membrane",
          ["Transmembrane: Helical", "Repeat: Solcar 1"])
fth1 = rec("P02794", "FTH1", "Ferritin heavy chain", "Stores iron in a soluble form", ["Binding site: Fe cation", "Domain: Ferritin-like diiron"])
check("a zinc finger the record does not list is named", C._premise_issues("What do the zinc finger domains of human NEUROD1 do?", [neurod]))
check("a domain the record lists is not", not C._premise_issues("Which residues form the bHLH domain of human NEUROD1?", [neurod]))
check("metal binding a transporter's record does not list is named", C._premise_issues(
      "What are the metal-binding coordination geometries of the human ADP/ATP translocase SLC25A4?", [ant]))
check("iron binding the record lists is not", not C._premise_issues("What residues form the iron-binding site of human FTH1?", [fth1]))
check("a comparison of two records is left alone", not C._premise_issues("zinc finger of A and B?", [neurod, ant]))
check("an unannotated record says nothing either way", not C._premise_issues("zinc finger of X?", [rec("X1", "X", "X", "a function")]))

q = "What are the documented functional roles of the zinc finger domains of human NEUROD1 in neuronal differentiation?"
inq = {"question": q, "uniprot_query": "gene:NEUROD1 AND organism_id:9606 AND reviewed:true"}
def ask(*a, **k): raise AssertionError("the reviewer must not be asked about a premise its target's record does not list")
saved = C._ask; C._ask = ask
try:
    out = C._reflect("", inq, {"records": [neurod]})
finally:
    C._ask = saved
check("the review names the premise and asks no model", out["answers_question"].startswith("no: premise not established")
      and out.get("premise_check", {}).get("issues"), out)
check("its outcome is a flawed premise, not missing evidence", LCE.outcome(out)[0] == "flawed_premise", LCE.outcome(out))
check("a flawed premise is not sent to the full-text search", LCE.gather(inq, out, [neurod], fetch=_no).get("skipped", "").startswith("flawed_premise"))

print("--- coordinates read the structure ---")
cq = "What are the precise XYZ coordinates for the oxygen atoms of Glu 27 and Glu 107 in the 2CEI structure?"
check("a coordinate question naming a PDB entry reads its coordinates",
      C._coordinate_route(cq, None) == {"source": "pdb", "entry_id": "2CEI", "operation": "structure_evidence"})
check("a PDB metadata request becomes a coordinate read", C._coordinate_route(cq, {"source": "pdb", "entry_id": "2CEI"})["operation"] == "structure_evidence")
check("another source the planner chose is kept", C._coordinate_route(cq, {"source": "chembl", "target_id": "CHEMBL1"}) == {"source": "chembl", "target_id": "CHEMBL1"})
check("no PDB entry named, no route", C._coordinate_route("What are the bond angles of the human SOD1 metal site?", None) is None)
check("a year is not a PDB entry", C._coordinate_route("What distances were reported in 2023 structures of SOD1?", None) is None)
made = C._inquiry({"question": cq, "uniprot_query": "gene:FTH1 AND organism_id:9606"})
check("the inquiry carries the coordinate read, and the question is unchanged",
      made["source_query"] == {"source": "pdb", "entry_id": "2CEI", "operation": "structure_evidence"} and made["question"] == cq, made["source_query"])

print("--- the fixed set, rechecked ---")
items = [{"inquiry": inq, "coverage_check": {"answered": False, "missing": ["zinc finger roles"], "supports": []}},
         {"inquiry": {"question": cq, "uniprot_query": "gene:FTH1 AND organism_id:9606"}, "coverage_check": {"answered": False, "missing": ["xyz"], "supports": []}},
         {"inquiry": {"question": "Which residues form the iron-binding site of human FTH1?", "uniprot_query": "gene:FTH1 AND organism_id:9606"},
          "coverage_check": {"answered": False, "missing": ["residues"], "supports": []}}]
rows = {"gene:NEUROD1 AND organism_id:9606 AND reviewed:true": [neurod], "gene:FTH1 AND organism_id:9606": [fth1]}
got = RP.recheck(items, browse=lambda query: rows[query])
check("recheck: flawed premise, coordinate read, reviewable", [r["now"] for r in got] == ["flawed_premise", "coordinate_read", "reviewable"], got)
check("nothing reached the network", not NET, NET)
print("%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
