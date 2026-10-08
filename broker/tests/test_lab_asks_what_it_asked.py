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
M._atomic(M.KNOWN_TAXA, {"version": M.KNOWN_TAXA_VERSION, "ids": ["1579"]})   # an organism a receipt has returned; guessed IDs are tested below

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
M.remember_taxa([{"organism": {"taxonId": 272621}}, {"uid": "33958", "summary": {"taxid": 1584}}])
check("an ID a receipt returns becomes one he may use",
      M.unsourced_ids({"source": "uniprot", "query": "taxonomy_id:272621"}) == []
      and "1584" in M.known_taxa())
check("an NCBI record number is not taken for an organism (1152240 for Colwellia, 2026-09-28)",
      "33958" not in M.known_taxa())

# --- the searches that found nothing are shown to him ---------------------------------------------
ctx, _ = M.lab_context()
check("his planning context lists the searches that found nothing, and why",
      "SEARCHES THAT FOUND NOTHING" in ctx and "the source holds no such record" in ctx
      and "says nothing about biology" in ctx and "the source's answer" not in ctx
      and "512419" in ctx and "look the organism up by name first" in ctx, ctx[-900:])

# --- the Forge is asked for an instrument, never for documentation --------------------------------
offers = []
sys.modules["chemistry_sources"] = types.SimpleNamespace(
    query=fake_query, flush_reports=lambda: None,
    offer_report=lambda ids, intent, **k: offers.append((ids, intent)) or {"id": "P-1"})
reply = {"receipt": {"receipt_id": "REC-3", "response_sha256": "e" * 64, "records": [{"primaryAccession": "Q3"}]}}
M.tick(); M.tick(); M.tick(); M.tick()
check("a reflection that needs nothing new opens no Forge project", offers == [], offers)

# Only a genuinely missing limb reaches the Forge (2026-09-28); lab equipment stays in the Lab.
M._reflect = lambda context, inquiry, records: dict(REFLECTION, instrument_gap="a circular dichroism reading to see the fold")
reply = {"receipt": {"receipt_id": "REC-4", "response_sha256": "f" * 64, "records": [{"primaryAccession": "Q4"}]}}
M.tick(); M.tick(); M.tick(); M.tick()
check("lab equipment he could never operate opens no Forge project", offers == [], offers)
check("it is kept in the Lab, where she can read it",
      any(x.get("instrument_gap_kept_in_lab") and "circular dichroism" in str(x.get("instrument_gap_recorded"))
          for x in M._jsonl(M.NOTEBOOK)))
check("cryo-EM, crystallography and mass spectrometry are equipment; a simulator or a database is a limb",
      not any(M.missing_limb(g) for g in ("cryo-EM of the S-layer lattice", "Cryo-Electron Tomography of ribosomes",
                                          "X-ray crystallography of KaiC", "a mass spectrometer for the glycan"))
      and all(M.missing_limb(g) for g in ("a molecular dynamics simulator to watch the domains move",
                                          "access to the AlphaFold database", "a pressure sensor on the bed")))

# 2026-10-08: a limb worth building is specific and on his work; a simulator from one question is kept in the Lab
# (forge_gaps.py, and its own test). The example is the kind Gloria kept: the H723R transcript mapping.
M._reflect = lambda context, inquiry, records: dict(REFLECTION, instrument_gap="a transcript-variant mapper that places p.H723R on each SLC26A4 transcript")
reply = {"receipt": {"receipt_id": "REC-5", "response_sha256": "a" * 64, "records": [{"primaryAccession": "Q5"}]}}
M.tick(); M.tick(); M.tick(); M.tick()
check("a missing limb does open one, as a capability to build",
      len(offers) == 1 and offers[0][1].startswith("The Lab needs an instrument it does not have:")
      and "transcript-variant mapper" in offers[0][1] and "Build or connect" in offers[0][1]
      and "Document this sourced Lab question" not in offers[0][1], offers)
reply = {"receipt": {"receipt_id": "REC-5b", "response_sha256": "b" * 64, "records": [{"primaryAccession": "Q5b"}]}}
M.tick(); M.tick(); M.tick(); M.tick()
check("the same limb is not asked for twice", len(offers) == 1, offers)
check("the notebook shows what he asked the Forge for",
      any(x.get("forge_report") for x in M._jsonl(M.NOTEBOOK) if x.get("kind") == "reflection"))

def refusing(ids, intent, **k):
    offers.append((ids, intent)); raise OSError("403 four unfinished reports")
sys.modules["chemistry_sources"].offer_report = refusing
M._reflect = lambda context, inquiry, records: dict(REFLECTION, instrument_gap="a glycan binding-site predictor for P62249")
for n, h in (("REC-6", "1"), ("REC-7", "2")):
    reply = {"receipt": {"receipt_id": n, "response_sha256": h * 64, "records": [{"primaryAccession": n}]}}
    M.tick(); M.tick(); M.tick(); M.tick()
check("a request the full Forge refused is not queued again on every later reflection",
      sum("binding-site predictor" in o[1] for o in offers) == 1, [o[1][:60] for o in offers])

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
    if "KaiC" in q and "length:[" not in q:
        return _R({"results": [{"primaryAccession": "Q79PF4", "uniProtkbId": "KAIC_SYNE7",
                                "sequence": {"length": 519, "value": "A" * 519}}]})
    if "PFOR" in q and "length:[" not in q:
        return _R({"results": [{"primaryAccession": "P0PFOR", "uniProtkbId": "PFOR_TEST",
                                "sequence": {"length": 1170, "value": "A" * 1170}}]})
    return _R({"results": []})
M.urllib.request.urlopen = length_aware_urlopen
try:
    long_one = M._browse(M._safe_query('gene:kaiC AND protein_name:"KaiC"'), 4)
    pfor = M._browse(M._safe_query('keyword:PFOR AND protein_name:"pyruvate ferredoxin oxidoreductase"'), 4)
finally:
    M.urllib.request.urlopen = _real
check("a named protein search has no length ceiling",
      [r["accession"] for r in long_one["records"]] == ["Q79PF4"]
      and [r["accession"] for r in pfor["records"]] == ["P0PFOR"]
      and "length:[" not in long_one["executed_query"] and "length:[" not in pfor["executed_query"],
      (asked[-3:], long_one["executed_query"], pfor["executed_query"]))
# the record keeps the whole sequence, and ESM-C trims its own copy to 350 (Gloria, 2026-10-05: a 759-residue
# protein read as 350, so its C-terminal domain was never in front of him)
check("its full length is recorded and its whole sequence kept; ESM-C trims its own copy to 350",
      long_one["records"] and long_one["records"][0]["length"] == 519
      and len(long_one["records"][0]["sequence"]) == 519
      and "[:MAX_LENGTH]" in open(os.path.join(REPO, "scripts", "chemistry_esmc.py")).read())

# --- he gets the records he asked for even when his wording is not UniProt's (2026-09-28) ---------
# A stand-in for UniProt: a protein_name phrase must match a name exactly; bare words match anywhere.
ENTRY = {"primaryAccession": "Q97W60", "uniProtkbId": "PROT_SACS2", "entryType": "UniProtKB reviewed (Swiss-Prot)",
         "text": "Thermosome-associated protease Saccharolobus 2287", "sequence": {"length": 420, "value": "A" * 420}}
def uniprot_like(q):
    if "protein_name:" in q or "gene:" in q or "taxonomy_id:2287" not in q: return []
    inner = q.split("taxonomy_id:2287 AND ", 1)[1]
    # Exact reviewed and exact unreviewed searches fail; only the final partial search answers.
    return [] if "thermophilic AND" in inner or "protease" not in inner else [ENTRY]
def loose_urlopen(req, timeout=0):
    q = __import__("urllib.parse").parse.parse_qs(req.full_url.split("?", 1)[1])["query"][0]
    asked.append(q)
    if "xref_pdb:" in q: raise _ue.HTTPError(req.full_url, 400, "bad query", {}, None)
    return _R({"results": uniprot_like(q)})
M.urllib.request.urlopen = loose_urlopen
asked[:] = []
try:
    loose = M._browse(M._safe_query('protein_name:"thermophilic proteases" AND organism_id:2287'), 4)
    refused = M._browse(M._safe_query('protein_name:"thermophilic proteases" AND organism_id:2287 AND xref_pdb:9ZZZ'), 4)
finally:
    M.urllib.request.urlopen = _real
check("thermophilic proteases of S. solfataricus: the exact name finds nothing, his words do",
      [r["accession"] for r in loose["records"]] == ["Q97W60"] and loose["relaxed"] == "partial_any_word", (asked, loose))
check("the looser search kept his organism and his filters, and says how it found the record",
      "taxonomy_id:2287" in loose["executed_query"]
      and loose["records"][0]["found_by"] == "partial_any_word" and loose["records"][0]["partial_match"] is True
      and loose["source_receipt"]["metadata"]["relaxed"] == "partial_any_word"
      and loose["source_receipt"]["metadata"]["partial_match"] is True)
check("no form he was sent drops his subject or his organism",
      all("taxonomy_id:2287" in q and "protease" in q for q in asked), asked)
check("a query UniProt refused as written is asked again in a form it accepts, with a receipt",
      [r["accession"] for r in refused["records"]] == ["Q97W60"] and refused["fallback_reason"] is None
      and refused["source_receipt"] and "xref_pdb" not in refused["executed_query"], refused.get("executed_query"))

import lab_sources as LS
calls = []
def fake_fetch(url):
    q = __import__("urllib.parse").parse.parse_qs(url.split("?", 1)[1])["query"][0]; calls.append(q)
    return {"results": uniprot_like(q)}, {}
got = LS.Sources(fetch=fake_fetch).query({"source": "uniprot",
      "query": 'taxonomy_id:2287 AND reviewed:true AND protein_name:"thermophilic proteases"'})
check("the microbiology lane's UniProt source gets the same looser forms",
      got["records"] and got["metadata"].get("relaxed") == "partial_any_word"
      and got["metadata"].get("partial_match") is True
      and got["records"][0]["found_by"] == "partial_any_word"
      and got["records"][0]["partial_match"] is True
      and got["query"]["executed_query"].startswith("taxonomy_id:2287 AND "), (calls, got.get("metadata")))
relaxations = LS.uniprot_relaxations(
    'taxonomy_id:2287 AND reviewed:true AND protein_name:"thermophilic proteases" AND go:GO:0000001')
check("relaxation order tries all requested subject words before any partial match",
      [label for label, _ in relaxations] == ["all_words_reviewed", "all_words_unreviewed_included", "partial_any_word"]
      and "thermophilic" in relaxations[0][1] and "proteases" in relaxations[0][1]
      and "reviewed:true" in relaxations[0][1] and "reviewed:true" not in relaxations[1][1]
      and "GO" not in relaxations[0][1], relaxations)
free_text = LS.uniprot_relaxations('taxonomy_id:2287 AND reviewed:true AND membrane protease')
check("free text becomes the subject only when no typed subject field was supplied",
      free_text and "membrane" in free_text[0][1] and "protease" in free_text[0][1], free_text)

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

# asked twice and still KaiC
prompts[:] = []
M._ask = lambda system, prompt, *a, **k: prompts.append(prompt) or json.dumps(
    {"browse_lane": "protein", "uniprot_query": "organism_id:1140", "question": "KaiC, surely, once more?"})
M.NOTEBOOK = nb
try: stubborn = REAL_ORIENT("context")
finally: M._ask, M.NOTEBOOK = real_ask, real_nb
# No random wander after that (2026-09-28): it filled the Lab with reviews of unrelated human proteins.
# He is asked once more; if he still chooses it, his question stands and the literature is read on it.
check("KaiC chosen twice is asked once more, then his question stands, never swapped for a random one",
      len(prompts) == 2 and not stubborn.get("dead_end_fallback") and stubborn["question"] == "KaiC, surely, once more?",
      stubborn)

# the journal's KaiC finding stops pulling him back while KaiC is spent
real_threads = M.journal_threads
M.journal_threads = lambda include_frontier=True: [
    {"thread_id": "CLT-1", "state": "finding", "question": "KaiC coupling", "finding": "coupled domains",
     "next_question": "Which KaiC residues?", "source_accessions": ["Q79PF4"], "entries": 3, "lesson": ""},
    {"thread_id": "CLT-2", "state": "finding", "question": "S-layer length", "finding": "444 residues",
     "next_question": "Is slpA glycosylated?", "source_accessions": ["P35829"], "entries": 1, "lesson": ""}]
try: journal = M.journal_context()
finally: M.journal_threads = real_threads
check("a journal finding on a spent subject is left out of his planning context",
      "KaiC" not in journal and "S-layer" in journal, journal)

# --- he is given the material: published abstracts, fetched by the Lab (2026-09-28) ---------------
import lab_sources as LS2
PUBMED_XML = """<PubmedArticleSet><PubmedArticle><MedlineCitation><PMID>31000001</PMID><Article>
<Journal><Title>J Bacteriol</Title><JournalIssue><PubDate><Year>2019</Year></PubDate></JournalIssue></Journal>
<ArticleTitle>Modular polyketide synthases of <i>Streptomyces</i></ArticleTitle><Abstract>
<AbstractText Label="BACKGROUND">Type I PKS modules carry KS, AT and ACP domains.</AbstractText>
<AbstractText>Optional KR, DH and ER domains set the reduction state.</AbstractText></Abstract></Article>
</MedlineCitation></PubmedArticle></PubmedArticleSet>"""
urls = []
def pm_fetch(url):
    urls.append(url); q = __import__("urllib.parse").parse.parse_qs(url.split("?", 1)[1])
    if q["db"][0] == "taxonomy": return {"esearchresult": {"idlist": ["1883"]}}, {}
    if "esummary" in url: return {"result": {}}, {}
    hit = "marine" not in q["term"][0]                      # four terms find nothing; three do
    return {"esearchresult": {"idlist": ["31000001"] if hit else []}}, {}
client = LS2.Sources(fetch=pm_fetch, fetch_record=lambda url: urls.append(url) or PUBMED_XML)
got = client.query({"source": "pubmed_abstracts", "terms": ["polyketide synthase", "Streptomyces", "module (KS)", "marine"]})
rec = got["records"][0] if got["records"] else {}
check("PubMed abstracts come back whole, with PMID, title, journal and year",
      rec.get("pmid") == "31000001" and "KS, AT and ACP" in rec.get("abstract", "") and "KR, DH and ER" in rec["abstract"]
      and rec.get("title") == "Modular polyketide synthases of Streptomyces" and rec.get("year") == "2019", got)
check("when all his terms find nothing, the last is dropped until something does",
      got["query"]["terms_matched"] == ["polyketide synthase", "Streptomyces", "module KS"], got["query"])
urls[:] = []
named = client.query({"source": "ncbi", "operation": "protein", "organism": "Streptomyces", "term": "polyketide synthase"})
check("an organism named instead of an ID is looked up by the Lab, not refused",
      "db=taxonomy" in urls[0] and "txid1883" in __import__("urllib.parse").parse.unquote(urls[1])
      and named["query"]["resolved_taxon_id"] == "1883", urls)

_cs = importlib.util.spec_from_file_location("chemistry_sources_real", os.path.join(REPO, "scripts", "chemistry_sources.py"))
CS_real = importlib.util.module_from_spec(_cs); _cs.loader.exec_module(CS_real)
pks = {"question": "What are the specific modular architectures of polyketide synthases (PKS) in marine "
                   "actinobacteria, and how do these modules dictate the biosynthetic diversity?",
       "uniprot_query": M._safe_query('protein_name:"polyketide synthase"'), "source_query": None}
terms = CS_real.material_terms(pks)
check("without chosen terms, the protein he named and the words that carry the question are used",
      terms[0] == "polyketide synthase" and "PKS" in terms and "the" not in terms and len(terms) <= 5, terms)
check("terms he chose himself are used as he wrote them",
      CS_real.material_terms(dict(pks, material_terms=["KaiC", "phosphorylation"])) == ["KaiC", "phosphorylation"])

# the lane: a source that holds nothing, then the literature is read instead of the question dropped
seen_by_reflect = []
M._reflect = lambda context, inquiry, records: seen_by_reflect.append(records) or dict(REFLECTION)
sys.modules["chemistry_sources"] = types.SimpleNamespace(
    query=lambda spec_, question="", **k: {"receipt": {"receipt_id": "REC-E", "response_sha256": "0" * 64, "records": []}},
    flush_reports=lambda: 0, material=lambda inquiry: got)
M._atomic(M.STATE, {"phase": "sources", "turns": 90, "inquiry": {
    "browse_lane": "microbiology", "source_query": {"source": "ncbi", "operation": "literature", "term": "PKS marine"},
    "uniprot_query": M.BASELINE_QUERY, "question": "PKS modules in marine actinobacteria?"}})
went = M.tick()
check("an empty source goes on to the literature, not back to a new question",
      went.get("next_phase") == "reflect" and M._jsonl(M.NOTEBOOK)[-1].get("literature_instead") == 1, went)
M.tick()
last = M._jsonl(M.NOTEBOOK)[-1]
check("the review reads the abstracts and records which papers it read",
      seen_by_reflect and seen_by_reflect[-1]["LITERATURE"][0]["pmid"] == "31000001"
      and last["kind"] == "reflection" and last["literature"][0]["pmid"] == "31000001"
      and "PMID-31000001" in last["source_accessions"], last)

# --- an organism ID written from memory is replaced by the one for the organism he named (2026-09-28) ---
looked = []
def taxonomy(name):
    looked.append(name); return "28228" if name == "Colwellia" else None
q, how = M.resolve_taxa('reviewed:true AND (protein_name:"cold shock protein" AND organism_id:99999)',
                        "Does the Tyr51 substitution in Colwellia psychre CSP create a pocket?", lookup=taxonomy)
check("a guessed organism ID is replaced by the genus he named when the species is cut short",
      "taxonomy_id:28228" in q and "99999" not in q and looked == ["Colwellia psychre", "Colwellia"]
      and how == {"guessed": ["99999"], "resolved": "28228", "from_name": "Colwellia"}, (q, looked, how))
check("and the resolved ID is remembered as sourced", "28228" in M.known_taxa())
looked[:] = []
kept, how2 = M.resolve_taxa("reviewed:true AND (gene:kaiC AND taxonomy_id:28228)", "KaiC in Colwellia psychre", lookup=taxonomy)
check("an ID a receipt already returned is trusted and not looked up", kept.endswith("taxonomy_id:28228)") and looked == [] and how2 is None)
unnamed, how3 = M.resolve_taxa("reviewed:true AND (gene:x AND taxonomy_id:424242)", "What does the fold do?", lookup=taxonomy)
check("with no organism named, his ID is left as it was", "424242" in unnamed and how3 is None)

M._atomic(M.KNOWN_TAXA, ["1152240", "1584"])   # the first version of the file, with a record number in it
check("the first version of the known-organism file is rebuilt once, without record numbers",
      "1152240" not in M.known_taxa() and M._load(M.KNOWN_TAXA, {}).get("version") == M.KNOWN_TAXA_VERSION)
M._add_known_taxa({"1152240"})   # as if a source had once returned it
looked[:] = []
forced, how4 = M.resolve_taxa('reviewed:true AND (protein_name:"cold shock protein" AND taxonomy_id:1152240)',
                              "Tyr51 in Colwellia psychre CSP", lookup=taxonomy, force=True)
check("after an empty search even a 'known' ID is checked against the organism he named",
      "taxonomy_id:28228" in forced and how4["resolved"] == "28228", (forced, how4))
same, how5 = M.resolve_taxa("reviewed:true AND (gene:cspA AND taxonomy_id:28228)", "cspA in Colwellia psychre",
                            lookup=taxonomy, force=True)
check("and when his ID was right it is left alone", how5 is None and same.endswith("taxonomy_id:28228)"))

# the whole turn: an empty search on a 'known' wrong ID is retried once on the organism he named
browsed = []
def by_taxon(q, n):
    browsed.append(q)
    rows = [{"accession": "Q47XU5", "protein_name": "Cold shock protein"}] if "taxonomy_id:28228" in q else []
    return {"source_receipt": None, "records": rows, "requested_query": q, "executed_query": q,
            "fallback_reason": None, "relaxed": None}
real_browse, real_taxon = M._browse, LS2.Sources._taxon
M._browse, LS2.Sources._taxon = by_taxon, lambda self, spec: "28228" if spec.get("organism") == "Colwellia" else None
M._atomic(M.STATE, {"phase": "browse", "turns": 110, "inquiry": {"browse_lane": "protein", "source_query": None,
          "uniprot_query": "reviewed:true AND (protein_name:cold shock protein AND taxonomy_id:1152240 AND reviewed:true)",
          "question": "Does the Tyr51 substitution in Colwellia psychre CSP matter?"}})
try: M.tick()
finally: M._browse, LS2.Sources._taxon = real_browse, real_taxon
row = M._jsonl(M.NOTEBOOK)[-1]
check("an empty search on a wrong organism ID is retried on the organism he named, and finds it",
      len(browsed) == 2 and "1152240" in browsed[0] and "taxonomy_id:28228" in browsed[1]
      and row["kind"] == "source_read" and row["organism_resolved"]["resolved"] == "28228", (browsed, row.get("kind")))

# --- the same papers are not reviewed again and again (three Tyr51 reviews in two minutes) ---------
real_browse = M._browse
M._browse = lambda q, n: {"source_receipt": None, "records": [], "requested_query": q, "executed_query": q,
                          "fallback_reason": None, "relaxed": None}
def protein_turn():
    M._atomic(M.STATE, {"phase": "browse", "turns": 120, "inquiry": {"browse_lane": "protein", "source_query": None,
              "uniprot_query": M.BASELINE_QUERY, "question": "Tyr51 in the cold-shock protein?"}})
    went = M.tick()
    if went.get("next_phase") == "reflect": M.tick()
    return went
try:
    before = sum(1 for x in M._jsonl(M.NOTEBOOK) if x.get("kind") == "reflection" and "PMID-31000001" in (x.get("source_accessions") or []))
    turns = [protein_turn() for _ in range(3)]
finally:
    M._browse = real_browse
reviews = sum(1 for x in M._jsonl(M.NOTEBOOK) if x.get("kind") == "reflection" and "PMID-31000001" in (x.get("source_accessions") or []))
check("the same abstracts are reviewed at most twice, then he is sent to another question",
      before == 1 and reviews == 2 and turns[-1].get("next_phase") == "orient"
      and M._jsonl(M.NOTEBOOK)[-1].get("papers_already_reviewed") is True, (before, reviews, [t.get("next_phase") for t in turns]))

# --- PubMed asked for the way the connector names it, and a cut-off word does not empty it (2026-09-28) --
pm_urls = []
def pm2(url):
    pm_urls.append(url); q = __import__("urllib.parse").parse.parse_qs(url.split("?", 1)[1])
    term = q.get("term", [""])[0]
    if q.get("retmax") == ["0"]: return {"esearchresult": {"count": "0" if "psychre" in term else "57"}}, {}
    return {"esearchresult": {"idlist": ["31000001"] if "psychre" not in term else []}}, {}
pm_client = LS2.Sources(fetch=pm2, fetch_record=lambda url: PUBMED_XML)
asked_pm = pm_client.query({"operation": "search_articles", "source": "pubmed",
                            "term": "Colwellia psychre cold shock protein Tyr51 thermostability"})
check("source pubmed, as he writes it, is the PubMed search, not an unknown source",
      asked_pm["source"] == "pubmed_abstracts" and asked_pm["records"][0]["pmid"] == "31000001", asked_pm.get("query"))
check("a word no paper contains is dropped before the search, and his other words are kept",
      "psychre" not in asked_pm["query"]["terms_matched"]
      and asked_pm["query"]["terms_matched"][:2] == ["Colwellia", "cold"]
      and "protein" not in asked_pm["query"]["terms"], asked_pm["query"])

print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
