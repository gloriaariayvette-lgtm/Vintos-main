"""Join frozen residual measurements to frozen EmoClaw exports; never invoke EmoClaw."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .io import append_jsonl, read_jsonl


def join(emoclaw_path: Path, residual_path: Path, output_path: Path) -> dict[str, int]:
    emoclaw = {str(row["turn_id"]): row for row in read_jsonl(emoclaw_path)}
    residual = {str(row["turn_id"]): row for row in read_jsonl(residual_path)}
    ids = sorted(emoclaw.keys() & residual.keys())
    rows = [{
        "turn_id": turn_id,
        "timestamp": residual[turn_id].get("timestamp") or emoclaw[turn_id].get("timestamp"),
        "input_text": residual[turn_id].get("input_text", ""),
        "emoclaw_scores": emoclaw[turn_id].get("scores", {}),
        "residual_measurements": residual[turn_id].get("measurements", {}),
        "agreement": "not_computed_scale_not_calibrated",
        "divergence_points": [],
        "truth_status": "offline_join_no_outcome_claim",
    } for turn_id in ids]
    output_path.unlink(missing_ok=True)
    append_jsonl(output_path, rows)
    return {"emoclaw": len(emoclaw), "residual": len(residual), "joined": len(rows)}
