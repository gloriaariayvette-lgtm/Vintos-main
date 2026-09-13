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

R = []
def check(name, ok, detail=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + name + ((" -> " + str(detail)[:180]) if detail and not ok else ""))

check("test is in a scratch workspace", M.WS == WS and HOME in M.ROOT and not M.ROOT.startswith("/home/gloria"), M.ROOT)
check("starts disabled", M.status()["enabled"] is False and M.status()["effective_state"] == "off")
on = M.set_enabled(True)
check("Tune control enables without deleting state", on["enabled"] is True and not os.path.exists(M.STOP))
ctx, receipt = M.lab_context()
check("Gemma context contains a bounded slice of Vintos", "I am Vintos" in ctx and "shapes and mechanisms" in ctx and len(ctx) <= M.config()["context_budget_chars"] + 200, len(ctx))
check("context provenance is written", receipt["total_chars"] > 0 and all(x.get("sha256") for x in receipt["sources"]) and os.path.exists(M.RECEIPTS), receipt)

@contextlib.contextmanager
def admitted(*a, **k): yield types.SimpleNamespace()
sys.modules["compute_admission"] = types.SimpleNamespace(admit=admitted)
M._orient = lambda context: {"uniprot_query": "reviewed:true AND length:[40 TO 350]", "question": "Which compact fold catches me?", "why_now": "shape"}
M._browse = lambda query, limit: {"records": [{"accession": "P00001", "protein_name": "small test protein", "organism": "Example", "length": 80, "sequence": "A" * 80}],
                                  "requested_query": query, "executed_query": query,
                                  "fallback_reason": None}
M._embed_records = lambda records: {"ok": True, "model": "test-esmc", "device": "test",
                                    "embeddings": [{"accession": "P00001", "dimension": 4,
                                                    "embedding_sha256": "abc", "artifact": "memory/chemistry-lab/artifacts/esmc/test.npy"}]}
M._reflect = lambda context, inquiry, records: {"attention": "the compactness", "factual_observation": "the record says length 80", "speculative_reading": "it feels architectural", "next_question": "what recurs?"}
one, two, three, four = M.tick(), M.tick(), M.tick(), M.tick()
check("four checkpointed turns complete the loop", [one.get("kind"), two.get("kind"), three.get("kind"), four.get("kind")] == ["inquiry", "source_read", "protein_representation", "reflection"], (one, two, three, four))
notes = [json.loads(x) for x in open(M.NOTEBOOK) if x.strip()]
check("source and speculation stay distinguishable", any(x.get("truth_status") == "source_metadata_not_lived_experience" for x in notes) and any("named_speculation" in x.get("truth_status", "") for x in notes))
source_note = next(x for x in notes if x.get("kind") == "source_read")
check("source note records requested and executed queries", source_note.get("requested_query") == source_note.get("executed_query") and source_note.get("fallback_reason") is None)
check("dangerous generated query cannot widen the perimeter", "toxin" not in M._safe_query("toxin human target") and M._safe_query("toxin human target").startswith("reviewed:true"))

before = open(M.NOTEBOOK).read()
off = M.set_enabled(False)
check("off requests a stop and preserves notebook", off["enabled"] is False and os.path.exists(M.STOP) and before in open(M.NOTEBOOK).read())
check("an off tick does no work", M.tick().get("state") == "off")
check("Atelier is architecturally absent", "atelier" not in M.ROOT.lower() and M.status()["paths"]["atelier"] is False)

server = open(os.path.join(REPO, "bin", "server.py")).read()
ui = open(os.path.join(REPO, "clients", "mobile", "index.html")).read()
check("status and toggle routes are private", '@app.get("/api/lab/chemistry/status")' in server and '@app.post("/api/lab/chemistry/toggle")' in server and server[server.index('async def chemistry_lab_status'):server.index('async def chemistry_lab_toggle')].count("_require_secret") == 1)
check("Tune exposes and reloads the control", "chemistry-lab-toggle" in ui and "loadChemistryLabStatus()" in ui and "toggleChemistryLab()" in ui)
check("service and deploy manifest name both workers", os.path.exists(os.path.join(REPO, "broker", "vintos-chemistry-lab.service")) and all(x in open(os.path.join(REPO, "scripts", "deploy-atelier.sh")).read() for x in ("chemistry_lab.py", "chemistry_esmc.py")))
deploy = open(os.path.join(REPO, "scripts", "deploy-atelier.sh")).read()
check("release and rollback own the new service", '"vintos-chemistry-lab": unit(' in deploy and 'CHEM_UNIT_NAME' in deploy and 'disable --now %q' in deploy)

print("\n%d/%d passed" % (sum(R), len(R)))
raise SystemExit(0 if all(R) else 1)
