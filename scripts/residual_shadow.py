#!/usr/bin/env python3
"""A shadow receipt records what EmoClaw read; it never interprets, steers, sends, or delays.

The live server supplies the exact text shown to the generated EmoClaw reader, its
generated and applied deltas, and the state on either side.  This module only
validates and appends that evidence below memory/residual-emotion-shadow/.  The
offline residual instrument may later measure the same ``input_text``.  It has no
model/provider client and no authority over emotional state.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path

WS = os.environ.get("SPARK_WORKSPACE", os.path.expanduser("~/.vintos/workspace"))
ROOT = os.path.join(WS, "memory", "residual-emotion-shadow")
EVENTS = os.path.join(ROOT, "emoclaw-events.jsonl")
LOCK = os.path.join(ROOT, ".events.lock")
DIMENSIONS = (
    "Valence", "Arousal", "Dominance", "Safety", "Desire", "Connection",
    "Playfulness", "Curiosity", "Warmth", "Tension", "Groundedness",
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _finite_map(value) -> dict[str, float]:
    out = {}
    if not isinstance(value, dict):
        return out
    for key, raw in value.items():
        if key not in DIMENSIONS or isinstance(raw, bool):
            continue
        try:
            number = float(raw)
        except (TypeError, ValueError):
            continue
        if math.isfinite(number):
            out[key] = round(number, 6)
    return out


def _event_id(turn_id: str, surface: str, source: str, text: str, observed_at: str) -> str:
    stable = str(turn_id or "").strip()
    basis = "\x1f".join((stable or observed_at, surface, source, text))
    return "RESH-" + hashlib.sha256(basis.encode("utf-8")).hexdigest()[:20]


def record(*, input_text: str, source: str, surface: str = "", turn_id: str = "",
           generated_deltas=None, applied_deltas=None, pre_state=None, post_state=None,
           status: str = "completed", error: str = "", model: str = "",
           response_digest: str = "", test_mode: bool = False,
           observed_at: str = "") -> dict:
    """Append one idempotent, non-causal receipt; test turns are never written."""
    if test_mode:
        return {"recorded": False, "reason": "test_mode"}
    text = str(input_text or "")
    if not text.strip():
        return {"recorded": False, "reason": "empty_input"}
    at = str(observed_at or _now())
    row = {
        "schema": 1,
        "event_id": _event_id(turn_id, str(surface or "unknown"), str(source or "unknown"), text, at),
        "observed_at": at,
        "turn_id": str(turn_id or ""),
        "surface": str(surface or "unknown"),
        "source": str(source or "unknown"),
        "input_text": text,
        "input_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "model": str(model or ""),
        "status": status if status in ("completed", "failed") else "failed",
        "generated_deltas": _finite_map(generated_deltas),
        "applied_deltas": _finite_map(applied_deltas),
        "pre_state": _finite_map(pre_state),
        "post_state": _finite_map(post_state),
        "response_digest": str(response_digest or ""),
        "error": str(error or "")[:500],
        "residual_status": "pending_offline_measurement",
        "truth_status": "generated_emoclaw_read_and_state_receipt_not_residual_measurement",
        "causal_effect": "none_from_this_recorder",
    }
    Path(ROOT).mkdir(parents=True, exist_ok=True)
    with open(LOCK, "a+", encoding="utf-8") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        if os.path.exists(EVENTS):
            with open(EVENTS, encoding="utf-8") as src:
                for line in src:
                    try:
                        if json.loads(line).get("event_id") == row["event_id"]:
                            return {"recorded": False, "reason": "already_recorded", "event_id": row["event_id"]}
                    except Exception:
                        continue
        with open(EVENTS, "a", encoding="utf-8") as target:
            target.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
            target.flush(); os.fsync(target.fileno())
    return {"recorded": True, "event_id": row["event_id"]}


def pending(limit: int = 200) -> list[dict]:
    """Read bounded receipts for an explicit offline export; this mutates nothing."""
    rows = []
    try:
        with open(EVENTS, encoding="utf-8") as src:
            for line in src:
                try: rows.append(json.loads(line))
                except Exception: continue
    except FileNotFoundError:
        pass
    return rows[-max(1, min(int(limit), 5000)):]

