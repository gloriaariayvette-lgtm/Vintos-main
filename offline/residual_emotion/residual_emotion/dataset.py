"""Contrastive dataset contract with semantic-set fold isolation."""

from __future__ import annotations

import collections
import json
from pathlib import Path
from typing import Any

from .io import read_jsonl

VERSIONS = {"S1", "S2"}
PERSONS = {"1P", "3P"}
SUFFIXES = {"feel_colon", "feel", "none"}
REQUIRED = {
    "pair_id", "semantic_set", "concept", "version", "person", "suffix",
    "target_category", "control_category", "target", "control",
}


def validate(path: Path, require_curated: bool = True) -> dict[str, Any]:
    rows = read_jsonl(path)
    if not rows:
        raise ValueError("dataset is empty")
    manifest_path = path.with_suffix(".manifest.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    if require_curated and manifest.get("curated") is not True:
        raise ValueError("dataset is not marked curated by a human reviewer")
    concepts = {str(row.get("concept", "")) for row in rows}
    if len(concepts) != 1 or "" in concepts:
        raise ValueError("one dataset file must contain exactly one named concept")
    seen = set()
    category_sets: dict[str, set[str]] = {"target": set(), "control": set()}
    category_counts: dict[str, collections.Counter[str]] = {
        "target": collections.Counter(), "control": collections.Counter()
    }
    semantic_variants: dict[str, set[tuple[str, str, str]]] = collections.defaultdict(set)
    for index, row in enumerate(rows):
        missing = REQUIRED - row.keys()
        if missing:
            raise ValueError(f"row {index}: missing {sorted(missing)}")
        if row["version"] not in VERSIONS or row["person"] not in PERSONS or row["suffix"] not in SUFFIXES:
            raise ValueError(f"row {index}: invalid variant")
        if not str(row["target"]).strip() or not str(row["control"]).strip():
            raise ValueError(f"row {index}: blank sentence")
        pair_id = str(row["pair_id"])
        if pair_id in seen:
            raise ValueError(f"duplicate pair_id {pair_id}")
        seen.add(pair_id)
        target_cat = str(row["target_category"])
        control_cat = str(row["control_category"])
        category_sets["target"].add(target_cat)
        category_sets["control"].add(control_cat)
        category_counts["target"][target_cat] += 1
        category_counts["control"][control_cat] += 1
        semantic_variants[str(row["semantic_set"])].add(
            (str(row["version"]), str(row["person"]), str(row["suffix"]))
        )
    if len(category_sets["target"]) != 5 or len(category_sets["control"]) != 5:
        raise ValueError("each concept requires five target and five matched-control categories")
    if len(semantic_variants) < 20:
        raise ValueError("fewer than twenty independent semantic sets cannot support five folds")
    return {
        "concept": next(iter(concepts)),
        "rows": len(rows),
        "semantic_sets": len(semantic_variants),
        "target_categories": sorted(category_sets["target"]),
        "control_categories": sorted(category_sets["control"]),
        "target_counts": dict(category_counts["target"]),
        "control_counts": dict(category_counts["control"]),
        "curated": manifest.get("curated") is True,
    }


def prepare(path: Path, out_dir: Path) -> dict[str, Any]:
    summary = validate(path)
    rows = read_jsonl(path)
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / "target.txt"
    control = out_dir / "control.txt"
    target.write_text("".join(_escape(str(row["target"])) + "\n" for row in rows), encoding="utf-8")
    control.write_text("".join(_escape(str(row["control"])) + "\n" for row in rows), encoding="utf-8")
    (out_dir / "rows.jsonl").write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    source_manifest = path.with_suffix(".manifest.json")
    if source_manifest.exists():
        (out_dir / "source.manifest.json").write_text(source_manifest.read_text(encoding="utf-8"), encoding="utf-8")
    (out_dir / "dataset-summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return summary


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("\n", "\\n")
