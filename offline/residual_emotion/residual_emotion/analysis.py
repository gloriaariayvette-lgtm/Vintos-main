"""Nested, grouped validation of contrastive residual directions."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Iterable

import numpy as np
from sklearn.decomposition import PCA
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import GroupKFold

from .dataset import validate
from .io import atomic_json, read_jsonl, read_residual


def _unit(vector: np.ndarray) -> np.ndarray:
    norm = float(np.linalg.norm(vector))
    if not math.isfinite(norm) or norm <= 1e-12:
        raise ValueError("direction has zero or non-finite norm")
    return vector / norm


def fit_direction(target: np.ndarray, control: np.ndarray, variance: float = 0.5) -> np.ndarray:
    if target.ndim != 2 or control.ndim != 2 or target.shape[1] != control.shape[1]:
        raise ValueError("target/control matrices are incompatible")
    vector = target.mean(axis=0) - control.mean(axis=0)
    centered = control - control.mean(axis=0)
    if len(control) > 1 and np.any(centered):
        pca = PCA().fit(centered)
        count = int(np.searchsorted(np.cumsum(pca.explained_variance_ratio_), variance) + 1)
        for component in pca.components_[:count]:
            vector = vector - float(vector @ component) * component
    return _unit(vector)


def auc(target: np.ndarray, control: np.ndarray, direction: np.ndarray) -> float:
    scores = np.concatenate([target @ direction, control @ direction])
    labels = np.concatenate([np.ones(len(target)), np.zeros(len(control))])
    return float(roc_auc_score(labels, scores))


def load_work(work_dir: Path, pooling: str) -> tuple[list[dict[str, Any]], np.ndarray, np.ndarray]:
    rows = read_jsonl(work_dir / "rows.jsonl")
    target, control = [], []
    for index in range(len(rows)):
        target.append(read_residual(work_dir / "dumps" / f"{index:06d}_target_{pooling}.f32"))
        control.append(read_residual(work_dir / "dumps" / f"{index:06d}_control_{pooling}.f32"))
    target_array = np.stack(target)
    control_array = np.stack(control)
    if target_array.shape != control_array.shape:
        raise ValueError("target and control dumps have different shapes")
    return rows, target_array, control_array


def grouped_layer_curve(rows: list[dict[str, Any]], target: np.ndarray, control: np.ndarray,
                        folds: int = 5) -> list[dict[str, Any]]:
    groups = np.array([str(row["semantic_set"]) for row in rows])
    unique = np.unique(groups)
    if len(unique) < folds:
        raise ValueError(f"need at least {folds} semantic sets")
    splitter = GroupKFold(n_splits=folds)
    curves = []
    indices = np.arange(len(rows))
    for layer in range(target.shape[1]):
        fold_scores = []
        for train, test in splitter.split(indices, groups=groups):
            try:
                direction = fit_direction(target[train, layer, :], control[train, layer, :])
                fold_scores.append(auc(target[test, layer, :], control[test, layer, :], direction))
            except ValueError:
                fold_scores.append(0.5)
        curves.append({
            "layer": layer,
            "auc_mean": float(np.mean(fold_scores)),
            "auc_std": float(np.std(fold_scores)),
            "fold_aucs": [float(value) for value in fold_scores],
        })
    return curves


def fit(work_dir: Path, output_dir: Path, auc_minimum: float = 0.85) -> dict[str, Any]:
    validate(work_dir / "rows.jsonl", require_curated=False)
    source_manifest = work_dir / "source.manifest.json"
    if not source_manifest.exists() or json.loads(source_manifest.read_text()).get("curated") is not True:
        raise ValueError("prepared work is missing its curated source manifest")
    output_dir.mkdir(parents=True, exist_ok=True)
    pooling_reports = {}
    best = None
    for pooling in ("final", "mean"):
        rows, target, control = load_work(work_dir, pooling)
        curves = grouped_layer_curve(rows, target, control)
        candidate = max(curves, key=lambda row: row["auc_mean"])
        pooling_reports[pooling] = {"best": candidate, "layers": curves}
        if best is None or candidate["auc_mean"] > best["auc_mean"]:
            best = {**candidate, "pooling": pooling, "target": target, "control": control, "rows": rows}
    assert best is not None
    layer = int(best["layer"])
    direction = fit_direction(best["target"][:, layer, :], best["control"][:, layer, :])
    control_projection = best["control"][:, layer, :] @ direction
    status = "validated" if best["auc_mean"] >= auc_minimum else "rejected_below_auc"
    np.savez_compressed(
        output_dir / "direction.npz",
        direction=direction.astype(np.float32), layer=layer, pooling=best["pooling"],
        control_mean=float(control_projection.mean()), control_std=float(control_projection.std()),
    )
    report = {
        "schema": 1,
        "concept": best["rows"][0]["concept"],
        "truth_status": "held_out_grouped_validation",
        "status": status,
        "auc_minimum": auc_minimum,
        "selected_layer": layer,
        "selected_pooling": best["pooling"],
        "held_out_auc": float(best["auc_mean"]),
        "held_out_auc_std": float(best["auc_std"]),
        "denoise_control_variance": 0.5,
        "model_identity_required": "gemma-4-26b-a4b-it-uncensored",
        "architecture_caveat": "A4B MoE extension; paper validation set was dense",
        "pooling_reports": pooling_reports,
        "unembedding": {"status": "not_run", "admission_blocking": True},
    }
    atomic_json(output_dir / "validation.json", report)
    return report


def cosine_matrix(direction_files: Iterable[Path]) -> dict[str, Any]:
    names, vectors = [], []
    for path in direction_files:
        validation = json.loads((path.parent / "validation.json").read_text())
        if validation.get("status") != "validated":
            continue
        values = np.load(path, allow_pickle=False)
        names.append(str(validation["concept"]))
        vectors.append(_unit(values["direction"].astype(np.float64)))
    matrix = np.stack(vectors) @ np.stack(vectors).T if vectors else np.zeros((0, 0))
    return {"concepts": names, "cosine": matrix.tolist(), "truth_status": "descriptive_not_dimensionality_proof"}
