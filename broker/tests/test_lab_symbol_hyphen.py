#!/usr/bin/env python3
"""A gene symbol written with a hyphen is the same symbol without it, and nothing looser (21 October, fault loop: the
18 October TDP-43 inquiry, notebook 122261, was refused with source_gene_mismatch although its UniProt record named
TARDBP and TDP43; reproduced offline: verify_uniprot_identity and question_entity_context both refused TDP-43 against
Q13148).

Pure functions on hand-built records shaped like UniProt's; nothing is fetched, no model is asked; sockets are refused."""
import os, socket, sys
HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
NET = []
def _no(self, *a, **k): NET.append(a); raise OSError("this suite reaches nothing")
socket.socket.connect = _no
sys.path.insert(0, os.path.join(REPO, "scripts"))
import lab_sources as L
R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + ("" if ok else "  ->  %r" % (str(d)[:400],)))

def rec(acc, gene, synonyms=(), taxon=9606, protein=""):
    return {"primaryAccession": acc, "accession": acc, "taxon_id": taxon, "protein_name": protein,
            "genes": [{"geneName": {"value": gene}, "synonyms": [{"value": s} for s in synonyms]}]}
TARDBP = rec("Q13148", "TARDBP", ["TDP43"], protein="TAR DNA-binding protein 43")
MOUSE = rec("Q921F2", "Tardbp", ["Tdp43"], taxon=10090, protein="TAR DNA-binding protein 43")
FUS = rec("P35637", "FUS", ["TLS"], protein="RNA-binding protein FUS")
def kept(query, records):
    try: return [r["primaryAccession"] for r in L.verify_uniprot_identity(query, records)]
    except ValueError as e: return str(e)
def issues(question, query, records):
    return L.question_entity_context({"question": question, "uniprot_query": query}, records)["issues"]

check("TDP-43 is established by TARDBP's synonym TDP43", kept("gene:TDP-43 AND organism_id:9606", [TARDBP]) == ["Q13148"])
check("and the reading's own identity check agrees",
      issues("What does the C-terminal region of human TDP-43 do?", "gene:TDP-43 AND organism_id:9606", [TARDBP]) == [])
check("TDP43 and TARDBP still match exactly", kept("gene:TDP43", [TARDBP]) == ["Q13148"] and kept("gene:TARDBP", [TARDBP]) == ["Q13148"])
check("a record writing the hyphen matches a request without it",
      kept("gene:TDP43", [rec("X00001", "TARDBP", ["TDP-43"])]) == ["X00001"])
check("TDP-43 among unrelated hits keeps only TARDBP", kept("gene:TDP-43", [FUS, TARDBP]) == ["Q13148"])

r = kept("gene:TDP-43", [FUS])
check("an unrelated gene is still refused, naming what came back", r.startswith("source_gene_mismatch") and "FUS" in r, r)
check("only the hyphen is dropped: TDP-43 is not TDP-4, TDP4 or TDP430",
      all(str(kept("gene:TDP-43", [rec("X1", g)])).startswith("source_gene_mismatch") for g in ("TDP-4", "TDP4", "TDP430")))
check("HLA-A is not HLA-B", str(kept("gene:HLA-A", [rec("P01889", "HLA-B")])).startswith("source_gene_mismatch"))
check("MHC1 is not MHC_1: underscores are kept (the 20 October MHC refusal stands)",
      str(kept("gene:MHC1", [rec("A0A836GP37", "MHC_1")])).startswith("source_gene_mismatch"))
check("case alone was already ignored, and still is", kept("gene:tdp-43", [MOUSE]) == ["Q921F2"])

amb = issues("What does TDP-43 bind?", "gene:TDP-43", [TARDBP, MOUSE])
check("two species' TDP-43 with no taxon asked is still ambiguous", any("multiple retrieved targets" in i for i in amb), amb)
check("asking for human settles it to the human record",
      issues("What does human TDP-43 bind?", "gene:TDP-43 AND organism_id:9606", [TARDBP, MOUSE]) == [])

two = L.question_entity_context({"question": "Compare TDP-43 and FUS low-complexity domains in human cells.",
                                 "uniprot_query": "(gene:TDP-43 OR gene:FUS) AND organism_id:9606"}, [TARDBP, FUS])
check("two named targets map each to its own record", two["issues"] == []
      and two.get("target_mapping") == {"FUS": "P35637", "TDP-43": "Q13148"}, two)
one = issues("Compare TDP-43 and FUS low-complexity domains in human cells.",
             "(gene:TDP-43 OR gene:FUS) AND organism_id:9606", [TARDBP])
check("and a target with no record of its own is still unresolved", any("no retrieved record establishes FUS" in i for i in one), one)
check("nothing reached the network", not NET)
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
