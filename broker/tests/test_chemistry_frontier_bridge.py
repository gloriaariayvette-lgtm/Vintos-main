#!/usr/bin/env python3
"""Frontier bridge: scratch stores, no network, no provider calls."""
import importlib.util, json, os, sys, tempfile

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
HOME = tempfile.mkdtemp(prefix="vintos-chem-bridge-")
WS = os.path.join(HOME, ".vintos", "workspace")
MEM = os.path.join(WS, "memory")
os.makedirs(MEM, exist_ok=True)
os.environ["HOME"] = HOME; os.environ["SPARK_WORKSPACE"] = WS
json.dump({"heading": "learning by making molecular structures"},
          open(os.path.join(MEM, "living-trajectory.json"), "w"))

def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec); sys.modules[name] = mod
    spec.loader.exec_module(mod); return mod

lab = load("chemistry_lab", os.path.join(REPO, "scripts", "chemistry_lab.py"))
bridge = load("chemistry_frontier_bridge", os.path.join(REPO, "scripts", "chemistry_frontier_bridge.py"))
assert HOME in bridge.INTEREST and HOME in bridge.SURFACES
assert not bridge.INTEREST.startswith("/home/gloria")

note = {"at": "2026-09-13T00:00:00+00:00", "source_accessions": ["P12345"],
        "factual_observation": "The sourced molecular structure contains a compact repeat.",
        "attention": "The compact structure caught my attention.",
        "next_question": "How does this molecular structure keep its shape?"}
row = bridge.assess(note, source_query_succeeded=True)
assert row["flagged_for_next_lab_session"] is True, row
assert row["truth_status"] == "routing_priority_from_independent_receipts_not_truth_or_importance"
assert "model_confidence" not in row and "vibes" not in json.dumps(row)

block, ids = bridge.frontier_block()
assert ids == [row["entry_id"]] and row["entry_id"] in block
base = {"sources": [], "total_chars": 3, "context_sha256": "old"}
context, receipt, offered = bridge.add_to_context("him", base)
assert offered == ids and len(context) <= 4 + bridge.BLOCK_CHARS + 80
assert receipt["frontier_interest_entry_ids"] == ids
assert any(x.get("name") == "flagged_lab_findings" for x in receipt["sources"])
assert any(x.get("kind") == "frontier_context" for x in lab._jsonl(lab.RECEIPTS))

# Being shown is not being acknowledged. It stays pending until the returned plan names it.
first = bridge.record_delivery("CHEM-1", "claude", ids, [], state="responded")
assert first["unacknowledged_entry_ids"] == ids and bridge.status()["pending"] == 1
second = bridge.record_delivery("CHEM-2", "sol", ids, ids + ["invented"], state="responded")
assert second["acknowledged_entry_ids"] == ids and "invented" not in second["acknowledged_entry_ids"]
assert bridge.status()["acknowledged"] == 1 and bridge.frontier_block() == ("", [])

# A duplicate question is penalized; recurrence is history, not evidence for itself.
repeat = bridge.assess(dict(note, at="2026-09-14T00:00:00+00:00"), source_query_succeeded=True)
assert repeat["score_components"]["repetition_penalty"] < 0
assert repeat["flagged_for_next_lab_session"] is False and "duplicate_evidence_suppressed" in repeat["reason_for_score"]
assert bridge._evidence_key(dict(row, evidence_sha256=None)) == row["evidence_sha256"]
assert bridge.frontier_block() == ("", [])
fresh = bridge.assess(dict(note, at="2026-09-15T00:00:00+00:00", source_accessions=["P67890"]),
                      source_query_succeeded=True)
assert fresh["flagged_for_next_lab_session"] is True and fresh["evidence_sha256"] != row["evidence_sha256"]
assert bridge.frontier_block()[1] == [fresh["entry_id"]]

source = open(os.path.join(REPO, "scripts", "chemistry_frontier_bridge.py")).read()
assert "requests" not in source and "urllib" not in source and "atelier" not in source.lower()
print("18/18 passed")
