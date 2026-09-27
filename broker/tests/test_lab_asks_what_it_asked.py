#!/usr/bin/env python3
"""The Lab sends the question he actually asked, and stops when the source has no answer.

2026-09-26, from her review of 30 notebook entries: he asked eight times for the S-layer protein of
Lactobacillus acidophilus. The Lab sent "every reviewed protein of this organism" instead, the same
first record came back each time — a bile-salt enzyme — and he wrote it down as the S-layer protein.
The repetition guard did not run in this lane, and every reflection opened a Forge project to
document the question.

Scratch HOME; the source client and both model calls are stubs; nothing here reaches the network.
"""
import re, contextlib, importlib.util, json, os, sys, tempfile, time, types

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
HOME = tempfile.mkdtemp(prefix="vintos-lab-intent-")
WS = os.path.join(HOME, ".vintos", "workspace")
os.makedirs(os.path.join(WS, "memory"), exist_ok=True)
os.environ["HOME"] = HOME; os.environ["SPARK_WORKSPACE"] = WS
open(os.path.join(WS, "SOUL.md"), "w").write("I am Vintos.")

spec = importlib.util.spec_from_file_location("chemistry_lab_intent_test", os.path.join(REPO, "scripts", "chemistry_lab.py"))
M = importlib.util.module_from_spec(spec); spec.loader.exec_module(M)
sys.modules["chemistry_lab"] = M

R = []
def check(name, ok, detail=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + name + ((" -> " + str(detail)[:300]) if detail and not ok else ""))

check("the suite runs in a scratch workspace", M.WS == WS and HOME in M.ROOT and not M.ROOT.startswith("/home/gloria"), M.ROOT)

@contextlib.contextmanager
def admitted(*a, **k): yield types.SimpleNamespace()
sys.modules["compute_admission"] = types.SimpleNamespace(admit=admitted)
M.set_enabled(True)
cfg = M.config(); cfg["forge_report_intake"] = {"url": "http://127.0.0.1:9/api/lab-intake", "token_file": "x"}
M._atomic(M.CONFIG, cfg)
M._atomic(M.KNOWN_TAXA, ["1579"])   # an organism a receipt has returned; guessed IDs are tested below

# --- the query he wrote is the query that is sent -------------------------------------------------
HIS_UNIPROT = 'reviewed:true AND length:[40 TO 350] AND (protein_name : S-layer protein organism_id : 1579 reviewed : True)'
BROAD = {"source": "uniprot", "query": "taxonomy_id:1579 AND reviewed:true"}
merged = M.merge_source_intent(BROAD, HIS_UNIPROT)
check("the protein he named is carried into the query that is sent",
      merged["query"] == 'taxonomy_id:1579 AND reviewed:true AND protein_name:"S-layer protein"', merged)
check("a gene he named is carried too",
      M.merge_source_intent(BROAD, "reviewed:true AND (gene:slpA taxonomy_id:1579)")["query"].endswith("gene:slpA"))
check("a query naming no protein is left exactly as it is",
      M.merge_source_intent(BROAD, "reviewed:true AND length:[40 TO 350]") == BROAD)
check("a protein_name already in the sent query is not doubled",
      M.merge_source_intent({"source": "uniprot", "query": 'protein_name:"S-layer"'}, HIS_UNIPROT)["query"]
      == 'protein_name:"S-layer"')
check("another source's query is untouched",
      M.merge_source_intent({"source": "ncbi", "operation": "taxonomy", "term": "x"}, HIS_UNIPROT)["term"] == "x")

sent, reply = [], {"receipt": {"receipt_id": "REC-1", "response_sha256": "b" * 64,
                               "records": [{"primaryAccession": "Q1", "protein_name": "S-layer protein A"}]}}
def fake_query(spec_, question="", **k):
    sent.append(spec_); return reply
sys.modules["chemistry_sources"] = types.SimpleNamespace(query=fake_query, flush_reports=lambda: None)

REAL_ORIENT = M._orient   # the dead-end section below calls the real one
M._orient = lambda context, lean=None: {"browse_lane": "microbiology", "source_query": dict(BROAD),
                                        "uniprot_query": HIS_UNIPROT, "plugin_query": None,
                                        "question": "What is the S-layer protein sequence?", "why_now": "to probe it"}
REFLECTION = {"attention": "the S-layer record", "factual_observation": "it is 444 residues",
              "speculative_reading": "the repeats may tile the surface", "next_question": "how do they pack?",
              "answers_question": "yes", "instrument_gap": ""}
M._reflect = lambda context, inquiry, records: dict(REFLECTION)

M.tick()                      # orient
route = M.tick()              # browse_route
source_turn = M.tick()        # sources
check("the loop reaches the source step", (route["kind"], source_turn["kind"]) == ("browse_route", "additional_source"),
      (route, source_turn))
check("the request carries the protein he asked about, not the whole organism",
      sent and sent[-1]["query"] == 'taxonomy_id:1579 AND reviewed:true AND protein_name:"S-layer protein"', sent)
note = M._jsonl(M.NOTEBOOK)[-1]
check("the notebook records the query that was actually sent", note.get("query_sent") == sent[-1], note.get("query_sent"))
check("a record that came back is reflected on", source_turn["next_phase"] == "reflect" and note["records_returned"] == 1)
reflected = M.tick()
check("the reflection is written", reflected["kind"] == "reflection")

# --- a source that holds no such record has answered him ------------------------------------------
reply = {"receipt": {"receipt_id": "REC-EMPTY", "response_sha256": "c" * 64, "records": []}}
M.tick(); M.tick()
empty = M.tick()
note = M._jsonl(M.NOTEBOOK)[-1]
check("an empty result is named as the source holding no such record, not reflected on",
      empty["next_phase"] == "orient" and note["records_returned"] == 0
      and note["truth_status"] == "this_source_holds_no_such_record_not_an_absence_in_nature", note)

# --- the same response twice is not new evidence --------------------------------------------------
reply = {"receipt": {"receipt_id": "REC-2", "response_sha256": "d" * 64, "records": [{"primaryAccession": "Q2"}]}}
M.tick(); M.tick(); M.tick(); M.tick()          # orient, route, sources, reflect
M.tick(); M.tick()                              # orient, route
repeat = M.tick()                               # the identical response again
note = M._jsonl(M.NOTEBOOK)[-1]
check("an identical response set redirects instead of reflecting again",
      repeat["next_phase"] == "orient" and note.get("saturation_redirect") is True
      and note["truth_status"] == "unchanged_source_set_not_new_evidence", note)
check("the saturation guard still allows the protein lane its five looks",
      M.journal_source_saturated(["RESPONSE-" + "d" * 32], limit=1)
      and not M.journal_source_saturated(["RESPONSE-" + "d" * 32]), "limit is honoured")

# --- a source still cooling down is waited for, not spent -----------------------------------------
M._atomic(M.STATE, {"phase": "sources", "turns": 50, "inquiry": {
    "browse_lane": "microbiology", "source_query": dict(BROAD), "uniprot_query": HIS_UNIPROT, "question": "q"}})
M._atomic(os.path.join(M.ROOT, "source-throttle.json"), {"uniprot": __import__("time").time() + 45})
rows_before, sent_before = len(M._jsonl(M.NOTEBOOK)), len(sent)
waited = M.tick()
check("a source in its cooldown is waited out without spending the question",
      waited["state"] == "waiting_for_source" and M._load(M.STATE, {})["phase"] == "sources"
      and len(M._jsonl(M.NOTEBOOK)) == rows_before and len(sent) == sent_before, waited)
os.unlink(os.path.join(M.ROOT, "source-throttle.json"))

# --- an organism ID no receipt ever returned is not sent ------------------------------------------
M._atomic(M.STATE, {"phase": "sources", "turns": 51, "inquiry": {
    "browse_lane": "microbiology", "source_query": {"source": "uniprot", "query": "taxonomy_id:512419 AND reviewed:true"},
    "uniprot_query": HIS_UNIPROT, "question": "q"}})
guessed = M.tick()
note = M._jsonl(M.NOTEBOOK)[-1]
check("a guessed organism ID is refused before any request",
      guessed["next_phase"] == "orient" and note["kind"] == "unsourced_id" and note["ids"] == ["512419"]
      and len(sent) == sent_before, note)
check("an NCBI taxon_id is held to the same rule",
      M.unsourced_ids({"source": "ncbi", "operation": "gene", "taxon_id": 424242}) == ["424242"]
      and M.unsourced_ids({"source": "ncbi", "operation": "taxonomy", "term": "L. acidophilus"}) == [])
M.remember_taxa([{"organism": {"taxonId": 272621}}, {"uid": "33958"}])
check("an ID a receipt returns becomes one he may use",
      M.unsourced_ids({"source": "uniprot", "query": "taxonomy_id:272621"}) == []
      and "33958" in M.known_taxa())

# --- the searches that found nothing are shown to him ---------------------------------------------
ctx, _ = M.lab_context()
check("his planning context lists the searches that found nothing, and why",
      "SEARCHES THAT FOUND NOTHING" in ctx and "the source holds no such record" in ctx
      and "512419" in ctx and "look the organism up by name first" in ctx, ctx[-900:])

# --- the Forge is asked for an instrument, never for documentation --------------------------------
offers = []
sys.modules["chemistry_sources"] = types.SimpleNamespace(
    query=fake_query, flush_reports=lambda: None,
    offer_report=lambda ids, intent, **k: offers.append((ids, intent)) or {"id": "P-1"})
reply = {"receipt": {"receipt_id": "REC-3", "response_sha256": "e" * 64, "records": [{"primaryAccession": "Q3"}]}}
M.tick(); M.tick(); M.tick(); M.tick()
check("a reflection that needs nothing new opens no Forge project", offers == [], offers)

M._reflect = lambda context, inquiry, records: dict(REFLECTION, instrument_gap="a circular dichroism reading to see the fold")
reply = {"receipt": {"receipt_id": "REC-4", "response_sha256": "f" * 64, "records": [{"primaryAccession": "Q4"}]}}
M.tick(); M.tick(); M.tick(); M.tick()
check("a named missing instrument does open one, as a capability request",
      len(offers) == 1 and offers[0][1].startswith("The Lab needs an instrument it does not have:")
      and "circular dichroism" in offers[0][1] and "Document this sourced Lab question" not in offers[0][1], offers)

reply = {"receipt": {"receipt_id": "REC-5", "response_sha256": "a" * 64, "records": [{"primaryAccession": "Q5"}]}}
M.tick(); M.tick(); M.tick(); M.tick()
check("the same instrument is not asked for twice", len(offers) == 1, offers)
check("the notebook shows what he asked the Forge for",
      any(x.get("forge_report") for x in M._jsonl(M.NOTEBOOK) if x.get("kind") == "reflection"))

def refusing(ids, intent, **k):
    offers.append((ids, intent)); raise OSError("403 four unfinished reports")
sys.modules["chemistry_sources"].offer_report = refusing
M._reflect = lambda context, inquiry, records: dict(REFLECTION, instrument_gap="a mass spectrometer for the glycan")
for n, h in (("REC-6", "1"), ("REC-7", "2")):
    reply = {"receipt": {"receipt_id": n, "response_sha256": h * 64, "records": [{"primaryAccession": n}]}}
    M.tick(); M.tick(); M.tick(); M.tick()
check("a request the full Forge refused is not queued again on every later reflection",
      sum("mass spectrometer" in o[1] for o in offers) == 1, [o[1][:60] for o in offers])

# --- a gene symbol written as a protein name is read as the gene it is -----------------------------
import urllib.error as _ue
asked = []
class _R:
    def __init__(self, body): self.body = json.dumps(body).encode()
    def read(self, n=-1): return self.body
    def __enter__(self): return self
    def __exit__(self, *a): return False
def fake_urlopen(req, timeout=0):
    q = __import__("urllib.parse").parse.parse_qs(req.full_url.split("?", 1)[1])["query"][0]
    asked.append(q)
    if "gene:RPS16" in q or "gene:KaiC" in q:
        return _R({"results": [{"primaryAccession": "P62249", "uniProtkbId": "RS16_HUMAN",
                                "sequence": {"length": 146, "value": "M" * 146}}]})
    return _R({"results": []})
_real = M.urllib.request.urlopen
M.urllib.request.urlopen = fake_urlopen
try:
    got = M._browse("reviewed:true AND (protein_name:RPS16 AND organism_id:9606)", 4)
    kaic = M._browse('reviewed:true AND (protein_name:"KaiC" AND organism_id:1140)', 4)
    none = M._browse('reviewed:true AND (protein_name:"Clarin 2" AND organism_id:9606)', 4)
finally:
    M.urllib.request.urlopen = _real
check("protein_name:RPS16 that finds nothing is tried once as gene:RPS16",
      [r["accession"] for r in got["records"]] == ["P62249"] and "gene:RPS16" in got["executed_query"]
      and "gene:RPS16" in asked[1], (asked, got["executed_query"]))
check("a mixed-case gene name like KaiC, even quoted, is tried as the gene too",
      kaic["records"] and "gene:KaiC" in kaic["executed_query"], (asked, kaic["executed_query"]))
check("a multi-word protein name is not reread as a gene", none["records"] == [] and "gene:" not in asked[-1], asked)

# --- a protein longer than 350 residues can be found at all (KaiC is 519) --------------------------
def length_aware_urlopen(req, timeout=0):
    q = __import__("urllib.parse").parse.parse_qs(req.full_url.split("?", 1)[1])["query"][0]
    asked.append(q)
    lo, hi = map(int, re.search(r"length:\[(\d+) TO (\d+)\]", q).groups())
    if "KaiC" in q and lo <= 519 <= hi:   # what UniProt does: the length range filters first
        return _R({"results": [{"primaryAccession": "Q79PF4", "uniProtkbId": "KAIC_SYNE7",
                                "sequence": {"length": 519, "value": "A" * 519}}]})
    return _R({"results": []})
M.urllib.request.urlopen = length_aware_urlopen
try:
    long_one = M._browse(M._safe_query('gene:kaiC AND protein_name:"KaiC"'), 4)
finally:
    M.urllib.request.urlopen = _real
check("the Lab's own length perimeter admits KaiC (519 residues)",
      [r["accession"] for r in long_one["records"]] == ["Q79PF4"], (asked[-2:], long_one["executed_query"]))
check("its full length is recorded but only 350 residues go on to ESM-C",
      long_one["records"] and long_one["records"][0]["length"] == 519
      and len(long_one["records"][0]["sequence"]) == 350)

# --- he may not substitute a different protein for the one asked about ----------------------------
src = open(os.path.join(REPO, "scripts", "chemistry_lab.py")).read()
check("the reading step is told to say so when the records are not what was asked",
      "never let a different protein stand in for the one asked about" in src and '"answers_question"' in src)
check("the orient menu tells him to name the protein in the query he sends",
      "name the protein_name or gene you are actually asking about in THIS query" in src)

# --- a run of questions with no review is a spent thread, and he is told so (KaiC, 2026-09-27) ------
def kaic(n): return {"kind": "inquiry", "inquiry": {"question": "KaiC coupling, take %d?" % n, "browse_lane": "protein",
                     "uniprot_query": M._safe_query('protein_name:"KaiC" AND organism_id:1140'), "source_query": None}}
review = {"kind": "reflection", "source_accessions": ["Q79PF4"]}
empty = {"kind": "source_unavailable", "reason": "uniprot_returned_no_records"}
check("two questions since the last review are not yet a dead end",
      M.dead_ends([review, kaic(1), empty, kaic(2), empty])["questions"] == [])
spent = M.dead_ends([kaic(0), review, kaic(1), empty, kaic(2), empty, kaic(3), empty])
check("three are, and the subject he kept asking about is named",
      spent["count"] == 3 and spent["subjects"] == ["KaiC"] and len(spent["questions"]) == 3, spent)
check("a question back on KaiC repeats it; another protein does not",
      M.repeats_dead_end({"question": "What about kaiC phosphorylation?"}, spent)
      and not M.repeats_dead_end({"question": "S-layer protein of L. acidophilus"}, spent))
check("a named protein followed by AND is carried without the AND",
      M.merge_source_intent(BROAD, 'reviewed:true AND (protein_name:"KaiC" AND organism_id:1140)')["query"]
      .endswith("protein_name:KaiC"))
check("UniProt refusing his query is shown to him as a miss too", "refused this query" in open(
      os.path.join(REPO, "scripts", "chemistry_lab.py")).read())

nb = os.path.join(HOME, "dead-end-notebook.jsonl")
with open(nb, "w") as f:
    for row in (review, kaic(1), empty, kaic(2), empty, kaic(3), empty): f.write(json.dumps(row) + "\n")
prompts, answers = [], [
    json.dumps({"browse_lane": "protein", "uniprot_query": "gene:kaiC", "question": "KaiC once more?"}),
    json.dumps({"browse_lane": "protein", "uniprot_query": "gene:slpA", "question": "How long is slpA?"})]
real_ask, real_nb = M._ask, M.NOTEBOOK
M._ask = lambda system, prompt, *a, **k: prompts.append(prompt) or answers[len(prompts) - 1]
M.NOTEBOOK = nb
try:
    moved = REAL_ORIENT("context")
finally:
    M._ask, M.NOTEBOOK = real_ask, real_nb
check("the orient prompt names the spent run", "LAST 3 QUESTIONS ALL ENDED WITHOUT NEW EVIDENCE" in prompts[0]
      and "SPENT FOR TODAY" in prompts[0] and "KaiC." in prompts[0], prompts[0][-400:])
check("choosing KaiC again is asked once more, and the new subject is kept",
      len(prompts) == 2 and moved["question"] == "How long is slpA?", (len(prompts), moved.get("question")))
open(nb, "w").write(json.dumps(review) + "\n")
prompts[:] = []; answers[0] = answers[1]
M._ask = lambda system, prompt, *a, **k: prompts.append(prompt) or answers[0]
M.NOTEBOOK = nb
try: REAL_ORIENT("context")
finally: M._ask, M.NOTEBOOK = real_ask, real_nb
check("with a fresh review behind him the run warning is gone and one call is made",
      len(prompts) == 1 and "WITHOUT NEW EVIDENCE" not in prompts[0])
check("but KaiC stays spent for the day, so a review on another protein does not reopen it",
      "SPENT FOR TODAY" in prompts[0] and "KaiC" in M.spent_subjects() and M.spent_subjects(time.time() + 25 * 3600) == [])

# the subject named only in the question text, as he actually writes it
only_text = [{"kind": "inquiry", "inquiry": {"question": q, "uniprot_query": M._safe_query("organism_id:1140")}}
             for q in ("What mediates coupling between the ATPase domains in Synechococcus elongatus KaiC?",
                       "Does KaiC change between its states?", "Which residues in KaiC couple its ATPase domains?")]
check("a protein named only in his questions is found, and a molecule class is not",
      M.dead_ends([review] + only_text)["subjects"] == ["KaiC"], M.dead_ends([review] + only_text))

# asked twice and still KaiC: the third time is not sent
prompts[:] = []
M._ask = lambda system, prompt, *a, **k: prompts.append(prompt) or json.dumps(
    {"browse_lane": "protein", "uniprot_query": "organism_id:1140", "question": "KaiC, surely, once more?"})
M.NOTEBOOK = nb
try: stubborn = REAL_ORIENT("context")
finally: M._ask, M.NOTEBOOK = real_ask, real_nb
check("KaiC chosen twice more is not sent: the Lab wanders the curated set instead",
      len(prompts) == 2 and stubborn.get("dead_end_fallback") and "KaiC" not in stubborn["uniprot_query"]
      and re.fullmatch(re.escape(M.BASELINE_QUERY) + r" AND \(length:\[\d+ TO \d+\]\)", stubborn["uniprot_query"]),
      stubborn)

# the journal's KaiC finding stops pulling him back while KaiC is spent
real_threads = M.journal_threads
M.journal_threads = lambda: [
    {"thread_id": "CLT-1", "state": "finding", "question": "KaiC coupling", "finding": "coupled domains",
     "next_question": "Which KaiC residues?", "source_accessions": ["Q79PF4"], "entries": 3, "lesson": ""},
    {"thread_id": "CLT-2", "state": "finding", "question": "S-layer length", "finding": "444 residues",
     "next_question": "Is slpA glycosylated?", "source_accessions": ["P35829"], "entries": 1, "lesson": ""}]
try: journal = M.journal_context()
finally: M.journal_threads = real_threads
check("a journal finding on a spent subject is left out of his planning context",
      "KaiC" not in journal and "S-layer" in journal, journal)

print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
