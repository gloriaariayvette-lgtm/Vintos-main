#!/usr/bin/env python3
"""Chemistry Lab control plane and loop. Scratch HOME only; no model or network."""
import contextlib
import importlib.util
import json
import os
import sys
import tempfile
import types

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
HOME = tempfile.mkdtemp(prefix="vintos-chem-lab-")
WS = os.path.join(HOME, ".vintos", "workspace")
os.makedirs(os.path.join(WS, "memory"), exist_ok=True)
os.environ["HOME"] = HOME; os.environ["SPARK_WORKSPACE"] = WS
open(os.path.join(WS, "SOUL.md"), "w").write("I am Vintos. I am curious in my own particular way.")
open(os.path.join(WS, "SELF-MODEL.md"), "w").write("I have been returning to shapes and mechanisms.")
json.dump({"heading": "learning by making"}, open(os.path.join(WS, "memory", "living-trajectory.json"), "w"))

spec = importlib.util.spec_from_file_location("chemistry_lab_test", os.path.join(REPO, "scripts", "chemistry_lab.py"))
M = importlib.util.module_from_spec(spec); spec.loader.exec_module(M)
sys.modules["chemistry_lab"] = M

R = []
def check(name, ok, detail=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + name + ((" -> " + str(detail)[:180]) if detail and not ok else ""))

check("test is in a scratch workspace", M.WS == WS and HOME in M.ROOT and not M.ROOT.startswith("/home/gloria"), M.ROOT)
check("starts disabled", M.status()["enabled"] is False and M.status()["effective_state"] == "off")
check("requested cadence and patient compute wait are visible",
      M.status()["poll_seconds"] == 15 and M.status()["turn_wait_seconds"] == 300
      and M.status()["turns"] == 0 and M.DEFAULTS["turn_wait_seconds"] == 300, M.status())
M._ensure(); json.dump({"enabled": True, "poll_seconds": 300, "turn_wait_seconds": 2}, open(M.CONFIG, "w"))
check("persisted legacy cadence migrates instead of defeating new defaults",
      M.config()["cadence_version"] == 3 and M.config()["poll_seconds"] == 15
      and M.config()["turn_wait_seconds"] == 300, M.config())
on = M.set_enabled(True)
check("Tune control enables without deleting state", on["enabled"] is True and not os.path.exists(M.STOP))
ctx, receipt = M.lab_context()
check("Gemma context contains a bounded slice of Vintos", "I am Vintos" in ctx and "shapes and mechanisms" in ctx and len(ctx) <= M.config()["context_budget_chars"] + 200, len(ctx))
check("context provenance is written", receipt["total_chars"] > 0 and all(x.get("sha256") for x in receipt["sources"]) and os.path.exists(M.RECEIPTS), receipt)

@contextlib.contextmanager
def admitted(*a, **k): yield types.SimpleNamespace()
sys.modules["compute_admission"] = types.SimpleNamespace(admit=admitted)
M._orient = lambda context: {"uniprot_query": "reviewed:true AND length:[40 TO 350]", "question": "Which compact fold catches me?", "why_now": "shape"}
real_browse = M._browse
M._browse = lambda query, limit: {"records": [{"accession": "P00001", "protein_name": "small test protein", "organism": "Example", "length": 80, "sequence": "A" * 80}],
                                  "requested_query": query, "executed_query": query,
                                  "fallback_reason": None}
M._embed_records = lambda records: {"ok": True, "model": "test-esmc", "device": "test",
                                    "embeddings": [{"accession": "P00001", "dimension": 4,
                                                    "embedding_sha256": "abc", "artifact": "memory/chemistry-lab/artifacts/esmc/test.npy"}]}
M._reflect = lambda context, inquiry, records: {"attention": "the compactness", "factual_observation": "the record says length 80", "speculative_reading": "it feels architectural", "next_question": "what recurs?"}
one, two, three, four = M.tick(), M.tick(), M.tick(), M.tick()
check("four checkpointed turns complete the loop", [one.get("kind"), two.get("kind"), three.get("kind"), four.get("kind")] == ["inquiry", "source_read", "protein_representation", "reflection"], (one, two, three, four))
check("status accounts for completed turns and their last receipt",
      M.status()["turns"] == 4 and M.status()["last_outcome"] == "reflection"
      and bool(M.status()["last_turn_at"]), M.status())
adapted = [json.loads(x) for x in open(M.COLLISION_ADAPTER) if x.strip()]
check("protein material crosses by source text, never raw vector coordinates",
      len(adapted) == 1 and adapted[0].get("transform") == "uniprot_metadata_to_text_v1_then_house_nomic"
      and "vector" not in adapted[0] and adapted[0].get("source_accession") == "P00001", adapted)
notes = [json.loads(x) for x in open(M.NOTEBOOK) if x.strip()]
check("source and speculation stay distinguishable", any(x.get("truth_status") == "source_metadata_not_lived_experience" for x in notes) and any("named_speculation" in x.get("truth_status", "") for x in notes))
source_note = next(x for x in notes if x.get("kind") == "source_read")
check("source note records requested and executed queries", source_note.get("requested_query") == source_note.get("executed_query") and source_note.get("fallback_reason") is None)
check("dangerous generated query cannot widen the perimeter", "toxin" not in M._safe_query("toxin human target") and M._safe_query("toxin human target").startswith("reviewed:true"))
normalized = M._safe_query("protein_name : Clarin-2 organism_id : 9606 reviewed : True")
check("generated UniProt syntax is canonical before the request",
      "protein_name:Clarin-2 AND organism_id:9606 AND reviewed:true" in normalized
      and " : " not in normalized and "True" not in normalized, normalized)
original_urlopen = M.urllib.request.urlopen; rejected_calls = []
def reject_specific(request, timeout=0):
    rejected_calls.append(request.full_url)
    raise M.urllib.error.HTTPError(request.full_url, 400, "fixture rejection", {}, None)
try:
    M.urllib.request.urlopen = reject_specific
    rejected_browse = real_browse(normalized, 4)
finally:
    M.urllib.request.urlopen = original_urlopen
check("a rejected specific UniProt query never widens to the generic baseline",
      len(rejected_calls) == 1 and rejected_browse["records"] == []
      and rejected_browse["source_receipt"] is None
      and rejected_browse["executed_query"] == normalized
      and rejected_browse["fallback_reason"] == "source_rejected_generated_query")
bad_lineage, bad_reason = M._sourced_followup({"source":"pdb", "entry_id":"1O96"},
                                               [{"accession":"A0PK11", "pdb_ids":[]}])
good_lineage, good_reason = M._sourced_followup({"source":"pdb", "entry_id":"6H86"},
                                                 [{"accession":"A1L190", "pdb_ids":["6H86"]}])
check("a structure follow-up must be named by the current protein records",
      bad_lineage is None and "absent" in bad_reason
      and good_lineage["id"] == "6H86" and good_reason is None)

M._append(M.NOTEBOOK, {"at":"2026-09-14T00:00:00Z", "kind":"reflection", "entry_id":"F-1",
    "inquiry":{"question":"Why does this fold recur?"}, "source_accessions":["P00001"],
    "factual_observation":"The sourced record has a repeat.", "next_question":"Compare a second sourced fold."})
M._append(M.NOTEBOOK, {"at":"2026-09-15T00:00:00Z", "kind":"reflection", "entry_id":"F-2",
    "inquiry":{"question":"Why does this fold recur?"}, "source_accessions":["P00001"],
    "factual_observation":"The sourced record has a repeat.", "next_question":"Compare a second sourced fold."})
M._append(M.NOTEBOOK, {"at":"2026-09-16T00:00:00Z", "kind":"reflection", "entry_id":"E-1",
    "inquiry":{"question":"Can an unsupported guess explain it?"},
    "speculative_reading":"It might.", "next_question":"Find an actual source first."})
M._append(M.NOTEBOOK, {"at":"2026-09-17T00:00:00Z", "kind":"reflection", "entry_id":"E-2",
    "inquiry":{"question":"Can an unsupported guess explain it?"},
    "speculative_reading":"It might.", "next_question":"Find an actual source first."})
threads = M.journal_threads()
finding = next(t for t in threads if t["question"] == "Why does this fold recur?")
redirect = next(t for t in threads if t["question"] == "Can an unsupported guess explain it?")
check("repeated source-backed observations form one durable finding",
      finding["state"] == "finding" and finding["entries"] == 2 and finding["salient_at"] == "2026-09-14T00:00:00Z"
      and finding["entry_ids"] == ["F-1", "F-2"] and finding["source_accessions"] == ["P00001"])
check("unsupported repeats remain a single low-salience redirect",
      redirect["state"] == "redirect" and redirect["entries"] == 2 and redirect["salient_at"] == "2026-09-16T00:00:00Z"
      and not redirect["finding"])
M._append(M.NOTEBOOK, {"at":"2026-09-17T01:00:00Z", "kind":"reflection", "entry_id":"BAD-PDB",
    "inquiry":{"question":"Does this protein use unrelated structure 1O96?",
               "source_query":{"source":"pdb", "entry_id":"1O96"}},
    "source_accessions":["A0PK11", "RESPONSE-fixture"], "source_query_succeeded":True,
    "factual_observation":"The unrelated structure says something interesting."})
bad_structure = next(t for t in M.journal_threads() if t["question"] == "Does this protein use unrelated structure 1O96?")
check("an old unlinked structure association is retained only as a redirect",
      bad_structure["state"] == "redirect" and "association is rejected" in bad_structure["lesson"])
for index in range(5):
    M._append(M.NOTEBOOK, {"at":"2026-09-%02dT00:00:00Z" % (18+index), "kind":"reflection",
        "entry_id":"SAT-%d" % index, "inquiry":{"question":"Variant angle %d?" % index},
        "source_accessions":["P99999"], "factual_observation":"Same record, new wording %d." % index,
        "next_question":"Could I read it again?"})
saturated = next(t for t in M.journal_threads() if t["question"].startswith("Repeated source set:"))
check("many rephrasings of one source set collapse into an auditable redirect",
      saturated["entries"] == 5 and saturated["state"] == "redirect" and not saturated["finding"]
      and "not new evidence" in saturated["lesson"] and saturated["source_accessions"] == ["P99999"])
check("the repeated source set is recognized before another reflection",
      M.journal_source_saturated(["P99999"]) and not M.journal_source_saturated(["NEW-ID"]))
M._atomic(M.STATE, {"phase":"browse", "turns":4,
                    "inquiry":{"browse_lane":"protein", "uniprot_query":"reviewed:true"}})
M._browse = lambda query, limit: {"records":[{"accession":"P99999", "sequence":"A"*80}],
                                   "requested_query":query, "executed_query":query,
                                   "fallback_reason":None}
stale_turn = M.tick()
check("a stale routine browse returns to orientation without another model reflection",
      stale_turn["kind"] == "browse_stale" and stale_turn["next_phase"] == "orient")
M._atomic(M.STATE, {"phase":"browse", "turns":5,
                    "inquiry":{"browse_lane":"protein", "question":"Wrong structure?",
                               "uniprot_query":"reviewed:true",
                               "source_query":{"source":"pdb", "entry_id":"1O96"}}})
M._browse = lambda query, limit: {"records":[{"accession":"A0PK11", "sequence":"A"*80,
                                                "pdb_ids":[], "chembl_ids":[]}],
                                   "requested_query":query, "executed_query":query,
                                   "fallback_reason":None, "source_receipt":None}
unsourced_turn = M.tick()
check("an invented PDB id is refused before the source call while valid protein work continues",
      unsourced_turn["kind"] == "source_read" and unsourced_turn["next_phase"] == "embed"
      and M._load(M.STATE,{})["inquiry"].get("source_query") is None
      and M._jsonl(M.NOTEBOOK)[-2]["kind"] == "unsourced_id")
def unavailable(*a, **k): raise PermissionError("fixture source unavailable")
sys.modules["chemistry_sources"] = types.SimpleNamespace(query=unavailable)
M._atomic(M.STATE, {"phase":"sources", "turns":5, "records":[{"accession":"P99999", "sequence":"A"*80}],
                    "source_query_succeeded":True,
                    "inquiry":{"browse_lane":"protein", "source_query":{"source":"pdb","entry_id":"TEST"}}})
failed_followup = M.tick()
check("a failed follow-up on saturated records redirects before embedding or reflecting",
      failed_followup["kind"] == "source_unavailable" and failed_followup["next_phase"] == "orient"
      and M._jsonl(M.NOTEBOOK)[-1]["saturation_redirect"] is True)
sys.modules["chemistry_sources"] = types.SimpleNamespace(query=lambda *a, **k: {
    "receipt":{"receipt_id":"REC-NEW", "response_sha256":"a"*64, "records":[{"value":"new"}]}})
M._atomic(M.STATE, {"phase":"sources", "turns":6, "records":[{"accession":"P99999", "sequence":"A"*80}],
                    "source_query_succeeded":False,
                    "inquiry":{"browse_lane":"protein", "question":"What is different?",
                               "source_query":{"source":"pdb","entry_id":"TEST"}}})
good_followup = M.tick()
M.tick(); reflected = M.tick()
latest_reflection = next(x for x in reversed(M._jsonl(M.NOTEBOOK)) if x.get("kind") == "reflection")
check("a genuinely new follow-up keeps its receipt and stable response fingerprint",
      good_followup["next_phase"] == "embed" and reflected["kind"] == "reflection"
      and latest_reflection["followup_receipt_id"] == "REC-NEW"
      and "RESPONSE-" + "a"*32 in latest_reflection["source_accessions"]
      and latest_reflection["source_query_succeeded"] is True)
ctx2, receipt2 = M.lab_context()
check("planning sees findings and redirects, not repeated raw notebook prose",
      "LAB JOURNAL THREADS" in ctx2 and '"finding":' in ctx2
      and "errors are redirects" in ctx2 and "Repeated source set" in ctx2
      and "RECENT LAB NOTEBOOK" not in ctx2
      and any(s["name"] == "lab_journal_threads" for s in receipt2["sources"]), ctx2[:1100])

before = open(M.NOTEBOOK).read()
off = M.set_enabled(False)
check("off requests a stop and preserves notebook", off["enabled"] is False and os.path.exists(M.STOP) and before in open(M.NOTEBOOK).read())
check("an off tick does no work", M.tick().get("state") == "off")
check("Atelier is architecturally absent", "atelier" not in M.ROOT.lower() and M.status()["paths"]["atelier"] is False)

server = open(os.path.join(REPO, "bin", "server.py")).read()
ui = open(os.path.join(REPO, "clients", "mobile", "index.html")).read()
check("the Lab activity page counts the recorded embedding field",
      'len(row.get("embeddings") or row.get("representations") or [])' in server)
check("status and toggle routes are private", '@app.get("/api/lab/chemistry/status")' in server and '@app.post("/api/lab/chemistry/toggle")' in server and server[server.index('async def chemistry_lab_status'):server.index('async def chemistry_lab_toggle')].count("_require_secret") == 1)
check("Tune exposes and reloads the control", "chemistry-lab-toggle" in ui and "loadChemistryLabStatus()" in ui and "toggleChemistryLab()" in ui)
check("service and deploy manifest name background and scheduled workers", os.path.exists(os.path.join(REPO, "broker", "vintos-chemistry-lab.service")) and os.path.exists(os.path.join(REPO, "broker", "vintos-chemistry-session.timer")) and all(x in open(os.path.join(REPO, "scripts", "deploy-atelier.sh")).read() for x in ("chemistry_lab.py", "chemistry_esmc.py", "chemistry_mac.py", "chemistry_session.py")))
deploy = open(os.path.join(REPO, "scripts", "deploy-atelier.sh")).read()
check("release and rollback own the new service", '"vintos-chemistry-lab": unit(' in deploy and 'CHEM_UNIT_NAME' in deploy and 'disable --now %q' in deploy)
self_review = open(os.path.join(REPO, "scripts", "self_review.py")).read()
check("self-review consumes only the Chemistry text adapter", '"chemistry_lab", "chemistry-lab/collision-adapter.jsonl"' in self_review and "artifacts/esmc" not in self_review)

print("\n%d/%d passed" % (sum(R), len(R)))
raise SystemExit(0 if all(R) else 1)
