#!/usr/bin/env python3
"""UniProt and PubMed asked for in the planner's own words still run (16 October). From 21:26 to 23:26 CDT on 15
October, eight source failures were UniProt "plugin" routes the Lab refused (uniprot.none, uniprot.uniprot_search)
and three faults were "unsupported public PubMed search arguments". Pure functions; scratch HOME; no socket."""
import os, socket, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="lab-plugin-args-"); os.environ["HOME"] = HOME
os.environ["SPARK_WORKSPACE"] = os.path.join(HOME, ".vintos", "workspace")
NET = []
def _no(self, *a, **k): NET.append(a); raise OSError("this suite reaches nothing")
socket.socket.connect = _no
sys.path.insert(0, os.path.join(REPO, "scripts"))
import chemistry_lab as C
R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:400]) if d and not ok else ""))
check("the Lab's store is scratch and sockets are refused", C.ROOT.startswith(HOME) and socket.socket.connect is _no)
U = lambda args, tool="uniprot_search", purpose="": C.uniprot_from_plugin({"plugin": "uniprot", "tool": tool, "arguments": args}, purpose)
got = U({"query": "gene:SLC26A4 AND reviewed:true", "size": 3, "format": "json", "fields": "accession"})
check("a query with paging and formatting runs, its size kept as the limit",
      got and got["source"] == "uniprot" and got["query"].startswith("gene:SLC26A4") and got["limit"] == 3, got)
got = U({"search": "protein_name:Pendrin", "max_results": 50})
check("'search' is a query and a large limit is held to UniProt's 8", got and got["limit"] == 8 and "Pendrin" in got["query"], got)
got = U({"gene_name": "SLC26A4", "organism": "Homo sapiens"})
check("gene_name and organism are the source's gene and organism_name",
      got and 'gene:SLC26A4' in got["query"] and 'organism_name:"Homo sapiens"' in got["query"], got)
got = U({}, tool=None, purpose="What is the STAS domain of O43511 between residues 535 and 729?")
check("uniprot.none with one accession in the question reads that accession", got == {"source": "uniprot",
      "query": "accession:O43511", "limit": 1}, got)
check("uniprot.none with nothing named stays nothing", U({}, tool=None, purpose="What is the STAS domain?") is None)
try:
    U({"query": "gene:SLC26A4", "taxonomy": "9606; DROP"}); raised = ""
except ValueError as exc:
    raised = str(exc)
check("an argument that is not paging or formatting is still refused, and named", "taxonomy" in raised, raised)
P = lambda args: C.pubmed_from_plugin({"plugin": "pubmed", "tool": "search_articles", "arguments": args})
got = P({"query": "pendrin STAS domain structure", "max_results": 20, "sort": "relevance", "date_from": "2015"})
check("PubMed with paging, sort and dates runs, the limit held to 6",
      got and got["source"] == "pubmed_abstracts" and got["limit"] == 6 and "pendrin STAS domain structure" in got["terms"], got)
got = P({"term": "SLC26A4"})
check("a plain term runs as before, with no limit added", got == {"source": "pubmed_abstracts", "terms": ["SLC26A4"]}, got)
try:
    P({"query": "x", "journal_impact": "high"}); raised = ""
except ValueError as exc:
    raised = str(exc)
check("a PubMed argument that is not paging or dates is still refused, and named", "journal_impact" in raised, raised)
print("--- 16 October: bare UniProt requests, and literature searches that found nothing ---")
got = U({}, tool="uniprot.search", purpose="What are the specific structural features of the human SLC26A3 protein?")
check("a bare request on a question naming one human gene reads that gene",
      got and got["query"] == "gene:SLC26A3 AND organism_id:9606 AND reviewed:true", got)
check("a bare request on a question naming none stays nothing",
      U({}, tool="uniprot.search", purpose="What are Fe-S assembly proteins in thermophilic archaea?") is None)
import chemistry_sources as CS
try:
    CS.query_plugin("uniprot", "uniprot.search", {"foo": 1}, "What are Fe-S assembly proteins in archaea?"); raised = ""
except ValueError as exc:
    raised = str(exc)
except Exception as exc:
    raised = "WRONG: %s: %s" % (type(exc).__name__, exc)
check("a UniProt request naming nothing is refused plainly, never sent to the plugin gateway",
      raised.startswith("the UniProt request names nothing to look up") and "foo" in raised, raised)
import lab_sources as LS
forms = LS.literature_relaxations("thermophilic archaea sulfur disproportionation iron-sulfur cluster assembly structure")
check("a long literature phrase loosens: descriptive words out, then its first words",
      forms == ["thermophilic archaea sulfur disproportionation iron-sulfur cluster assembly",
                "thermophilic archaea sulfur disproportionation"], forms)
check("a short phrase has no looser form", LS.literature_relaxations("SufS structure") == [])
searched = []
from urllib.parse import unquote_plus
def fake_fetch(url, *a, **k):
    searched.append(url)
    if "esearch" in url:
        hit = "structure" not in unquote_plus(url)            # the whole phrase finds nothing; the looser one does
        return ({"esearchresult": {"idlist": ["123"] if hit else [], "count": "1" if hit else "0"}}, {})
    return ({"result": {"123": {"title": "SufS of Thermus"}}}, {})
try:
    rec = LS.Sources(fetch=fake_fetch).query({"source": "ncbi", "operation": "literature", "term": "Thermus thermophilus SufS structure sulfur metabolism"})
except Exception as exc:
    rec = {"error": "%s: %s" % (type(exc).__name__, exc)}
check("an empty literature search is tried again looser, and the receipt says which form found it",
      isinstance(rec, dict) and rec.get("records") and (rec.get("metadata") or {}).get("executed_term") == "Thermus thermophilus SufS sulfur metabolism"
      and (rec.get("query") or {}).get("term") == "Thermus thermophilus SufS structure sulfur metabolism", rec)
check("nothing reached the network", not NET, NET)
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
