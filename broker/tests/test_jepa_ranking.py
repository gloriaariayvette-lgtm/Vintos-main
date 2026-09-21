#!/usr/bin/env python3
"""JEPA ranking and structured-context fixtures. All paths are scratch; no provider is reachable."""
from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent; REPO = HERE.parents[1]
HOME = Path(tempfile.mkdtemp(prefix="vintos-jepa-ranking-")); os.environ["HOME"] = str(HOME)
WS = HOME / ".vintos" / "workspace"; MEM = WS / "memory"; MEM.mkdir(parents=True)
R = []


def check(name, ok, detail=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + name + ((" -> " + str(detail)) if detail and not ok else ""))


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path); mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod); return mod


JP = load("jepa_predictor_fixture", REPO / "scripts" / "jepa_predictor.py")
RA = load("jepa_ranking_fixture", REPO / "scripts" / "jepa_ranking_audit.py")
CA = load("jepa_calibration_fixture", REPO / "scripts" / "jepa_calibration_audit.py")
JP.MEMORY = str(MEM); JP.MODEL = str(MEM / "model.pt"); JP.OUT = str(MEM / "prediction.json")
JP.SHADOW_MODEL = str(MEM / "shadow.pt"); JP.SHADOW_OUT = str(MEM / "shadow-prediction.json")
JP.CALIBRATION_AUDIT = str(MEM / "calibration.json"); JP.RANKING_AUDIT = str(MEM / "ranking.json")
JP.SHADOW_RANKING_AUDIT = str(MEM / "shadow-ranking.json")
RA.MEM = str(MEM); RA.HIST = str(MEM / "history.jsonl"); RA.LEDGER = str(MEM / "ledger.json"); RA.OUT = str(MEM / "ranking.json"); RA.MODEL = str(MEM / "model.pt")
check("ranking fixture is isolated from the live workspace", str(HOME) in RA.OUT and str(HOME) in JP.MODEL and ".vintos/workspace" in RA.OUT)


print("\n--- structured turn context ---")
turns = [
    {"role": "user", "speaker": "gloria", "surface": "avatar", "timestamp": "2026-09-18T10:00:00+00:00", "content": "same words"},
    {"role": "assistant", "speaker": "vintos", "surface": "reelroom", "timestamp": "2026-09-18T10:06:00+00:00", "content": "same words"},
]
structured = JP.format_context(turns, "structured-turns-v1")
legacy = JP.format_context(turns, "legacy-concat-v1")
check("structured context preserves speaker and surface", "SPEAKER=gloria" in structured and "SURFACE=avatar" in structured and "SPEAKER=vintos" in structured and "SURFACE=reelroom" in structured)
check("structured context preserves bounded temporal rhythm", "GAP=5_to_30m" in structured and "2026-09-18" not in structured)
check("production legacy rendering remains available", legacy == "same words \nsame words")


print("\n--- true-next ranking versus voice retrieval ---")
class Encoder:
    def encode(self, texts, show_progress_bar=False):
        out = []
        for text in texts:
            text = str(text)
            if "target" in text: out.append([1.0, 0.0, 0.0])
            elif "wrong-a" in text: out.append([0.0, 1.0, 0.0])
            elif "wrong-b" in text: out.append([0.0, 0.0, 1.0])
            else: out.append([0.0, 0.7, 0.7])  # familiar voice centroid prefers neither true target
        return out

base = datetime(2026, 9, 18, 10, 0, tzinfo=timezone.utc)
ledger = []
for i, suffix in enumerate(("past-old", "past", "target", "wrong-a", "wrong-b")):
    ledger.append({"timestamp": (base + timedelta(minutes=(i - 1) * 10)).isoformat(),
                   "gloria": "g-" + suffix, "vintos": "s-" + suffix})
forecast_ts = (base + timedelta(minutes=5)).timestamp()
history = [{"ts": forecast_ts, "iso": datetime.fromtimestamp(forecast_ts, timezone.utc).isoformat(), "checkpoint_id": "ck",
            "gloria": {"emb": [1.0, 0.0, 0.0]}, "self": {"emb": [1.0, 0.0, 0.0]}},
           # Same realized target: must not inflate the sample.
           {"ts": forecast_ts + 1, "iso": datetime.fromtimestamp(forecast_ts + 1, timezone.utc).isoformat(), "checkpoint_id": "ck",
            "gloria": {"emb": [1.0, 0.0, 0.0]}, "self": {"emb": [1.0, 0.0, 0.0]}}]
rows = RA.evaluate(history, ledger, Encoder(), checkpoint="ck", trained_before=0, pool_size=3)
check("one cron burst cannot count the same future twice", len(rows) == 2, rows)
check("both heads rank the actual next turn against same-speaker futures", {r["head"] for r in rows} == {"gloria", "self"} and all(r["rank"] == 1 and r["pool_size"] == 3 for r in rows), rows)
check("ranking keeps a separate familiar-voice control", all(r["voice_baseline_rank"] != r["rank"] for r in rows), rows)

enough = []
for i in range(30):
    enough.append({"head": "gloria", "rank": 1, "reciprocal_rank": 1.0, "top1": True, "pool_size": 6,
                   "voice_baseline_rank": 3, "voice_baseline_top1": False,
                   "recent_turn_baseline_rank": 2, "context_copy_baseline_rank": 4,
                   "pairwise_by_tier": {"later_future": True, "recent_echo": True}})
summary = RA._summary(enough, "gloria")
check("a verdict needs thirty prospective targets and must beat voice retrieval", summary["n"] == 30 and summary["state"] == "EVIDENCE_OF_PREDICTION")
check("fewer than thirty stays insufficient", RA._summary(enough[:29], "gloria")["state"] == "INSUFFICIENT")

cal_history = [{"ts": forecast_ts, "iso": "one", "checkpoint_id": "ck",
                "gloria": {"confidence": .5, "decode_similarity": .4, "emb": [1., 0., 0.]},
                "self": {"confidence": .5, "decode_similarity": .4, "emb": [1., 0., 0.]}},
               {"ts": forecast_ts + 1, "iso": "duplicate", "checkpoint_id": "ck",
                "gloria": {"confidence": .6, "decode_similarity": .4, "emb": [1., 0., 0.]},
                "self": {"confidence": .6, "decode_similarity": .4, "emb": [1., 0., 0.]}}]
cal_turns = [(forecast_ts + 10, "g-target", "s-target")]
cal_rows = CA.joined_rows(cal_history, cal_turns, Encoder(), "ck", 0)
check("calibration counts repeated forecasts of one realized exchange once", len(cal_rows) == 1 and cal_rows[0]["iso"] == "one", cal_rows)


print("\n--- stable checkpoint lifecycle ---")
Path(JP.MODEL).write_bytes(b"production checkpoint")
checkpoint = JP.checkpoint_fingerprint(JP.MODEL)
ready, receipt = JP.retrain_readiness(JP.MODEL, shadow=False)
check("an unaudited production checkpoint is held", ready is False and receipt["state"] == "HELD_UNAUDITED_CHECKPOINT")
Path(JP.RANKING_AUDIT).write_text(json.dumps({"checkpoint": checkpoint, "gloria": {"n": 30}, "self": {"n": 29}}))
ready, receipt = JP.retrain_readiness(JP.MODEL, shadow=False)
check("raw history cannot replace thirty realized ranking outcomes", ready is False and receipt["ranking"]["self"] == 29)
Path(JP.RANKING_AUDIT).write_text(json.dumps({"checkpoint": checkpoint, "gloria": {"n": 30}, "self": {"n": 30}}))
Path(JP.CALIBRATION_AUDIT).write_text(json.dumps({"checkpoint": "stale", "n_joined": 300}))
ready, receipt = JP.retrain_readiness(JP.MODEL, shadow=False)
check("a receipt from a different checkpoint cannot release retraining", ready is False and "calibration" in receipt["need"])
Path(JP.CALIBRATION_AUDIT).write_text(json.dumps({"checkpoint": checkpoint, "n_joined": 88, "n_holdout": 29, "verdict": "INSUFFICIENT"}))
ready, receipt = JP.retrain_readiness(JP.MODEL, shadow=False)
check("thirty ranking outcomes cannot bypass calibration's thirty-held-out law", ready is False and receipt["calibration_holdout_n"] == 29)
Path(JP.CALIBRATION_AUDIT).write_text(json.dumps({"checkpoint": checkpoint, "n_joined": 89, "n_holdout": 30, "verdict": "WITHHELD"}))
ready, receipt = JP.retrain_readiness(JP.MODEL, shadow=False)
check("completed measurement permits the next cycle even when the verdict is negative", ready is True and receipt["state"] == "READY_AFTER_AUDIT")

Path(JP.SHADOW_MODEL).write_bytes(b"shadow checkpoint")
shadow_checkpoint = JP.checkpoint_fingerprint(JP.SHADOW_MODEL)
Path(JP.SHADOW_RANKING_AUDIT).write_text(json.dumps({"checkpoint": shadow_checkpoint, "gloria": {"n": 30}, "self": {"n": 30}}))
ready, receipt = JP.retrain_readiness(JP.SHADOW_MODEL, shadow=True)
check("the shadow waits on its own ranking receipt without borrowing production calibration", ready is True and receipt["checkpoint"] == shadow_checkpoint)

context_id = "ctx-1"
Path(JP.OUT).write_text(json.dumps({"checkpoint_id": checkpoint, "context_id": context_id, "prediction_id": "old"}))
check("same checkpoint plus same context is not predicted twice", JP.unchanged_forecast(JP.OUT, checkpoint, context_id) is True)
check("a changed context still earns a fresh prospective prediction", JP.unchanged_forecast(JP.OUT, checkpoint, "ctx-2") is False)
check("a new checkpoint may forecast the same context once", JP.unchanged_forecast(JP.OUT, shadow_checkpoint, context_id) is False)


print("\n--- shadow boundary ---")
src = (REPO / "scripts" / "jepa_predictor.py").read_text()
check("structured model has separate checkpoint output and history", "jepa-predictor-structured-shadow.pt" in src and "jepa-prediction-structured-shadow-history.jsonl" in src)
check("shadow prediction is structurally barred from steering", '"steering_allowed": (False if shadow else' in src and '"shadow_only": bool(shadow)' in src)
check("head-specific confidence is confined to the shadow architecture", 'head-specific-confidence-v2' in src and 'train(SHADOW_MODEL, "structured-turns-v1", "head-specific-confidence-v2", validation_fraction=0.2)' in src)
check("shadow training selects weights on a later time slice", '"kind": "latest_time_slice"' in src and 'net.load_state_dict(best_state)' in src and 'early stop epoch' in src)
check("duplicate suppression happens before the encoder is loaded", src.index("if unchanged_forecast(") < src.index("enc = encoder()", src.index("def predict(")))
check("forced retraining is explicit and absent from ordinary scheduler commands", 'elif cmd == "train-force"' in src and 'elif cmd == "train-shadow-force"' in src)

print("\n%d/%d" % (sum(R), len(R))); sys.exit(0 if all(R) else 1)
