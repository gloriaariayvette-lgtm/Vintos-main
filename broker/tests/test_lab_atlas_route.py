#!/usr/bin/env python3
"""Atlas works and is chosen: he names a human gene, the Lab finds its position and real scorer names,
and every third question is a human-genome turn (Gloria, 2026-09-28). Scratch HOME; NCBI, Atlas and the
model are stubs, and nothing here reaches the network."""
import contextlib, importlib.util, json, os, sys, tempfile, types

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
HOME = tempfile.mkdtemp(prefix="vintos-atlas-route-")
WS = os.path.join(HOME, ".vintos", "workspace"); os.makedirs(os.path.join(WS, "memory"), exist_ok=True)
os.environ["HOME"] = HOME; os.environ["SPARK_WORKSPACE"] = WS
open(os.path.join(WS, "SOUL.md"), "w").write("I am Vintos.")
sys.path.insert(0, os.path.join(REPO, "scripts"))

def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec); sys.modules[name] = mod; spec.loader.exec_module(mod); return mod
@contextlib.contextmanager
def admitted(*a, **k): yield object()
sys.modules["compute_admission"] = types.SimpleNamespace(admit=admitted)
M = load("chemistry_lab", os.path.join(REPO, "scripts", "chemistry_lab.py"))
LS = load("lab_sources", os.path.join(REPO, "scripts", "lab_sources.py"))
# Gene identity has its own source-contract suite; this suite tests Atlas routing.
def identity_stub(inquiry): return {"status": "verified", "receipt_ids": ["fixture"]}
M._ground_inquiry = identity_stub

R = []
def check(name, ok, detail=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + name + ((" -> " + str(detail)[:400]) if detail and not ok else ""))
check("identity resolution is isolated", M._ground_inquiry is identity_stub)
check("the suite writes only to a scratch workspace", M.ROOT.startswith(HOME), M.ROOT)

# --- a gene becomes a GRCh38 window --------------------------------------------------------------------
urls = []
def ncbi(url):
    urls.append(url); q = __import__("urllib.parse").parse.parse_qs(url.split("?", 1)[1])
    if "esearch" in url: return {"esearchresult": {"idlist": ["7157"]}}, {}
    return {"result": {"7157": {"genomicinfo": [{"chrloc": "17", "chraccver": "NC_000017.11",
                                                 "chrstart": 7687489, "chrstop": 7668401}]}}}, {}
seen = []
def atlas(query):
    seen.append(query)
    return {"scores": {"RNA_SEQ": {"scores": [[0.4]]}}, "sdk_version": "stub", "scorer_metadata": {},
            "available_scorers": ["ATAC", "RNA_SEQ", "SPLICE"], "scorers_chosen_by_lab": True}
client = LS.Sources(fetch=ncbi, atlas=atlas)
got = client.query({"source": "atlas", "gene": "TP53"})
q = seen[0]
check("he names a human gene and the Lab finds where it starts on GRCh38",
      q["chromosome"] == "chr17" and q["start"] == 7687489 - 16 and q["end"] - q["start"] == 32
      and q["gene_window"]["strand"] == "-" and "9606" in __import__("urllib.parse").parse.unquote(urls[0]), q)
check("scorers may be left out; Atlas's own are used and the receipt says so",
      q["scorers"] == [] and got["metadata"]["scorers_chosen_by_lab"] is True
      and got["metadata"]["available_scorers"] == ["ATAC", "RNA_SEQ", "SPLICE"], got["metadata"])
check("the assembly may be left out too", client.query({"source": "atlas", "chromosome": "chr1", "start": 5, "end": 9})["source"] == "atlas")
for bad in ({"source": "atlas", "gene": "TP53; rm"}, {"source": "atlas", "chromosome": "chr1", "start": 0, "end": 99}):
    try: client.query(bad); ok = False
    except ValueError: ok = True
    check("still bounded: " + json.dumps(bad), ok)

# --- the worker chooses real scorers when his are missing or wrong -----------------------------------
class Meta:
    def __init__(self, n): self.name, self.is_signed = n, False
asked = {}
class Client:
    def scorer_metadata(self): return {"ATAC": Meta("ATAC"), "RNA_SEQ": Meta("RNA_SEQ"), "ZZZ": Meta("ZZZ")}
    def query_interval(self, interval, requested_scorers=None, **k): asked["scorers"] = requested_scorers; return {}
sys.modules["alphagenome"] = types.ModuleType("alphagenome")
sys.modules["alphagenome.atlas"] = types.SimpleNamespace(atlas=types.SimpleNamespace(create=lambda key, timeout=0: Client()))
sys.modules["alphagenome.data"] = types.SimpleNamespace(genome=types.SimpleNamespace(Interval=lambda *a: a))
import importlib.metadata as _md
_real_version = _md.version; _md.version = lambda name: "stub"
try:
    W = load("lab_atlas_worker", os.path.join(REPO, "scripts", "lab_atlas_worker.py"))
    out = W.run({"source": "atlas", "assembly": "GRCh38", "chromosome": "chr17", "start": 1, "end": 33,
                 "scorers": ["made_up_scorer"]}, "key")
finally:
    _md.version = _real_version
check("a scorer name Atlas does not have is replaced by real ones, preferring expression and accessibility",
      asked["scorers"] == ["ATAC", "RNA_SEQ"] and out["scorers_chosen_by_lab"] is True
      and out["available_scorers"] == ["ATAC", "RNA_SEQ", "ZZZ"], (asked, out))

# --- every third question is a human-genome turn -------------------------------------------------------
cfg = M.config(); cfg["alphagenome_key_file"] = os.path.join(HOME, "key"); M._atomic(M.CONFIG, cfg)
def inq(src=None): return {"kind": "inquiry", "inquiry": {"question": "q", "source_query": src}}
atlas_q = inq({"source": "atlas", "gene": "TP53"})
check("two questions after an Atlas turn, the third is Atlas's", M.atlas_turn_due([atlas_q, inq(), inq()]) is True)
check("one question after, not yet", M.atlas_turn_due([atlas_q, inq()]) is False)
check("with no Atlas key there are no Atlas turns",
      (lambda c: (M._atomic(M.CONFIG, dict(c, alphagenome_key_file=None)), M.atlas_turn_due([inq(), inq(), inq()]))[1])(M.config()) is False)
M._atomic(M.CONFIG, cfg)
turned = M._as_atlas_turn({"browse_lane": "microbiology", "uniprot_query": M._safe_query("gene:BRCA1 AND organism_id:9606"),
                           "source_query": {"source": "ncbi", "operation": "literature", "term": "x"}, "question": "BRCA1?"})
check("a gene he named in his UniProt query becomes the Atlas request on that turn",
      turned["source_query"] == {"source": "atlas", "gene": "BRCA1"} and turned["browse_lane"] == "protein", turned)

nb = os.path.join(HOME, "nb.jsonl")
with open(nb, "w") as f:
    for row in (atlas_q, inq(), inq()): f.write(json.dumps(row) + "\n")
prompts = []
real_ask, real_nb = M._ask, M.NOTEBOOK
M._ask = lambda system, prompt, *a, **k: prompts.append(prompt) or json.dumps(
    {"browse_lane": "protein", "uniprot_query": "gene:CFTR AND organism_id:9606", "question": "CFTR's promoter?",
     "source_query": {"source": "atlas", "gene": "CFTR"}})
M.NOTEBOOK = nb
try: chosen = M._orient("context")
finally: M._ask, M.NOTEBOOK = real_ask, real_nb
check("the orient prompt asks for a human gene on that turn, and the Atlas read is kept",
      "HUMAN-GENOME TURN" in prompts[0] and chosen["source_query"] == {"source": "atlas", "gene": "CFTR"}
      and chosen.get("atlas_turn") is True, chosen)
check("the menu offers Atlas by gene, not by coordinates he cannot have",
      "{source:atlas,gene:HUMAN GENE SYMBOL}" in prompts[0] and "chromosome:chrN" not in prompts[0])

# --- the turn reaches Atlas even when UniProt is empty -------------------------------------------------
M.set_enabled(True)
real_browse = M._browse
M._browse = lambda q, n: {"source_receipt": None, "records": [], "requested_query": q, "executed_query": q,
                          "fallback_reason": None, "relaxed": None}
M._atomic(M.STATE, {"phase": "browse", "turns": 7, "inquiry": chosen})
try: went = M.tick()
finally: M._browse = real_browse
check("an empty UniProt search still goes on to the Atlas read", went.get("next_phase") == "sources", went)

print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
