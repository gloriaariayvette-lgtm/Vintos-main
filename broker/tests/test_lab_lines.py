#!/usr/bin/env python3
"""His Lab follows a line of thought to its end, the frontier reviews steer it four times a day, and the phage
reverse-transcriptase screen works in one step (Gloria, 2026-10-03).

Scratch workspace; every socket refused; NCBI is a stub that serves fixed records; the frontier model is a stub; no
LM Studio, no GPU. HMMER runs for real only when hmmscan is installed (it is on Aegis), on a tiny model built here.
"""
import json, os, shutil, socket, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="lab-lines-")
WS = os.path.join(HOME, ".vintos", "workspace")
os.environ["HOME"] = HOME
os.environ["SPARK_WORKSPACE"] = WS
os.environ["VINTOS_PFAM"] = os.path.join(HOME, "pfam", "Pfam-A.hmm")
sys.path.insert(0, os.path.join(REPO, "scripts"))

NET = []
def _no_net(self, *a, **k):
    if self.family != socket.AF_UNIX: NET.append(a)
    raise OSError("this suite reaches nothing")
socket.socket.connect = _no_net

import lab_lines as LL, lab_crt, lab_hmm, lab_phage, lab_sources
import chemistry_lab as lab
import chemistry_frontier_bridge as bridge

R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:400]) if d and not ok else ""))

check("every store is in the scratch workspace",
      all(p.startswith(HOME) for p in (LL.STORE, LL.NOTEBOOK, LL.SESSIONS, lab_phage.LEDGER, lab.ROOT, bridge.INTEREST,
                                        lab_hmm.PFAM)))

# --- CRT, against minCED's own answers on a real genome -----------------------------------------------------
data = json.load(open(os.path.join(HERE, "data", "aquifex_crispr.json")))
for region in data["regions"]:
    want = region["minced"]
    got = [dict(a, start=a["start"] + region["genome_start"] - 1, end=a["end"] + region["genome_start"] - 1)
           for a in lab_crt.find_arrays(region["sequence"])]
    one = got[0] if len(got) == 1 else {}
    check("CRT finds the Aquifex array minCED finds at %d (%d repeats)" % (want["start"], want["repeats"]),
          len(got) == 1 and abs(one["start"] - want["start"]) <= 2 and abs(one["end"] - want["end"]) <= 2
          and one["repeats"] == want["repeats"] and want["repeat"][2:26] in one["repeat"], got)
import random
random.seed(7)
noise = "".join(random.choice("ACGT") for _ in range(12000))
check("CRT calls nothing in random sequence", lab_crt.find_arrays(noise) == [])
check("... nor in a tandem repeat (spacers that are copies of each other are not an array)",
      lab_crt.find_arrays(noise[:400] + "ACGTTGCAAGGT" * 120 + noise[:400]) == [])
rep = "GTTTCAATCCACGCGCCCACGCGGGGCGCGAC"
array_seq = noise[:3000] + "".join(rep + noise[5000 + 40 * k:5000 + 40 * k + 34] for k in range(6)) + rep + noise[3000:6000]
arr = lab_crt.find_arrays(array_seq)
check("CRT finds an array of 7 repeats where it was put", len(arr) == 1 and arr[0]["repeats"] == 7 and abs(arr[0]["start"] - 3001) <= 2, arr)

# --- the repeat screen's crash: a window over 12 kb no longer fails the read ---------------------------------
asked = []
def fake_record(url):
    asked.append(url)
    q = dict(x.split("=", 1) for x in url.split("?", 1)[1].split("&"))
    n = int(q.get("seq_stop", 0)) - int(q.get("seq_start", 0)) + 1
    return GB(q["id"], noise[:n] if n > 0 else noise[:500], [])
def GB(acc, seq, feats, extra=""):
    f = "".join("<GBFeature><GBFeature_key>%s</GBFeature_key><GBFeature_location>%s</GBFeature_location><GBFeature_quals>%s"
                "</GBFeature_quals></GBFeature>" % (k, loc, "".join("<GBQualifier><GBQualifier_name>%s</GBQualifier_name>"
                "<GBQualifier_value>%s</GBQualifier_value></GBQualifier>" % kv for kv in q.items()))
                for k, loc, q in feats)
    return ("<GBSet><GBSeq><GBSeq_accession-version>%s</GBSeq_accession-version><GBSeq_definition>%s</GBSeq_definition>"
            "<GBSeq_organism>Escherichia phage T9</GBSeq_organism><GBSeq_taxonomy>Viruses; Caudoviricetes</GBSeq_taxonomy>"
            "<GBSeq_length>%d</GBSeq_length><GBSeq_sequence>%s</GBSeq_sequence><GBSeq_feature-table>%s</GBSeq_feature-table>"
            "</GBSeq></GBSet>" % (acc, extra or "test record", len(seq), seq.lower(), f))
src = lab_sources.Sources(fetch_record=fake_record)
r = src.query({"source": "ncbi_neighborhood", "accession": "MW248466.1", "anchor_start": 3001, "anchor_end": 5000, "flank": 5000})
rec = r["records"][0]
check("a 2 kb gene with 5 kb flanks is read as at most 12 kb, and screened", rec["window_end"] - rec["window_start"] + 1 <= 12000
      and "error" not in rec["repeat_screen"] and rec["crispr_arrays"] == [], (rec["window_start"], rec["window_end"], rec["repeat_screen"]))

# --- the phage screen, in one step -----------------------------------------------------------------------------
RT = "M" + "".join(random.choice("ACDEFGHIKLMNPQRSTVWY") for _ in range(420))
CAS1 = "M" + "".join(random.choice("ACDEFGHIKLMNPQRSTVWY") for _ in range(300))
window = noise[:2000] + "".join(rep + noise[7000 + 40 * k:7000 + 40 * k + 34] for k in range(5)) + rep + noise[2000:9000]
fetched = []
def phage_record(url):
    fetched.append(url)
    if "db=protein" in url:
        return GB("WP_123456.1", RT, [("CDS", "1..421", {"coded_by": "NC_099999.1:6001..7266"})],
                  extra="reverse transcriptase [Escherichia phage T9]")
    return GB("NC_099999.1", window, [("CDS", "5001..6266", {"protein_id": "WP_123456.1", "product": "reverse transcriptase",
                                                              "translation": RT}),
                                      ("CDS", "complement(7000..7903)", {"protein_id": "WP_777.1", "product": "hypothetical protein",
                                                                         "translation": CAS1})])
hmm_calls = []
def hmm_stub(proteins):
    hmm_calls.append(sorted(proteins))
    return {"QUERY": [{"family": "RVT_1", "pfam": "PF00078.31", "evalue": 1e-30, "score": 120.0, "from": 60, "to": 300,
                       "description": "Reverse transcriptase (RNA-dependent DNA polymerase)"}],
            "WP_777.1": [{"family": "Cas_Cas1", "pfam": "PF01867.20", "evalue": 1e-40, "score": 150.0, "from": 5, "to": 290,
                          "description": "CRISPR associated protein Cas1"}]}
src = lab_sources.Sources(fetch_record=phage_record)
lab_phage_screen = lab_phage.screen
lab_phage.screen = lambda sources, spec: lab_phage_screen(sources, spec, hmm=hmm_stub)
r = src.query({"source": "rt_locus_screen", "accession": "WP_123456.1"})
rec = r["records"][0]
check("one query reads the protein, then its genome window", len(fetched) == 2 and "db=protein" in fetched[0] and "db=nuccore" in fetched[1])
check("the window is placed by coded_by and kept within 12 kb", rec["coded_by"] == {"accession": "NC_099999.1", "start": 6001,
      "end": 7266, "strand": "+"} and rec["window"]["end"] - rec["window"]["start"] + 1 <= 12000, rec["window"])
check("the CRISPR array beside it is found, in genome coordinates", len(rec["crispr_arrays"]) == 1
      and rec["crispr_arrays"][0]["repeats"] == 6 and rec["array_associated"], rec["crispr_arrays"])
check("the protein and every neighbor are scanned for domains", hmm_calls == [["QUERY", "WP_777.1"]], hmm_calls)
check("its reverse-transcriptase family and the Cas1 beside it are named", rec["reverse_transcriptase_domain"] == ["RVT_1"]
      and rec["cas_associated"] and rec["cas_genes"][0]["families"] == ["Cas_Cas1"], (rec["reverse_transcriptase_domain"], rec["cas_genes"]))
check("translations are kept from what he reads", "translation" not in json.dumps(rec["neighbors"]) and RT not in json.dumps(r))
check("the locus is kept in his screened-loci ledger", [x["protein"] for x in lab_phage.screened()] == ["WP_123456.1"])
before = len(fetched)
again = src.query({"source": "rt_locus_screen", "accession": "WP_123456.1"})["records"][0]
check("a locus already screened is not read again", again.get("already_screened") and len(fetched) == before)
check("what he has covered is shown to him", "LOCI YOU HAVE SCREENED" in lab_phage.coverage_block()
      and "1 beside a CRISPR array" in lab_phage.coverage_block())
lab_phage.screen = lab_phage_screen

# --- HMMER for real, when it is installed ---------------------------------------------------------------------
check("domtblout rows are parsed", lab_hmm.parse_domtbl(
    "RVT_1 PF00078.31 214 q1 - 421 1e-30 120.0 0.1 1 1 1e-33 1e-30 119.0 0.1 3 210 60 300 55 305 0.95 Reverse transcriptase\n")
    == {"q1": [{"family": "RVT_1", "pfam": "PF00078.31", "evalue": 1e-30, "score": 119.0, "from": 60, "to": 300,
                "description": "Reverse transcriptase"}]})
if shutil.which("hmmscan") and shutil.which("hmmbuild"):
    pf = os.path.dirname(lab_hmm.PFAM); os.makedirs(pf)
    motif = "".join(random.choice("ACDEFGHIKLMNPQRSTVWY") for _ in range(60))
    def mutate(s):
        return "".join(c if random.random() > 0.1 else random.choice("ACDEFGHIKLMNPQRSTVWY") for c in s)
    open(os.path.join(pf, "rt.sto"), "w").write("# STOCKHOLM 1.0\n" + "".join("s%d %s\n" % (i, mutate(motif)) for i in range(8)) + "//\n")
    subprocess.run(["hmmbuild", "-n", "RVT_1", "--amino", os.path.join(pf, "one.hmm"), os.path.join(pf, "rt.sto")], check=True, capture_output=True)
    text = open(os.path.join(pf, "one.hmm")).read().replace("\nCKSUM", "\nGA    10.00 10.00;\nCKSUM", 1)
    text = text.replace("NAME  RVT_1\n", "NAME  RVT_1\nACC   PF00078.99\nDESC  Reverse transcriptase (test model)\n", 1)
    open(lab_hmm.PFAM, "w").write(text)
    subprocess.run(["hmmpress", lab_hmm.PFAM], check=True, capture_output=True)
    hits = lab_hmm.scan({"carrier": RT[:100] + motif + RT[100:200], "decoy": CAS1})
    check("hmmscan finds the domain in the protein that carries it, by Pfam's gathering threshold, and not in the other",
          [d["family"] for d in hits.get("carrier", [])] == ["RVT_1"] and not hits.get("decoy") and lab_hmm.is_rt(hits["carrier"][0]), hits)
else:
    print("SKIP hmmscan is not installed here; the domain scan runs for real on Aegis")

# --- lines of inquiry -----------------------------------------------------------------------------------------
d = LL.load()
standing = next(l for l in d["lines"] if l["id"] == "L-gloria-phage-rt")
check("Gloria's phage reverse-transcriptase line is there from the start, standing", standing["standing"] and standing["state"] == "open"
      and "rt_locus_screen" in standing["next_step"])
mine = LL.opened_by("Aquaporin selectivity", "Why does the AQP3 pore pass glycerol when AQP1 does not?", "it keeps catching me")
check("he can open a line of his own", mine and mine["origin"] == "vintos")
check("... not the same question twice", LL.opened_by("again", "Why does the AQP3 pore pass glycerol when AQP1 does not?", "") is None)
picks = [LL.pick() for _ in range(8)]
ids = [p["id"] if p else None for p in picks]
check("one cycle in four is free curiosity; the rest work a line", ids.count(None) == 2 and ids[3] is None and ids[7] is None, ids)
line_ids = [i for i in ids if i]
check("Gloria's standing line is worked at least every other line-cycle",
      all("L-gloria-phage-rt" in line_ids[k:k + 2] for k in range(0, len(line_ids) - 1)), line_ids)
check("his own line is worked too", mine["id"] in line_ids, line_ids)

# a cycle on a line: its question is the line's next step, and his review may end it
LL.record_step(mine["id"], {"question": "AQP3 vs AQP1 pore residues", "source": "uniprot", "result": "AQP3 has a wider ar/R filter",
                            "answered": "partly", "next": "Compare the ar/R residues of AQP3 and AQP1 in their PDB structures"})
text = LL.orient_text(LL.get(mine["id"]))
check("the orient prompt carries the line, its tests and its next step", "THIS CYCLE WORKS THAT LINE" in text
      and "wider ar/R filter" in text and "Compare the ar/R residues" in text and mine["id"] in text)
check("a free cycle is told it may open a line", "FREE CYCLE" in LL.orient_text(None) and "new_line" in LL.orient_text(None))
out = LL.after_reflection(mine["id"], {"inquiry": {"question": "ar/R residues", "source_query": {"source": "pdb"}},
                                       "factual_observation": "AQP3's ar/R has Gly where AQP1 has His",
                                       "answers_question": "yes", "next_question": "",
                                       "line_status": "answered: the wider ar/R constriction (Gly for His) passes glycerol"})
check("his 'answered:' ends his own line, with the answer kept", "answered" in out and LL.get(mine["id"])["state"] == "answered"
      and "Gly for His" in LL.get(mine["id"])["verdict"], (out, LL.get(mine["id"])))
out = LL.after_reflection("L-gloria-phage-rt", {"inquiry": {"question": "phage RTs"}, "factual_observation": "two found",
                                                "answers_question": "partly", "line_status": "dropped: too hard"})
check("Gloria's standing line cannot be dropped by him", LL.get("L-gloria-phage-rt")["state"] == "open" and "kept" in out, out)
for _ in range(LL.STALLED_AFTER):
    LL.record_step("L-gloria-phage-rt", {"question": "q", "result": "", "answered": "no: nothing returned"})
check("tests that answer nothing are counted as stalls", LL.get("L-gloria-phage-rt")["stalls"] == LL.STALLED_AFTER
      and "change the test, not the words" in LL.line_block(LL.get("L-gloria-phage-rt")))

# --- the frontier review steers the lines -----------------------------------------------------------------------
applied = LL.steer([{"line_id": "L-gloria-phage-rt", "decision": "redirect", "note": "UniProt has none of these",
                     "next_step": "Search NCBI protein in Caudoviricetes for 'reverse transcriptase' and screen the first hit"},
                    {"line_id": "L-gloria-phage-rt", "decision": "drop", "note": "not getting anywhere"},
                    {"decision": "open", "title": "Retron msr-msd", "question": "Do phage retrons keep their msr-msd beside the RT?", "why": "it came up"}],
                   by="opus")
g = LL.get("L-gloria-phage-rt")
check("a redirect sets the line's next step and clears its stalls", "Caudoviricetes" in g["next_step"] and g["stalls"] == 0
      and g["steer"][-1]["by"] == "opus")
check("a frontier model cannot drop Gloria's line either", g["state"] == "open" and applied[1].get("refused"), applied)
check("a frontier model can open a line it sees in his work", applied[2].get("line_id") and LL.get(applied[2]["line_id"])["origin"] == "frontier:opus")
fb = LL.frontier_block()
check("the frontier review reads every open line with its tests", "L-gloria-phage-rt" in fb and "Retron msr-msd" in fb
      and "stalled_tests" in fb and mine["id"] not in fb)

import chemistry_alignment as AL
os.makedirs(lab.ROOT, exist_ok=True)
lab._atomic(lab.CONFIG, dict(lab.config(), enabled=True))
lab._append(lab.NOTEBOOK, {"at": "2026-10-03T20:00:00+00:00", "kind": "reflection", "entry_id": "CLF-1",
                           "inquiry": {"question": "phage RT families"}, "factual_observation": "two RTs"})
seen = []
def frontier(lens, provider, model, system, user, reservation):
    seen.append(user)
    return json.dumps({"summary": "s", "accuracy": [], "pattern": "p", "guidance": "g", "drop": "", "next_focus": "n",
                       "lines": [{"line_id": "L-gloria-phage-rt", "decision": "continue", "note": "keep screening"}]})
import compute_admission
compute_admission.reserve_paid = lambda *a, **k: (True, "")
import contextlib
compute_admission.admit = lambda *a, **k: contextlib.nullcontext()
row = AL.run(call=frontier)
check("the review four times a day is shown his lines and his tests", seen and "HIS OPEN LINES OF INQUIRY" in seen[0]
      and "YOUR RECENT TESTS" in seen[0], row)
check("... and its decision on each line is applied and kept", row.get("lines") == [{"decision": "continue", "line_id": "L-gloria-phage-rt"}]
      and LL.get("L-gloria-phage-rt")["steer"][-1]["note"] == "keep screening", row.get("lines"))
check("the next model reads which lines were steered", any(e.get("lines_steered") for e in AL.shared_log() if e["kind"] == "alignment"))

# --- his loop, on a line --------------------------------------------------------------------------------------
prompts = []
def ask(system, prompt, **kw):
    prompts.append(prompt)
    return json.dumps({"browse_lane": "genome_mining", "source_query": {"source": "rt_locus_screen", "accession": "WP_123456.1"},
                       "question": "Which family is the RT beside the array?", "why_now": "the line's next step",
                       "line_id": "L-gloria-phage-rt", "new_line": None})
lab._ask = ask
LL._write(dict(LL._read(), cycle=0, worked=[]))
inq = lab._orient("context")
check("a cycle on a line carries the line into his inquiry", inq.get("line_id") in {l["id"] for l in LL.open_lines()}
      and "THIS CYCLE WORKS THAT LINE" in prompts[-1] and "YOUR RECENT TESTS" in prompts[-1], inq)
check("the one-step phage screen is on his genome-mining menu", "rt_locus_screen" in prompts[-1])
def ask_free(system, prompt, **kw):
    prompts.append(prompt)
    return json.dumps({"browse_lane": "protein", "uniprot_query": "protein_name:ferritin", "question": "How does ferritin's shell breathe iron in and out?",
                       "why_now": "c", "new_line": {"title": "Ferritin breathing", "question": "How does ferritin's shell pass iron in and out?", "why": "it moved me"}})
lab._ask = ask_free
LL._write(dict(LL._read(), cycle=3))
inq = lab._orient("context")
check("on a free cycle his new_line opens a line, and the inquiry joins it", inq.get("line_opened")
      and LL.get(inq["line_id"])["title"] == "Ferritin breathing", inq)

# --- the priority score ---------------------------------------------------------------------------------------
note = {"at": "2026-10-03T21:00:00+00:00", "source_accessions": ["NC_099999.1"], "factual_observation": "an RT beside an array",
        "next_question": "Is the array's leader on the RT side?", "inquiry": {"question": "Does a phage RT sit beside a CRISPR array?",
                                                                           "line_id": "L-gloria-phage-rt"}}
row = bridge.assess(note, source_query_succeeded=True)
c = row["score_components"]
check("advancing an open line counts", c["advances_open_line"] == 0.25)
check("new ground counts, and the old ceiling is gone", c["new_territory"] > 0.25 and row["interest_score"] > 0.73, row)
check("the trajectory and collision terms are no longer scored", "trajectory_contact" not in c and "cross_organ_collision" not in c)
again = bridge.assess(dict(note, at="2026-10-03T21:01:00+00:00"), source_query_succeeded=True)
check("the same question again is old ground", again["score_components"]["new_territory"] == 0.0
      and again["interest_score"] < row["interest_score"], again["score_components"])

# --- his recent tests, shown to him -------------------------------------------------------------------------------
lab._append(lab.NOTEBOOK, {"at": "2026-10-03T21:05:00+00:00", "kind": "additional_source", "records_returned": 1,
                           "query_sent": {"source": "rt_locus_screen", "accession": "WP_123456.1"}})
tb = LL.tests_block()
check("his recent tests are listed with what came back", "rt_locus_screen WP_123456.1 -> 1 record(s)" in tb
      and "LOCI YOU HAVE SCREENED" in tb, tb)

check("the page calls it priority", "'priority '" in open(os.path.join(REPO, "clients", "mobile", "index.html")).read())
dep = open(os.path.join(REPO, "scripts", "deploy-atelier.sh")).read()
check("the deploy installs the new Lab modules", all(m in dep for m in ("lab_lines.py", "lab_crt.py", "lab_hmm.py", "lab_phage.py")))
check("nothing left the machine", not NET, NET)
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
