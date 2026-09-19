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
CURATION_BASES = {"human_review", "published_source_dataset"}
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
    if require_curated:
        if manifest.get("curated") is not True:
            raise ValueError("dataset is not marked curated")
        basis = str(manifest.get("curation_basis", ""))
        if basis not in CURATION_BASES:
            raise ValueError("curated dataset lacks a recognized curation_basis")
        if basis == "human_review" and not manifest.get("reviewers"):
            raise ValueError("human-curated dataset has no named reviewer")
        if basis == "published_source_dataset":
            source = manifest.get("source") or {}
            if not all(str(source.get(key, "")).strip() for key in ("repository", "revision", "license", "source_sha256")):
                raise ValueError("published dataset lacks pinned source provenance")
    concepts = {str(row.get("concept", "")) for row in rows}
    if len(concepts) != 1 or "" in concepts:
        raise ValueError("one dataset file must contain exactly one named concept")
    seen = set()
    category_sets: dict[str, set[str]] = {"target": set(), "control": set()}
    category_counts: dict[str, collections.Counter[str]] = {
        "target": collections.Counter(), "control": collections.Counter()
    }
    category_semantic_sets: dict[str, dict[str, set[str]]] = {
        "target": collections.defaultdict(set), "control": collections.defaultdict(set)
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
        semantic_set = str(row["semantic_set"])
        category_semantic_sets["target"][target_cat].add(semantic_set)
        category_semantic_sets["control"][control_cat].add(semantic_set)
        semantic_variants[semantic_set].add(
            (str(row["version"]), str(row["person"]), str(row["suffix"]))
        )
    if len(category_sets["target"]) < 5 or len(category_sets["control"]) < 5:
        raise ValueError("each concept requires at least five target and five matched-control categories")
    if len(semantic_variants) < 20:
        raise ValueError("fewer than twenty independent semantic sets cannot support five folds")
    too_small = {
        f"{side}:{category}": len(sets)
        for side, categories in category_semantic_sets.items()
        for category, sets in categories.items()
        if len(sets) < 20
    }
    if too_small:
        raise ValueError(f"categories require twenty independent semantic sets: {too_small}")
    incomplete = {}
    for semantic_set, variants in semantic_variants.items():
        versions = {version for version, _, _ in variants}
        if len(versions) != 1:
            incomplete[semantic_set] = "semantic set spans multiple S1/S2 sentence families"
            continue
        version = next(iter(versions))
        expected = {(version, person, suffix) for person in PERSONS for suffix in SUFFIXES}
        if variants != expected:
            incomplete[semantic_set] = f"has {len(variants)} of 6 person/suffix variants"
    if incomplete:
        sample = dict(list(incomplete.items())[:5])
        raise ValueError(f"incomplete semantic variants: {sample}")
    return {
        "concept": next(iter(concepts)),
        "rows": len(rows),
        "semantic_sets": len(semantic_variants),
        "target_categories": sorted(category_sets["target"]),
        "control_categories": sorted(category_sets["control"]),
        "target_counts": dict(category_counts["target"]),
        "control_counts": dict(category_counts["control"]),
        "target_independent_sets": {key: len(value) for key, value in category_semantic_sets["target"].items()},
        "control_independent_sets": {key: len(value) for key, value in category_semantic_sets["control"].items()},
        "curated": manifest.get("curated") is True,
        "curation_basis": manifest.get("curation_basis"),
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
