#!/usr/bin/env python3
"""Review items 34, 39, 50, 51, 54, 65, 70, 71 (2026-09-10). Scratch HOME; no model."""
import os, sys, json, types, tempfile, importlib.util, time

HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
HOME = tempfile.mkdtemp(prefix="vintos-rc-"); os.environ["HOME"] = HOME
WS = os.path.join(HOME, ".vintos", "workspace"); MEM = os.path.join(WS, "memory"); os.makedirs(os.path.join(MEM, "art", "music"), exist_ok=True)
R = []
def check(name, ok, detail=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + name + (("  ->  %s" % (detail,)) if (detail and not ok) else ""))
def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m
def src(rel): return open(os.path.join(REPO, rel), errors="replace").read()

print("\n--- 34 / 39 / 51: one vocabulary for identity, layer and response ---")
RC = load("record_contract", os.path.join(REPO, "scripts", "record_contract.py"))
check("every crossing record kind names its id field and where it is minted", set(RC.IDENTITY) >= {"turn", "prediction", "grade", "effect", "want", "artifact", "moment", "correction", "question", "build"} and all(v["field"] and v["minted_by"] for v in RC.IDENTITY.values()))
check("the four layers are named with what belongs in each", set(RC.LAYERS) == {"raw", "derived", "requested", "acknowledged"} and all(len(v) > 20 for v in RC.LAYERS.values()))
check("legacy words map into the one response vocabulary", RC.normalize_state("ok") == "successful" and RC.normalize_state("refused") == "declined" and RC.normalize_state("timeout") == "timed_out" and RC.normalize_state("HELD") == "held")
try: RC.normalize_state("sideways"); check("a word with no meaning is refused, not guessed", False)
except ValueError: check("a word with no meaning is refused, not guessed", True)
a = RC.audit()
check("every named identity has at least one writer in the checkout", all(v["writers"] for k, v in a["identity"].items() if k != "question") , {k: v["writers"] for k, v in a["identity"].items() if not v["writers"]})
check("no attempt-responder uses a word outside the vocabulary; lifecycle states are listed apart", a["unmapped_states"] == [] and len(a["domain_states"]) > 10, a["unmapped_states"])

print("\n--- 50 / 54: what a restart caught mid-act ---")
PS = load("pending_sweep", os.path.join(REPO, "scripts", "pending_sweep.py")); PS.MEMORY = MEM
check("nothing outstanding on a clean tree", PS.sweep() == [])
json.dump({"landings": [{"task_id": "T1", "title": "x", "state": "landing", "at": "2026-09-10T01:00:00"}]}, open(os.path.join(MEM, "art", "music", "music.json"), "w"))
json.dump({"started_at": "2026-09-10T02:00:00", "state": "closing", "closing_at": "2026-09-10T02:05:00", "turns": [1]}, open(os.path.join(MEM, "voice-session-state.json"), "w"))
json.dump([{"id": "W1", "completion_held": {"at": "2026-09-10T03:00:00", "why": "judge unavailable"}}], open(os.path.join(MEM, "current-wants.json"), "w"))
open(os.path.join(MEM, "self-review-build-events.jsonl"), "w").write(json.dumps({"build_id": "SRB-1", "state": "started", "at": "2026-09-10T04:00:00"}) + "\n")
json.dump({"receipts": {"clip1:ntfy": {"state": "sent", "at": "2026-09-10T05:00:00"}}}, open(os.path.join(MEM, "delivery-receipts.json"), "w"))
rows = {r["kind"]: r for r in PS.sweep()}
check("each mid-act marker is found with its id, age and how it resumes", set(rows) == {"music_landing", "voice_session", "want_completion", "self_review_build", "delivery"} and rows["music_landing"]["id"] == "T1" and rows["music_landing"]["resumable"], list(rows))
check("a send with no acknowledgment is NOT resumable and never resent", rows["delivery"]["resumable"] is False and "never resend" in rows["delivery"]["how"])
check("every row carries an age in hours", all(r.get("age_h") is not None for r in rows.values()))

print("\n--- 65: a shared-support record carries its schema and source cursor ---")
am = src("bin/absence-map-cold.py")
check("an absence carries schema_version and a source cursor naming the source and when", '"schema_version": 2' in am and '"source_cursor": {"source": source, "source_id": source_id' in am and am == src("bin/absence_map_cold.py"))

print("\n--- 70: no watcher reports success from a stale predicate ---")
AW = load("armed_watch", os.path.join(REPO, "scripts", "armed_watch.py")); AW.MEM = MEM
check("coherence pressure is unknown without a fresh record", AW.w_coherence_pressure() is None)
json.dump([{"at": "t"}], open(os.path.join(MEM, "voice-coherence.json"), "w"))
check("... and true once one exists", AW.w_coherence_pressure() is True)
json.dump([{"id": "S1"}], open(os.path.join(MEM, "gloria-music-shares.json"), "w"))
check("a share alone is not the composer having read it", AW.w_composer_reads_shares() is None)
json.dump({"generated": [{"title": "a", "shares_in_context": ["S1"]}]}, open(os.path.join(MEM, "art", "music", "music.json"), "w"))
check("... a composition naming that share is", AW.w_composer_reads_shares() is True)

print("\n--- 71: a grounding that could not be evaluated is unknown ---")
gp = src("scripts/gloria_prediction.py")
check("the record says whether the grounding was evaluated and where the confidence came from", '"grounding_evaluated"] = False' in gp and '"confidence_source"] = "llm_self_report_unmeasured"' in gp and '"confidence_source"] = "jepa_calibrated"' in gp)

print("\n--- 34: the ids travel ---")
check("want completions, checkpoints, reactions and questions carry their contract id", '"want_id": wid' in src("scripts/want_completion.py") and '"checkpoint_id": cid' in src("scripts/want_checkpoints.py") and '"reaction_id": rid' in src("scripts/sensor_reactions.py") and '"question_id": x.get("id")' in src("scripts/question_lifecycle.py"))
print("\n%d/%d" % (sum(R), len(R))); sys.exit(0 if all(R) else 1)
