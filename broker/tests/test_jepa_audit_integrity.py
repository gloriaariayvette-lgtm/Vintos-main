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

ck = "fixture-checkpoint"
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
