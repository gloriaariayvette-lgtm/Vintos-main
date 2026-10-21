#!/usr/bin/env python3
"""The Lab poses a question nobody has written the answer to, and its own screen answers it (Gloria, 22 October:
"It can't be that difficult to produce a lab that poses novel questions and answers them. Look at how Anthropic got
Claude to find array-associated reverse transcriptase. That is what started his Lab." Her probe of the 21st: 0 of 14
"yes" reviews rested on anything his instruments produced; 1 instrument run of 25).

Scratch HOME and workspace; NCBI, the locus screen and Gemma are stubs; sockets are refused."""
import json, os, socket, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="lab-campaign-"); os.environ["HOME"] = HOME
os.environ["SPARK_WORKSPACE"] = os.path.join(HOME, ".vintos", "workspace")
NET = []
def _no(self, *a, **k): NET.append(a); raise OSError("this suite reaches nothing")
socket.socket.connect = _no
sys.path.insert(0, os.path.join(REPO, "scripts"))
import lab_campaign as L
R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + ("" if ok else "  ->  %r" % (str(d)[:400],)))
check("the campaign stores are scratch", all(p.startswith(HOME) for p in (L.STORE, L.FINDINGS, L.NOTEBOOK)))

class FakeNCBI:
    """Taxonomy and protein search, as NCBI's JSON answers them."""
    def __init__(self, n=30): self.n, self.urls = n, []
    def _taxon(self, spec): return {"Caudoviricetes": "2731619", "Archaea": "2157"}.get(spec.get("organism"))
    def fetch(self, url):
        self.urls.append(url)
        if "esearch" in url:
            return {"esearchresult": {"idlist": [str(1000 + i) for i in range(self.n)]}}, {}
        return {"result": {str(1000 + i): {"accessionversion": "QXP%05d.1" % i} for i in range(self.n)}}, {}

def fake_screen(sources, spec):
    """Every third locus beside an array; every sixth with a Cas1 too; a recurring neighbour on half of them."""
    i = int(spec["accession"][3:8])
    if i == 5: raise ValueError("the protein record names no coded_by location")
    rec = {"protein": spec["accession"], "organism": "phage %d" % (i % 7), "array_associated": i % 3 == 0,
           "cas_associated": i % 6 == 0, "nearest_array_bases": 400 + i if i % 3 == 0 else None,
           "domains": [{"family": "RVT_1"}],
           "cas_genes": [{"families": ["Cas_Cas1"]}] if i % 6 == 0 else [],
           "neighbor_families": {"p%d" % i: ["HNH"] if i % 2 == 0 else ["Phage_integrase"], "q": ["RVT_1"]},
           "domain_scan": "scanned"}
    return {"records": [rec]}

ASKED = []
def gemma(system, prompt):
    ASKED.append(prompt)
    if "Name ONE protein family" in prompt:
        return '{"family": "reverse transcriptase", "group": "Caudoviricetes", "why": "open", ' \
               '"prediction": "most will not sit beside an array"}'
    return ('{"pattern": "a third beside arrays", "prediction_vs_result": "confirmed: 8 of 24", '
            '"what_surprised_me": "HNH recurs", "next_question": "do the array-side ones share a family?"}')

ncbi = FakeNCBI()
first = L.step(ncbi, gemma, now="2026-10-22T10:00:00+00:00", screen=fake_screen)
data = L._load(); c = data["campaigns"][0]
check("with nothing open, a campaign is opened from Gemma's family and group, with its prediction",
      c["family"] == "reverse transcriptase" and c["group"] == "Caudoviricetes" and c["prediction"] and c["by"] == "gemma", c)
check("its proteins come from NCBI's search of that taxon, not invented",
      c["taxon_id"] == "2731619" and len(c["accessions"]) == 30 and "txid2731619" in ncbi.urls[0], ncbi.urls[:1])
check("its question is one the screen answers, not a lookup",
      c["question"].startswith("Across the first 24 reverse transcriptase proteins screened in Caudoviricetes genomes"))
check("and the same turn screens its first locus", first.get("protein") == "QXP00000.1" and first["array"] is True, first)

outs = [first] + [L.step(ncbi, gemma, now="2026-10-22T10:%02d:00+00:00" % k, screen=fake_screen) for k in range(1, 40)]
c = L._load()["campaigns"][0]
found = [json.loads(l) for l in open(L.FINDINGS)]
check("a locus that cannot be screened is skipped with its reason, not retried",
      [s["protein"] for s in c["skipped"]] == ["QXP00005.1"] and "coded_by" in c["skipped"][0]["why"], c["skipped"])
check("a finding after every 8 loci, and the campaign closes at 24",
      [f["result"]["loci"] for f in found[:3]] == [8, 16, 24] and c["state"] == "closed", [f["result"]["loci"] for f in found])
t = found[2]["result"]
check("the finding is the screen's own counts",
      t["beside_crispr_array"] == sum(1 for i in range(25) if i != 5 and i % 3 == 0)
      and t["beside_cas_gene"] == sum(1 for i in range(25) if i != 5 and i % 6 == 0)
      and t["array_and_cas"] == t["beside_cas_gene"], t)
check("recurring neighbours are counted per locus, the protein's own family left out",
      dict(t["recurring_neighbours"]).get("HNH") == sum(1 for i in range(25) if i != 5 and i % 2 == 0) and "RVT_1" not in dict(t["recurring_neighbours"]), t["recurring_neighbours"])
check("Gemma reads the numbers beside its prediction; the numbers stand on their own",
      found[2]["reading"]["prediction_vs_result"].startswith("confirmed") and found[2]["new_result"] is True)
check("a finding says it is a candidate association, not a function", "not function" in found[2]["truth_status"])
check("after it closes, the next campaign is a different family and group",
      L._load()["campaigns"][-1]["family"] + L._load()["campaigns"][-1]["group"] != "reverse transcriptaseCaudoviricetes",
      [(x["family"], x["group"]) for x in L._load()["campaigns"]])
nb = [json.loads(l) for l in open(L.NOTEBOOK)]
check("his notebook holds the plan, every screen and every finding",
      [r["kind"] for r in nb].count("campaign_open") >= 1 and [r["kind"] for r in nb].count("campaign_screen") >= 24
      and [r["kind"] for r in nb].count("campaign_finding") >= 3)
check("his Lab context shows the finding in words", "beside a CRISPR array" in L.findings_block() and "HNH" in L.findings_block(),
      L.findings_block())

# The day's limit, and a group NCBI does not know
d = L._load(); d["screens"]["2026-10-23"] = L.DAILY_SCREENS; L._save(d)
check("past the day's screens the turn goes back to the ordinary loop",
      L.step(ncbi, gemma, now="2026-10-23T09:00:00+00:00", screen=fake_screen)["kind"] == "campaign_rest")
os.remove(L.STORE)
bad = lambda s, p: '{"family": "reverse transcriptase", "group": "Nowhereia", "why": "x", "prediction": "y"}'
out = L.step(FakeNCBI(), bad, now="2026-10-24T09:00:00+00:00", screen=fake_screen)
camps = L._load()["campaigns"]
check("a group NCBI has no taxon for is not screened; an open corner from the list is",
      camps[0]["state"] == "unworkable" and any(x["state"] == "open" and x["by"] == "seed" for x in camps), camps)

# The minute loop hands a turn to a campaign
import chemistry_lab as C
check("the Lab's own stores are scratch too", C.ROOT.startswith(HOME))
C._append(C.NOTEBOOK, {"at": "2026-10-24T09:01:00+00:00", "kind": "inquiry_refused", "why": "repeat: spent subject"})
check("after a pass that ended without a source call, the next turn is a campaign", C._campaign_due({"turns": 7}, {}))
C._append(C.NOTEBOOK, {"at": "2026-10-24T09:02:00+00:00", "kind": "reflection", "answers_question": "no"})
check("otherwise every other turn", C._campaign_due({"turns": 8}, {}) and not C._campaign_due({"turns": 7}, {}))
check("and it can be turned off", not C._campaign_due({"turns": 8}, {"campaigns": False}))
check("a campaign finding ends a dead-end run, as an answered review does",
      C.dead_ends([{"kind": "inquiry", "inquiry": {"uniprot_query": "gene:KAIC"}}] * 3 + [{"kind": "campaign_finding"}])["count"] == 0)
src = open(os.path.join(REPO, "scripts", "chemistry_lab.py")).read()
check("tick asks for a campaign before the ordinary orient", src.index("_campaign_due(state, cfg)") < src.index("inquiry = _orient(context, lean)"))
check("nothing reached the network", not NET)
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
