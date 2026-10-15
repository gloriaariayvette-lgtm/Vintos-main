#!/usr/bin/env python3
"""A human question that names its gene fetches that gene, even when the planner searched by a name (15 October).
"human collagen type IV (COL4A1)" was searched as protein_name "collagen type IV", which returned Q9Y5P4 (collagen
type IV alpha-3-binding protein), and the review refused it as the wrong target: 8 of 23 questions after the 05:48
deploy ended that way. The question is never rewritten; only what is fetched. Scratch HOME; no socket; no model."""
import os, socket, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="lab-named-gene-fetch-"); os.environ["HOME"] = HOME
os.environ["SPARK_WORKSPACE"] = os.path.join(HOME, ".vintos", "workspace")
NET = []
def _no(self, *a, **k): NET.append(a); raise OSError("this suite reaches nothing")
socket.socket.connect = _no
sys.path.insert(0, os.path.join(REPO, "scripts"))
import chemistry_lab as C
R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:500]) if d and not ok else ""))
check("the Lab's store is scratch and sockets are refused", C.ROOT.startswith(HOME) and socket.socket.connect is _no)

Q = ("What are the specific structural motifs of the human collagen type IV (COL4A1) triple helix and its unique "
     "interaction with integrins?")
def q(uq, question=Q):
    return C._inquiry({"question": question, "uniprot_query": uq})
got = q('protein_name:"collagen type IV" AND organism_id:9606')
check("a search by name fetches the gene the question names",
      got["uniprot_query"] == "(gene:COL4A1) AND taxonomy_id:9606 AND reviewed:true", got["uniprot_query"])
check("the question is not rewritten", got["question"] == Q, got["question"])
check("the identity check is told the query that is sent", got["identity_queries"][0] == got["uniprot_query"])
got = q("gene:ITGB1 AND organism_id:9606")
check("a partner the planner chose is still fetched beside the named gene",
      got["uniprot_query"] == "(gene:COL4A1 OR gene:ITGB1) AND taxonomy_id:9606 AND reviewed:true", got["uniprot_query"])
got = q("gene:COL4A1 AND organism_id:9606")
check("a query that already names the gene is left as it is", "protein_name" not in got["uniprot_query"]
      and "gene:COL4A1 AND organism_id:9606" in got["uniprot_query"] and " OR " not in got["uniprot_query"], got["uniprot_query"])
got = q("accession:Q9Y5P4")
check("an accession is the planner's explicit choice and is left alone", "accession:Q9Y5P4" in got["uniprot_query"]
      and "COL4A1" not in got["uniprot_query"], got["uniprot_query"])
got = q("protein_name:collagen AND organism_id:10090")
check("a query for another organism is not rewritten", "10090" in got["uniprot_query"]
      and "COL4A1" not in got["uniprot_query"], got["uniprot_query"])
TJ = "What are the specific structural features of the human tight junction protein 1 (TJP1/ZO-1) scaffold?"
got = q('protein_name:"tight junction protein" AND organism_id:9606', TJ)
check("a gene written with its alias fetches both spellings",
      got["uniprot_query"] == "(gene:TJP1 OR gene:ZO-1) AND taxonomy_id:9606 AND reviewed:true", got["uniprot_query"])
NH = "What are the specific structural features of the crenochrome protein in the archaeon Sulfolobus solfataricus?"
got = q("protein_name:crenochrome", NH)
check("a question that is not about a human gene is not touched", "protein_name:crenochrome" in got["uniprot_query"]
      and "gene:" not in got["uniprot_query"], got["uniprot_query"])
check("nothing reached the network", not NET, NET)
print("%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
