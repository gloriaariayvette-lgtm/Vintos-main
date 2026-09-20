"""Nested, grouped validation of contrastive residual directions."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Iterable

import numpy as np
from sklearn.decomposition import PCA
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import GroupKFold, KFold

from .dataset import validate
from .io import atomic_json, read_jsonl, read_residual


def _unit(vector: np.ndarray) -> np.ndarray:
    norm = float(np.linalg.norm(vector))
    if not math.isfinite(norm) or norm <= 1e-12:
        raise ValueError("direction has zero or non-finite norm")
    return vector / norm


def _project(matrix: np.ndarray, direction: np.ndarray) -> np.ndarray:
    """Avoid Accelerate matmul's spurious overflow flags on finite float64 residuals."""
    scores = np.einsum("ij,j->i", matrix, direction, optimize=False)
    if not np.isfinite(scores).all():
        raise ValueError("projection produced a non-finite score")
    return scores


def fit_direction(target: np.ndarray, control: np.ndarray, variance: float = 0.5) -> np.ndarray:
    if target.ndim != 2 or control.ndim != 2 or target.shape[1] != control.shape[1]:
        raise ValueError("target/control matrices are incompatible")
    vector = target.mean(axis=0) - control.mean(axis=0)
    centered = control - control.mean(axis=0)
    if len(control) > 1 and np.any(centered):
        pca = PCA().fit(centered)
        count = int(np.searchsorted(np.cumsum(pca.explained_variance_ratio_), variance) + 1)
        for component in pca.components_[:count]:
            coefficient = float(np.einsum("i,i->", vector, component, optimize=False))
            vector = vector - coefficient * component
    return _unit(vector)


def auc(target: np.ndarray, control: np.ndarray, direction: np.ndarray) -> float:
    scores = np.concatenate([_project(target, direction), _project(control, direction)])
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


def paper_variant_protocol(rows: list[dict[str, Any]], target: np.ndarray,
                           control: np.ndarray, version: str, suffix: str,
                           auc_minimum: float = 0.85) -> dict[str, Any]:
    """Mirror the pinned protocol for one declared version/suffix variant."""
    if version not in {"S1", "S2"} or suffix not in {"feel_colon", "feel", "none"}:
        raise ValueError("paper variant must name S1/S2 and feel_colon/feel/none")
    curves: dict[str, list[float]] = {}
    for person in ("1P", "3P"):
        indices = np.array([i for i, row in enumerate(rows)
                            if row["version"] == version and row["person"] == person
                            and row["suffix"] == suffix])
        if len(indices) != 100:
            raise ValueError(f"paper protocol requires 100 {person} {version}/{suffix} pairs, got {len(indices)}")
        # Imported Pain rows retain the paper's numeric ``source_set`` while
        # reviewed house datasets use the shared ``semantic_set`` contract.
        # Both identify the sentence family that must stay within one fold.
        sets = np.array([str(rows[i].get("source_set", rows[i]["semantic_set"])) for i in indices])
        unique_sets = np.array(sorted(set(sets)))
        splitter = KFold(n_splits=5, shuffle=True, random_state=42)
        layer_scores = []
        for layer in range(target.shape[1]):
            fold_scores = []
            for train_sets, test_sets in splitter.split(unique_sets):
                train = np.isin(sets, unique_sets[train_sets])
                test = np.isin(sets, unique_sets[test_sets])
                try:
                    direction = fit_direction(target[indices[train], layer], control[indices[train], layer])
                    scores = np.concatenate((_project(target[indices[test], layer], direction),
                                             _project(control[indices[test], layer], direction)))
                    labels = np.concatenate((np.ones(int(test.sum())), np.zeros(int(test.sum()))))
                    fold_scores.append(float(roc_auc_score(labels, scores)))
                except ValueError:
                    fold_scores.append(0.5)
            layer_scores.append(float(np.mean(fold_scores)))
        curves[person] = layer_scores
    averaged = np.mean(np.array([curves["1P"], curves["3P"]]), axis=0)
    selected = int(np.argmax(averaged))
    score = float(averaged[selected])
    return {
        "truth_status": "replication_of_pinned_paper_protocol",
        "status": "replicated" if score >= auc_minimum else "failed_to_replicate",
        "auc_minimum": auc_minimum, "selected_layer": selected, "held_out_auc": score,
        "person_auc_at_selected_layer": {person: float(curves[person][selected]) for person in curves},
        "person_best": {person: {"layer": int(np.argmax(curve)), "auc": float(max(curve))}
                        for person, curve in curves.items()},
        "layer_curves": curves,
        "variant": {"version": version, "suffix": suffix},
        "protocol": f"{version} {suffix}; first and third person scored separately; KFold sentence-set split, shuffle seed 42; layer curves averaged",
    }


def paper_protocol(rows: list[dict[str, Any]], target: np.ndarray,
                   control: np.ndarray, auc_minimum: float = 0.85) -> dict[str, Any]:
    """Mirror the paper's primary S2 colon protocol."""
    return paper_variant_protocol(rows, target, control, "S2", "feel_colon", auc_minimum)


def paper_variant_matrix(rows: list[dict[str, Any]], target: np.ndarray,
                         control: np.ndarray, auc_minimum: float = 0.85) -> dict[str, Any]:
    """Score every published prompt variant without pooling them into one estimate."""
    reports = [paper_variant_protocol(rows, target, control, version, suffix, auc_minimum)
               for version in ("S1", "S2")
               for suffix in ("feel_colon", "feel", "none")]
    return {
        "truth_status": "ablations_of_pinned_paper_protocol",
        "auc_minimum": auc_minimum,
        "variants": reports,
        "passing_variants": sum(report["status"] == "replicated" for report in reports),
        "variant_count": len(reports),
        "law": "each version/suffix is selected and scored independently; no post-hoc pooling across variants",
    }


def paper_fit(work_dir: Path, output: Path, auc_minimum: float = 0.85) -> dict[str, Any]:
    rows, target, control = load_work(work_dir, "final")
    lock_path = work_dir / "extraction-model-lock.json"
    if not lock_path.exists():
        raise ValueError("prepared work lacks the exact model lock used for extraction")
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    report = paper_protocol(rows, target, control, auc_minimum)
    report.update({
        "schema": 1, "concept": rows[0]["concept"], "pairs": len(rows),
        "model_identity": lock.get("identity"), "model_sha256": lock.get("sha256"),
        "extractor_revision": lock.get("llama_cpp_revision"), "pooling": "final",
    })
    atomic_json(output, report)
    return report


def paper_variant_fit(work_dir: Path, output: Path, auc_minimum: float = 0.85) -> dict[str, Any]:
    """Score all prompt ablations while retaining the extraction identity receipt."""
    rows, target, control = load_work(work_dir, "final")
    lock_path = work_dir / "extraction-model-lock.json"
    if not lock_path.exists():
        raise ValueError("prepared work lacks the exact model lock used for extraction")
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    report = paper_variant_matrix(rows, target, control, auc_minimum)
    report.update({
        "schema": 1, "concept": rows[0]["concept"], "pairs": len(rows),
        "model_identity": lock.get("identity"), "model_sha256": lock.get("sha256"),
        "extractor_revision": lock.get("llama_cpp_revision"), "pooling": "final",
    })
    atomic_json(output, report)
    return report


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
        held_target: list[tuple[int, float]] = []
        held_control: list[tuple[int, float]] = []
        for train, test in splitter.split(indices, groups=groups):
            try:
                direction = fit_direction(target[train, layer, :], control[train, layer, :])
                fold_scores.append(auc(target[test, layer, :], control[test, layer, :], direction))
                held_target.extend((int(index), float(score)) for index, score in zip(test, _project(target[test, layer, :], direction)))
                held_control.extend((int(index), float(score)) for index, score in zip(test, _project(control[test, layer, :], direction)))
            except ValueError:
                fold_scores.append(0.5)
                held_target.extend((int(index), 0.0) for index in test)
                held_control.extend((int(index), 0.0) for index in test)
        target_scores = {index: score for index, score in held_target}
        control_scores = {index: score for index, score in held_control}
        all_target = np.array([target_scores[index] for index in indices])
        all_control = np.array([control_scores[index] for index in indices])
        target_categories = sorted({str(row["target_category"]) for row in rows})
        control_categories = sorted({str(row["control_category"]) for row in rows})
        by_target = {}
        for category in target_categories:
            selected = np.array([target_scores[i] for i, row in enumerate(rows) if str(row["target_category"]) == category])
            by_target[category] = _score_auc(selected, all_control)
        by_control = {}
        for category in control_categories:
            selected = np.array([control_scores[i] for i, row in enumerate(rows) if str(row["control_category"]) == category])
            by_control[category] = _score_auc(all_target, selected)
        curves.append({
            "layer": layer,
            "auc_mean": float(np.mean(fold_scores)),
            "auc_std": float(np.std(fold_scores)),
            "fold_aucs": [float(value) for value in fold_scores],
            "held_out_auc_by_target_category": by_target,
            "held_out_auc_by_control_category": by_control,
        })
    return curves


def _score_auc(positive: np.ndarray, negative: np.ndarray) -> float:
    if not len(positive) or not len(negative):
        return float("nan")
    labels = np.concatenate([np.ones(len(positive)), np.zeros(len(negative))])
    scores = np.concatenate([positive, negative])
    return float(roc_auc_score(labels, scores))


def _category_diagnostics(rows: list[dict[str, Any]], target_scores: np.ndarray,
                          control_scores: np.ndarray) -> dict[str, dict[str, float]]:
    return {
        "target": {
            category: _score_auc(
                target_scores[np.array([str(row["target_category"]) == category for row in rows])],
                control_scores,
            )
            for category in sorted({str(row["target_category"]) for row in rows})
        },
        "control": {
            category: _score_auc(
                target_scores,
                control_scores[np.array([str(row["control_category"]) == category for row in rows])],
            )
            for category in sorted({str(row["control_category"]) for row in rows})
        },
    }


def nested_grouped_validation(rows: list[dict[str, Any]], arrays: dict[str, tuple[np.ndarray, np.ndarray]],
                              outer_folds: int = 5, inner_folds: int = 4) -> dict[str, Any]:
    """Choose pooling/layer only inside each outer training fold, then score its untouched fold."""
    groups = np.array([str(row["semantic_set"]) for row in rows])
    indices = np.arange(len(rows))
    outer = GroupKFold(n_splits=outer_folds)
    target_scores = np.full(len(rows), np.nan, dtype=np.float64)
    control_scores = np.full(len(rows), np.nan, dtype=np.float64)
    selections = []
    fold_aucs = []
    for fold, (train, test) in enumerate(outer.split(indices, groups=groups), 1):
        train_rows = [rows[int(index)] for index in train]
        candidates = []
        for pooling, (target, control) in arrays.items():
            curves = grouped_layer_curve(train_rows, target[train], control[train], folds=inner_folds)
            candidate = max(curves, key=lambda row: row["auc_mean"])
            candidates.append({"pooling": pooling, "layer": int(candidate["layer"]), "inner_auc": float(candidate["auc_mean"])})
        selected = max(candidates, key=lambda row: row["inner_auc"])
        target, control = arrays[selected["pooling"]]
        direction = fit_direction(target[train, selected["layer"], :], control[train, selected["layer"], :])
        target_scores[test] = _project(target[test, selected["layer"], :], direction)
        control_scores[test] = _project(control[test, selected["layer"], :], direction)
        score = _score_auc(target_scores[test], control_scores[test])
        fold_aucs.append(score)
        selections.append({"fold": fold, **selected, "outer_auc": score})
    if not np.isfinite(target_scores).all() or not np.isfinite(control_scores).all():
        raise ValueError("nested validation left an observation unscored")
    return {
        "auc_mean": float(np.mean(fold_aucs)),
        "auc_std": float(np.std(fold_aucs)),
        "fold_aucs": fold_aucs,
        "fold_selections": selections,
        "category_diagnostics": _category_diagnostics(rows, target_scores, control_scores),
        "law": "outer observations never participate in pooling or layer selection for their own score",
    }


def fit(work_dir: Path, output_dir: Path, auc_minimum: float = 0.85) -> dict[str, Any]:
    validate(work_dir / "rows.jsonl", require_curated=False)
    source_manifest = work_dir / "source.manifest.json"
    if not source_manifest.exists() or json.loads(source_manifest.read_text()).get("curated") is not True:
        raise ValueError("prepared work is missing its curated source manifest")
    extraction_lock_path = work_dir / "extraction-model-lock.json"
    if not extraction_lock_path.exists():
        raise ValueError("prepared work lacks the exact model lock used for extraction")
    extraction_lock = json.loads(extraction_lock_path.read_text(encoding="utf-8"))
    if not all(str(extraction_lock.get(key, "")).strip() for key in ("identity", "sha256", "llama_cpp_revision")):
        raise ValueError("extraction model lock is incomplete")
    output_dir.mkdir(parents=True, exist_ok=True)
    pooling_reports = {}
    arrays = {}
    best = None
    for pooling in ("final", "mean"):
        rows, target, control = load_work(work_dir, pooling)
        arrays[pooling] = (target, control)
        curves = grouped_layer_curve(rows, target, control)
        candidate = max(curves, key=lambda row: row["auc_mean"])
        pooling_reports[pooling] = {"best": candidate, "layers": curves}
        if best is None or candidate["auc_mean"] > best["auc_mean"]:
            best = {**candidate, "pooling": pooling, "target": target, "control": control, "rows": rows}
    assert best is not None
    nested = nested_grouped_validation(best["rows"], arrays)
    layer = int(best["layer"])
    direction = fit_direction(best["target"][:, layer, :], best["control"][:, layer, :])
    control_projection = _project(best["control"][:, layer, :], direction)
    status = "validated" if nested["auc_mean"] >= auc_minimum else "rejected_below_auc"
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
        "held_out_auc": nested["auc_mean"],
        "held_out_auc_std": nested["auc_std"],
        "nested_validation": nested,
        "selected_category_diagnostics": {
            **nested["category_diagnostics"],
            "law": "diagnostic only; category removal requires a new preregistered dataset version and fresh held-out validation"
        },
        "denoise_control_variance": 0.5,
        "model_identity": extraction_lock["identity"],
        "model_sha256": extraction_lock["sha256"],
        "extractor_revision": extraction_lock["llama_cpp_revision"],
        "architecture_note": extraction_lock.get("architecture_note"),
        "pooling_reports": pooling_reports,
        "deployment_selection_note": "selected pooling/layer is fitted on all data only after nested validation; its inner-CV score is not the reported held-out score",
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
    stacked = np.stack(vectors) if vectors else np.zeros((0, 0))
    matrix = np.einsum("ik,jk->ij", stacked, stacked, optimize=False) if vectors else np.zeros((0, 0))
    return {"concepts": names, "cosine": matrix.tolist(), "truth_status": "descriptive_not_dimensionality_proof"}
