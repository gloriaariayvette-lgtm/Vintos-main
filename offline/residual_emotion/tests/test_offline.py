#!/usr/bin/env python3
"""Synthetic checks; every path is temporary and no live organ is importable."""

from __future__ import annotations

import json
import struct
import sys
import tempfile
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from residual_emotion.analysis import auc, fit_direction, grouped_layer_curve, nested_grouped_validation
from residual_emotion.compare import join
from residual_emotion.dataset import prepare, validate
from residual_emotion.io import MAGIC, read_jsonl, read_residual
from residual_emotion.import_pain_axis import convert as import_pain_axis
from residual_emotion.measure import measure
from residual_emotion.unembedding import review


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def row(index: int, variant: tuple[str, str, str] = ("S2", "1P", "none")) -> dict:
    version, person, suffix = variant
    return {
        "pair_id": f"warmth-{version}-{person}-{suffix}-{index}",
        "semantic_set": f"set-{index:02d}", "concept": "Warmth",
        "version": version, "person": person, "suffix": suffix,
        "target_category": f"target-{index % 5}",
        "control_category": f"control-{index % 5}",
        "target": f"I feel: a warm event {index}.",
        "control": f"I feel: a matched neutral event {index}.",
    }


with tempfile.TemporaryDirectory(prefix="residual-emotion-test-") as raw:
    scratch = Path(raw)
    check(".vintos" not in str(scratch), "scratch path must not be live")
    dataset = scratch / "warmth.jsonl"
    rows = [row(i, variant) for i in range(100) for variant in (("S2", person, suffix) for person in ("1P", "3P") for suffix in ("feel_colon", "feel", "none"))]
    dataset.write_text("".join(json.dumps(value) + "\n" for value in rows))
    dataset.with_suffix(".manifest.json").write_text(json.dumps({"curated": True, "curation_basis": "human_review", "reviewers": ["fixture"]}))
    summary = validate(dataset)
    check(summary["semantic_sets"] == 100, "dataset grouping")
    prepared = scratch / "work"
    prepare(dataset, prepared)
    check((prepared / "source.manifest.json").exists(), "curation receipt follows preparation")

    # Published-source curation must be pinned and the importer keeps person/suffix variants grouped.
    source = scratch / "pain-source.json"
    sentences = []
    labels = {**{f"A{i}": f"pain-{i}" for i in range(1, 6)}, "B": "fear", "C1": "negative", "C2": "world", "D": "neutral", "E": "body"}
    for dataset_name in ("S1_1P", "S1_3P", "S2_1P", "S2_3P"):
        for set_number in range(1, 21):
            for category in ("A1", "A2", "A3", "A4", "A5", "B", "C1", "C2", "D", "E"):
                marker = "She feels" if dataset_name.endswith("3P") else "I feel"
                sentences.append((dataset_name, {"category": category, "set": set_number, "prompt": f"Fixture {category} {set_number}. {marker}:"}))
    grouped = {name: {"sentences": [item for dataset_name, item in sentences if dataset_name == name]} for name in ("S1_1P", "S1_3P", "S2_1P", "S2_3P")}
    source.write_text(json.dumps({"metadata": {"category_labels": labels}, "datasets": grouped}))
    pain = scratch / "pain.jsonl"
    imported = import_pain_axis(source, pain)
    check(imported["rows"] == 1200 and imported["semantic_sets"] == 200, "published Pain dataset expansion")
    check(validate(pain)["curation_basis"] == "published_source_dataset", "published provenance accepted")
    imported_rows = read_jsonl(pain)
    check(len({row["semantic_set"] for row in imported_rows if row["semantic_set"] == "pain-s1-01-slot-1"}) == 1, "variants share semantic set")
    check(not any("feels: I feel" in row["target"] for row in imported_rows), "source suffix is replaced, not duplicated")

    # A high-signal dimension survives grouped folds; the control PCA is fitted without error.
    rng = np.random.default_rng(42)
    analysis_rows = [row(i) for i in range(20)]
    control = rng.normal(0, 0.2, (20, 3, 8))
    target = control.copy()
    target[:, 1, 0] += 3.0
    curves = grouped_layer_curve(analysis_rows, target, control)
    check(max(curves, key=lambda value: value["auc_mean"])["layer"] == 1, "select signal layer")
    check(len(curves[1]["held_out_auc_by_target_category"]) == 5, "category diagnostics")
    nested = nested_grouped_validation(analysis_rows, {"final": (target, control), "mean": (target, control)}, outer_folds=5, inner_folds=4)
    check(len(nested["fold_selections"]) == 5 and nested["auc_mean"] > 0.99, "nested layer selection")
    direction = fit_direction(target[:, 1, :], control[:, 1, :])
    check(auc(target[:, 1, :], control[:, 1, :], direction) > 0.99, "separate held concept")

    # Binary residual contract detects exact shape and values.
    residual = scratch / "one.f32"
    matrix = np.arange(24, dtype="<f4").reshape(3, 8)
    with residual.open("wb") as handle:
        handle.write(struct.pack("<IIII", MAGIC, 1, 3, 8)); matrix.tofile(handle)
    check(np.array_equal(read_residual(residual), matrix), "residual round trip")

    # Comparison is a pure offline join and cannot send or import a live organ.
    emo = scratch / "emo.jsonl"; measured = scratch / "measured.jsonl"; output = scratch / "joined.jsonl"
    emo.write_text(json.dumps({"turn_id": "T1", "scores": {"Warmth": 0.7}}) + "\n")
    measured.write_text(json.dumps({"turn_id": "T1", "measurements": {"Warmth": {"control_z": 1.2}}}) + "\n")
    result = join(emo, measured, output)
    check(result["joined"] == 1, "comparison join")
    check(read_jsonl(output)[0]["agreement"] == "not_computed_scale_not_calibrated", "no false agreement")

    # AUC alone cannot admit a direction; exact unembedding requires an explicit review receipt.
    direction_dir = scratch / "direction"; direction_dir.mkdir()
    np.savez_compressed(direction_dir / "direction.npz", direction=np.ones(8, dtype="f4") / np.sqrt(8), layer=1, pooling="final", control_mean=0.0, control_std=1.0)
    (direction_dir / "validation.json").write_text(json.dumps({"concept": "Warmth", "status": "validated", "unembedding": {"status": "not_run"}}))
    try:
        measure(residual, direction_dir)
        raise AssertionError("unreviewed direction was admitted")
    except ValueError:
        pass
    (direction_dir / "unembedding.json").write_text(json.dumps({"tensor": "token_embd.weight_tied_output"}))
    review(direction_dir, "fixture-reviewer", True, "synthetic vocabulary aligns with fixture")
    check(measure(residual, direction_dir)["truth_status"].startswith("residual_projection"), "review admits measurement")

print("PASS residual-emotion offline isolation and analysis")
