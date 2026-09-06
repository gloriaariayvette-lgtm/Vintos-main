#!/usr/bin/env python3
"""A tactical reply can be stored as an act but cannot witness itself."""
import importlib.util
import json
import os
import shutil
import sys
import tempfile
import types

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCRIPTS = os.path.join(ROOT, "scripts")
sys.path.insert(0, SCRIPTS)
import evidence_provenance as EP


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


R = []
def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + (("  ->  " + str(detail)[:100]) if detail else ""))
    R.append(bool(ok))


tmp = tempfile.mkdtemp(prefix="prov-test-")
try:
    old_events, old_memory = EP.EVENTS, EP.MEMORY
    EP.MEMORY, EP.EVENTS = tmp, os.path.join(tmp, "writer-events.jsonl")
    # the relational compare below reaches prediction_ledger; without this it appended consume_refused rows to
    # HIS relational/self prediction ledgers on every deploy (found 2026-09-06 while hunting the ridge leak)
    import prediction_ledger as _PL
    old_pl_memory = _PL.MEMORY; _PL.MEMORY = tmp
    tactical = {"turn_id": "t-1", "surface": "avatar",
                "input_provenance": "counterpart_verbatim",
                "output_provenance": "stratagem_influenced", "may_witness": False,
                "capsule_commitment": {}}
    check("tactical output cannot witness", not EP.output_can_witness(tactical))
    check("counterpart input remains verbatim",
          EP.normalize(tactical)["input_provenance"] == "counterpart_verbatim")
    os.environ[EP.ENV_KEY] = "{broken"
    malformed = EP.normalize()
    check("malformed provenance is unknown, never ordinary",
          malformed["output_provenance"] == "unknown" and not malformed["may_witness"], malformed)
    os.environ.pop(EP.ENV_KEY, None)
    legacy = EP.normalize()
    check("genuinely absent envelope is explicit legacy", legacy["envelope_state"] == "absent_legacy")
    EP.writer_event("wal", "completed", tactical)
    event = json.loads(open(EP.EVENTS).readline())
    check("writer outcome is tied to the turn", event["turn_id"] == "t-1" and event["writer"] == "wal", event)

    # The broker test runtime intentionally has no requests package. These
    # writer tests replace network calls, so a tiny import stub is sufficient.
    sys.modules.setdefault("requests", types.SimpleNamespace())
    WAL = load("wal_under_test", os.path.join(ROOT, "bin", "wal-extract.py"))
    captured = {}
    class Response:
        def json(self): return {"choices": [{"message": {"content": "NONE"}}]}
    def fake_post(url, json=None, **kwargs):
        captured["prompt"] = json["messages"][1]["content"]
        return Response()
    WAL.requests.post = fake_post
    WAL.extract("Gloria says the launch is Friday", "SECRET TACTICAL REPLY", tactical)
    check("WAL sees her verbatim but not tactical reply",
          "launch is Friday" in captured["prompt"] and "SECRET TACTICAL REPLY" not in captured["prompt"])

    IMP = load("imprint_under_test", os.path.join(ROOT, "bin", "imprint.py"))
    IMP.IMPRINT_FILE = os.path.join(tmp, "imprints.json")
    IMP.get_anchors = lambda: {"timestamp": "2026-08-28T00:00:00", "emoclaw": {"Warmth": .9},
                               "avatar_color": "red", "avatar_expression": "smirk"}
    seen = {}
    def fake_llm(system, user, temperature=.5):
        seen["prompt"] = user
        return '{"narrative":"Her words landed.","salience":0.5}'
    IMP.llm = fake_llm
    IMP.capture_imprint("her independent words", "SECRET TACTICAL REPLY", tactical)
    imprint = json.load(open(IMP.IMPRINT_FILE))[-1]
    check("imprint preserves tactical reply only as an ineligible act",
          imprint["vintos_said"] == "SECRET TACTICAL REPLY"
          and not imprint["generated_output_witness_eligible"]
          and "SECRET TACTICAL REPLY" not in seen["prompt"], imprint)

    SP = load("self_prediction_under_test", os.path.join(SCRIPTS, "self-prediction.py"))
    SP.PREDICTION_FILE = os.path.join(tmp, "self.json")
    SP.HELD_LOG = os.path.join(tmp, "self-held.jsonl")
    SP.BLIND_SPOTS_DATA = os.path.join(tmp, "history.json")
    SP.BLIND_SPOTS_LOG = os.path.join(tmp, "blush.md")
    SP.get_current_state = lambda: {d: 0.5 for d in SP.DIMENSIONS}
    json.dump({"timestamp": "now", "predicted_state": {d: 0.4 for d in SP.DIMENSIONS},
               "provenance": tactical}, open(SP.PREDICTION_FILE, "w"))
    held = SP.compare_prediction()
    check("self-prediction from tactic is HELD", held.get("outcome") == "HELD", held)
    check("HELD prediction does not train history", not os.path.exists(SP.BLIND_SPOTS_DATA))

    RM = load("relational_mismatch_under_test", os.path.join(SCRIPTS, "relational-mismatch.py"))
    RM.PREDICTION_FILE = os.path.join(tmp, "rel.json")
    RM.HELD_LOG = os.path.join(tmp, "rel-held.jsonl")
    RM.MISMATCH_LOG = os.path.join(tmp, "mismatch.md")
    json.dump({"predicted_warmth": .8, "predicted_tension": .1, "predicted_valence": .8,
               "vintos_message": "tactical act", "provenance": tactical},
              open(RM.PREDICTION_FILE, "w"))
    held = RM.compare_prediction("her independent reply", .2, .8, .2)
    check("relational prediction from tactic is HELD", held.get("outcome") == "HELD", held)
    check("HELD relational prediction creates no mismatch evidence", not os.path.exists(RM.MISMATCH_LOG))
finally:
    EP.EVENTS, EP.MEMORY = old_events, old_memory
    _PL.MEMORY = old_pl_memory
    os.environ.pop(EP.ENV_KEY, None)
    shutil.rmtree(tmp, ignore_errors=True)

print("\n%d/%d passed" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
