#!/usr/bin/env python3
"""A wrong premise in a planned question (16 October): "human SlyA" (a bacterial regulator) was searched and reviewed
before anything noticed. Now a bacterial-style name in a human question is checked against NCBI Gene at admission,
the planner is told once what was wrong and asked again, and the names that failed are shown to it after. The NCBI
check and the planner are stubs; scratch HOME; no socket."""
import json, os, socket, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="lab-wrong-premise-"); os.environ["HOME"] = HOME
os.environ["SPARK_WORKSPACE"] = os.path.join(HOME, ".vintos", "workspace")
NET = []
def _no(self, *a, **k): NET.append(a); raise OSError("this suite reaches nothing")
socket.socket.connect = _no
sys.path.insert(0, os.path.join(REPO, "scripts"))
import chemistry_lab as C, lab_repeats as L, lab_sources as LS
R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:500]) if d and not ok else ""))
check("the Lab's stores are scratch and sockets are refused", C.ROOT.startswith(HOME) and L.LOOKUPS.startswith(HOME))
HUMAN = {"ISCU", "SLC26A4", "TAS1R3"}
CHECKED = []
def identity(self, symbol):
    CHECKED.append(symbol)
    ok = symbol.upper() in HUMAN
    return LS.receipt("ncbi_gene_identity", {"symbol": symbol, "taxon_id": 9606}, [{"symbol": symbol}] if ok else [],
                      metadata={"status": "verified" if ok else "unresolved"})
LS.Sources.human_gene_identity = identity
g = C._ground_inquiry({"question": "What are the structural motifs of the human SlyA protein in inflammatory signaling?"})
check("a bacterial-style name in a human question is checked, and refused", g["status"] == "unresolved" and "SLYA" in CHECKED, g)
CHECKED.clear()
g = C._ground_inquiry({"question": "What is the structure of the human IscU scaffold protein?"})
check("a human gene written that way still verifies", g["status"] == "verified" and CHECKED == ["ISCU"], g)
CHECKED.clear()
g = C._ground_inquiry({"question": "What does SlyA regulate in Salmonella enterica?"})
check("the same name outside a human question is not checked as human", g["status"] == "not_applicable" and not CHECKED, g)

print("--- the planner is told once, and asks again ---")
asks = []
answers = [json.dumps({"browse_lane": "protein", "question": "What are the structural motifs of the human TAS1R3 protein?",
                       "uniprot_query": "gene:TAS1R3 AND organism_id:9606"})]
C._ask = lambda system, task, **k: (asks.append(task), answers.pop(0))[1]
first = C._inquiry({"browse_lane": "microbiology", "question": "What are the structural motifs of the human SlyA protein?",
                    "source_query": {"source": "ncbi", "operation": "literature", "term": "human SlyA structure"}})
inq, _ = C._held_to_plan("sys", "TASK", first, {}, None, None, L)
check("the wrong premise goes back to the planner named, and its corrected question is the one admitted",
      len(asks) == 1 and "REFUSED, A WRONG PREMISE" in asks[0] and "SLYA" in asks[0]
      and not inq.get("refused") and "TAS1R3" in inq.get("question", ""), (asks, inq))
check("the name that failed is remembered and shown to the planner from now on", "SLYA" in L.not_human_symbols())
answers[:] = [json.dumps({"browse_lane": "protein", "question": "What are the structural motifs of the human SufS protein?",
                          "uniprot_query": "gene:SufS AND organism_id:9606"})]
asks.clear()
inq, _ = C._held_to_plan("sys", "TASK", C._inquiry({"browse_lane": "protein", "question": "What is the human RecA fold?",
                                                     "uniprot_query": "gene:RecA AND organism_id:9606"}), {}, None, None, L)
check("a retry that is wrong too is refused, once, not asked again", len(asks) == 1 and inq.get("refused"), inq.get("refused"))
check("nothing reached the network", not NET, NET)
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
