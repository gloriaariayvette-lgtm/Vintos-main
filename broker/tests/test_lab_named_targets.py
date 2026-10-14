#!/usr/bin/env python3
"""Every protein a question names is fetched; a wrong alias is named, not stood in for (14 October). After the
9:55 restart, about a dozen of 30 reviews failed on identity: "SOX9 and SOX10" and "BRCA1 ... BARD1" fetched one
gene, and "GLUT1 (SLC1A1)" fetched EAAT3 for GLUT1. Scratch HOME; no socket; no model."""
import os, socket, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="lab-named-targets-"); os.environ["HOME"] = HOME
os.environ["SPARK_WORKSPACE"] = os.path.join(HOME, ".vintos", "workspace")
NET = []
def _no(self, *a, **k): NET.append(a); raise OSError("this suite reaches nothing")
socket.socket.connect = _no
sys.path.insert(0, os.path.join(REPO, "scripts"))
import chemistry_lab as C, lab_sources as S
R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:500]) if d and not ok else ""))
check("the Lab's store is scratch and sockets are refused", C.ROOT.startswith(HOME) and socket.socket.connect is _no)

sox = C._inquiry({"question": "What are the DNA-binding domains of the human SOX9 and SOX10 transcription factors?",
                  "uniprot_query": "gene:SOX9 AND organism_id:9606 AND reviewed:true"})
check("both named genes are fetched", sox["uniprot_query"] == "(gene:SOX9 OR gene:SOX10) AND taxonomy_id:9606 AND reviewed:true", sox["uniprot_query"])
check("the identity check is told the query that is sent", sox["identity_queries"][0] == sox["uniprot_query"])
one = C._inquiry({"question": "Which residues of human HMOX1 bind heme?", "uniprot_query": "gene:HMOX1 AND organism_id:9606 AND reviewed:true"})
check("a one-gene question is unchanged", one["uniprot_query"] == "gene:HMOX1 AND organism_id:9606 AND reviewed:true", one["uniprot_query"])
other = C._inquiry({"question": "Compare human SOX9 and SOX10 DNA-binding domains.",
                    "uniprot_query": "gene:SOX9 AND organism_id:10090 AND reviewed:true"})
check("a query for another organism is not rewritten", other["uniprot_query"] == "gene:SOX9 AND organism_id:10090 AND reviewed:true", other["uniprot_query"])

def rec(acc, gene, syn=(), name=""):
    return {"accession": acc, "taxon_id": 9606, "organism": "Homo sapiens", "protein_name": name,
            "genes": [{"geneName": {"value": gene}, "synonyms": [{"value": x} for x in syn]}]}
sox_records = [rec("P48436", "SOX9"), rec("P56693", "SOX10")]
ctx = S.question_entity_context(sox, sox_records)
check("two named genes, two records: each is established", ctx["status"] == "consistent"
      and ctx.get("target_mapping") == {"SOX9": "P48436", "SOX10": "P56693"}, ctx)

glut = C._inquiry({"question": "What are the extracellular loops of the human GLUT1 (SLC1A1) glucose transporter?",
                   "uniprot_query": "gene:SLC1A1 AND organism_id:9606 AND reviewed:true"})
ctx = S.question_entity_context(glut, [rec("P11166", "SLC2A1", ("GLUT1",)), rec("P43005", "SLC1A1", ("EAAC1", "EAAT3"))])
check("a wrong alias is refused with both identities named", ctx["status"] == "unresolved" and any(
      "GLUT1 and SLC1A1 as one protein" in i and "P11166" in i and "P43005" in i for i in ctx["issues"]), ctx["issues"])
right = C._inquiry({"question": "What are the extracellular loops of the human GLUT1 (SLC2A1) glucose transporter?",
                    "uniprot_query": "gene:SLC2A1 AND organism_id:9606 AND reviewed:true"})
ctx = S.question_entity_context(right, [rec("P11166", "SLC2A1", ("GLUT1",))])
check("a right alias passes", ctx["status"] == "consistent", ctx)
check("nothing reached the network", not NET, NET)
print("%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
