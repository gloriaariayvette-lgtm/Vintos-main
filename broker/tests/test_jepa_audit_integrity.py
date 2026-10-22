#!/usr/bin/env python3
"""JEPA evidence and consumer boundaries; scratch stores, fake encoder, no sends."""
import copy
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import types
from datetime import datetime

ROOT = Path(__file__).resolve().parents[2]
HOME = tempfile.mkdtemp(prefix="jepa-integrity-")
os.environ["HOME"] = HOME
os.environ["SPARK_WORKSPACE"] = HOME + "/workspace"
MEM = Path(HOME) / "workspace/memory"
MEM.mkdir(parents=True)
sys.path.insert(0, str(ROOT / "scripts"))
def no_send(*a, **k):
    raise AssertionError("no sends or model calls in this suite")
sys.modules["requests"] = types.SimpleNamespace(post=no_send, get=no_send)
import numpy as np
import calibration as C
import jepa_ranking_audit as A
import jepa_calibration_audit as CA
import latent_preparation as LP
import living_trajectory as LT
import presence_audit as PA

assert C.MEMORY == LP.MEMORY == PA.MEMORY == str(MEM)
assert sys.modules["requests"].post is no_send
Path(C.MODEL).write_bytes(b"test checkpoint")
ck = C.checkpoint_fingerprint()
audit = {"n_joined": 100, "n_holdout": 31, "axis_lockstep_corr": .3,
         "criteria_version": C.CRITERIA_VERSION, "checkpoint": ck,
         "holdout_protocol": "prospective-checkpoint-v1",
         "g": {"monotonicity_conf_vs_err": -.6, "CONTROL_dsim_vs_err": -.2, "wrong_but_confident": []}}
Path(C.AUDIT).write_text(json.dumps(audit))
ranking = {"checkpoint": ck, "criteria_version": A.CRITERIA_VERSION,
           "gloria": {"state": "EVIDENCE_OF_PREDICTION"}}
rank_path = MEM / "jepa-ranking-audit.json"
rank_path.write_text(json.dumps(ranking))
now = float(int(time.time()))
forecast = {"source": "jepa", "predicted_at": datetime.fromtimestamp(now).isoformat(),
            "checkpoint_id": ck, "qualification": {"gloria": "qualified"},
            "confidence": .8, "novelty": .1, "gloria": {"confidence": .8}}
assert C.forecast_allowed(forecast, now=now)
for change in ({"checkpoint_id": "old"}, {"shadow_only": True}, {"qualification": {}},
               {"predicted_at": datetime.fromtimestamp(now - 7201).isoformat()},
               {"predicted_at": datetime.fromtimestamp(now + 1).isoformat()},
               {"gloria": {"confidence": float("nan")}},
               {"gloria": {"confidence": .5, "confidence_placeholder": True}}):
    assert not C.forecast_allowed(dict(forecast, **change), now=now), change
for change in ({"checkpoint": "old"}, {"criteria_version": "old"},
               {"gloria": {"state": "NO_EVIDENCE_BEYOND_VOICE_RETRIEVAL"}}):
    rank_path.write_text(json.dumps(dict(ranking, **change)))
    assert not C.forecast_allowed(forecast, now=now), change
rank_path.write_text(json.dumps(ranking))
assert not C.forecast_allowed(dict(forecast, self={"source": "self-head-v2", "confidence": .9}), "self", now)
small = copy.deepcopy(audit)
small["g"]["n_holdout"] = 2
assert C.verdict("gloria", audit=small)["state"] == "INSUFFICIENT"
print("PASS current checkpoint, freshness, per-head count, ranking and confidence required together")

Path(LP.JEPA).write_text(json.dumps(forecast))
assert LP.signal()[3] == "jepa"
entry = {"type": "readiness", "forecast": forecast, "content": "a posture"}
assert LT.readiness_allowed(entry)
assert not LT.readiness_allowed({"type": "readiness", "content": "old ungated posture"})
rank_path.unlink()
assert not LT.readiness_allowed(entry)
Path(LP.CACHE).write_text(json.dumps([entry, {"type": "creative", "content": "keep"}]))
LP.voice = no_send
LP.main()
assert json.loads(Path(LP.CACHE).read_text()) == [{"type": "creative", "content": "keep"}]
print("PASS cached readiness is revoked without a current release and cannot invoke a model")

assert A._rank([.4, .4, .4]) == 3
assert A._rank([.5, .3, .4]) == 1
rows = [{"head": "gloria", "rank": 1, "top1": True, "reciprocal_rank": 1., "pool_size": 6, "voice_baseline_rank": 2,
         "recent_turn_baseline_rank": 3, "context_copy_baseline_rank": 2} for _ in range(30)]
assert A._summary(rows, "gloria")["state"] == "EVIDENCE_OF_PREDICTION"
rows[0].pop("context_copy_baseline_rank")
assert A._summary(rows, "gloria")["state"] == "INSUFFICIENT"
print("PASS ties cannot favor the target and incomplete controls cannot release")

class Encoder:
    def encode(self, texts, **kw):
        return np.asarray([[1., 0.] for _ in texts])
triple = {"confidence": .7, "decode_similarity": .8, "emb": [1., 0.]}
hist = [{"checkpoint_id": ck, "ts": t, "iso": str(t), "gloria": triple,
         "self": dict(triple, source="self-head-v2", checkpoint_id="separate")} for t in (1, 2, 4)]
turns = [(3, "", "first self reply"), (5, "one her turn", "second self reply")]
joined = CA.joined_rows(hist, turns, Encoder(), ck, 0)
assert len(joined) == 1 and joined[0]["g_err"] == 0 and joined[0]["s_err"] is None
for h in hist:
    h["legacy_self"] = dict(triple, checkpoint_id=ck)
joined = CA.joined_rows(hist, turns, Encoder(), ck, 0)
assert sum(r["g_err"] is not None for r in joined) == 1
assert sum(r["s_err"] is not None for r in joined) == 2
print("PASS each speaker target counts once and separate self weights cannot borrow shared attribution")

PA.archive_labels([{"id": "old", "timestamp": "2026-09-01", "composite": .4, "reply": "not retained"}])
PA.archive_labels([{"id": "old", "composite": .4}, {"id": "new", "composite": .8}])
labels = [json.loads(x) for x in (MEM / "presence-audit-history.jsonl").read_text().splitlines()]
assert len(labels) == 2 and all("reply" not in r for r in labels)
print("PASS rubric history retains unique labels without copying conversations")

# The existing daily ranking job invokes self evaluation once, using its encoder.
calls = []
sys.modules["jepa_predictor"] = types.SimpleNamespace(encoder=lambda: Encoder())
sys.modules["jepa_self_head"] = types.SimpleNamespace(run_eval=lambda **kw: calls.append(kw["enc"]), exchanges=lambda: [])
saved_argv = sys.argv
sys.argv = ["jepa_ranking_audit.py"]
A.main()
assert len(calls) == 1 and isinstance(calls[0], Encoder)
sys.argv = ["jepa_ranking_audit.py", "--shadow"]
A.main()
assert len(calls) == 1
sys.argv = saved_argv
print("PASS scheduled production ranking also evaluates independent self; shadow does not")
