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
RA.MEM = str(MEM); RA.HIST = str(MEM / "history.jsonl"); RA.LEDGER = str(MEM / "ledger.json"); RA.OUT = str(MEM / "ranking.json"); RA.MODEL = str(MEM / "model.pt")
check("ranking fixture is isolated from the live workspace", str(HOME) in RA.OUT and ".vintos/workspace" in RA.OUT)


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


print("\n--- shadow boundary ---")
src = (REPO / "scripts" / "jepa_predictor.py").read_text()
check("structured model has separate checkpoint output and history", "jepa-predictor-structured-shadow.pt" in src and "jepa-prediction-structured-shadow-history.jsonl" in src)
check("shadow prediction is structurally barred from steering", '"steering_allowed": (False if shadow else' in src and '"shadow_only": bool(shadow)' in src)
check("head-specific confidence is confined to the shadow architecture", 'head-specific-confidence-v2' in src and 'train(SHADOW_MODEL, "structured-turns-v1", "head-specific-confidence-v2")' in src)

print("\n%d/%d" % (sum(R), len(R))); sys.exit(0 if all(R) else 1)
