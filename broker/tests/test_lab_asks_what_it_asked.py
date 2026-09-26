#!/usr/bin/env python3
"""The Lab sends the question he actually asked, and stops when the source has no answer.

2026-09-26, from her review of 30 notebook entries: he asked eight times for the S-layer protein of
Lactobacillus acidophilus. The Lab sent "every reviewed protein of this organism" instead, the same
first record came back each time — a bile-salt enzyme — and he wrote it down as the S-layer protein.
The repetition guard did not run in this lane, and every reflection opened a Forge project to
document the question.

Scratch HOME; the source client and both model calls are stubs; nothing here reaches the network.
"""
import contextlib, importlib.util, json, os, sys, tempfile, types

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

# --- he may not substitute a different protein for the one asked about ----------------------------
src = open(os.path.join(REPO, "scripts", "chemistry_lab.py")).read()
check("the reading step is told to say so when the records are not what was asked",
      "never let a different protein stand in for the one asked about" in src and '"answers_question"' in src)
check("the orient menu tells him to name the protein in the query he sends",
      "name the protein_name or gene you are actually asking about in THIS query" in src)

print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
