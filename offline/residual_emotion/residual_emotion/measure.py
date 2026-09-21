"""Project frozen residual dumps; raw and reference-standardized values remain distinct."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

from .io import read_residual


def measure(dump: Path, direction_dir: Path) -> dict[str, Any]:
    validation = json.loads((direction_dir / "validation.json").read_text())
    if validation.get("status") != "validated" or validation.get("unembedding", {}).get("status") != "passed":
        raise ValueError("direction is not fully admitted: held-out AUC and unembedding must pass")
    values = np.load(direction_dir / "direction.npz", allow_pickle=False)
    matrix = read_residual(dump)
    layer = int(values["layer"])
    vector = values["direction"].astype(np.float64)
    with np.errstate(all="ignore"):
        raw = float(matrix[layer] @ vector)
    if not np.isfinite(raw):
        raise ValueError(f"non-finite projection for {dump} against {direction_dir}")
    mean = float(values["control_mean"])
    std = float(values["control_std"])
    return {
        "concept": validation["concept"],
        "raw_projection": raw,
        "control_z": (raw - mean) / (std + 1e-12),
        "layer": layer,
        "pooling": str(values["pooling"]),
        "truth_status": "residual_projection_not_self_report_not_feeling_claim",
    }
