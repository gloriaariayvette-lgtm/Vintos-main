"""Import the published Pain Axis corpus without relabelling or invented examples."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

TARGETS = ("A1", "A2", "A3", "A4", "A5")
CONTROLS = ("B", "C1", "C2", "D", "E")
DATASETS = ("S1_1P", "S1_3P", "S2_1P", "S2_3P")
SOURCE_REVISION = "8d1649c03a63a39c9aa092532c376800cc4a3863"
SOURCE_REPOSITORY = "https://github.com/valen-research/Pain-axis"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _suffix(prompt: str, form: str) -> str:
    match = re.search(r"\s+(I feel|(?:He|She|They) feels?):\s*$", prompt)
    marker = match.group(1) if match else "I feel"
    base = prompt[:match.start()].rstrip() if match else prompt.rstrip()
    if form == "feel_colon":
        return f"{base} {marker}:"
    if form == "feel":
        return f"{base} {marker}"
    if form == "none":
        return base
    raise ValueError(f"unknown suffix form {form}")


def convert(source: Path, output: Path) -> dict[str, Any]:
    payload = json.loads(source.read_text(encoding="utf-8"))
    labels = payload["metadata"]["category_labels"]
    rows: list[dict[str, Any]] = []
    for dataset_name in DATASETS:
        version, person = dataset_name.split("_")
        by_set: dict[int, dict[str, str]] = {}
        for item in payload["datasets"][dataset_name]["sentences"]:
            by_set.setdefault(int(item["set"]), {})[str(item["category"])] = str(item["prompt"])
        for set_number in sorted(by_set):
            entries = by_set[set_number]
            for slot, (target_code, control_code) in enumerate(zip(TARGETS, CONTROLS), 1):
                if target_code not in entries or control_code not in entries:
                    raise ValueError(f"{dataset_name} set {set_number} lacks {target_code}/{control_code}")
                semantic_set = f"pain-{version.lower()}-{set_number:02d}-slot-{slot}"
                for suffix in ("feel_colon", "feel", "none"):
                    rows.append({
                        "pair_id": f"{semantic_set}-{person.lower()}-{suffix}",
                        "semantic_set": semantic_set,
                        "concept": "Pain",
                        "version": version,
                        "person": person,
                        "suffix": suffix,
                        "target_category": labels[target_code],
                        "control_category": labels[control_code],
                        "target": _suffix(entries[target_code], suffix),
                        "control": _suffix(entries[control_code], suffix),
                        "source_category_codes": {"target": target_code, "control": control_code},
                        "source_dataset": dataset_name,
                        "source_set": set_number,
                    })
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
    manifest = {
        "schema": 1,
        "concept": "Pain",
        "curated": True,
        "curation_basis": "published_source_dataset",
        "derivation": "Deterministic suffix expansion and fixed A1-B, A2-C1, A3-C2, A4-D, A5-E pairing; labels and sentences are unchanged apart from the declared suffix variants.",
        "source": {
            "repository": SOURCE_REPOSITORY,
            "revision": SOURCE_REVISION,
            "path": "datasets/3.1_pain_and_control_datasets.json",
            "source_sha256": _sha256(source),
            "license": "MIT",
            "paper": "https://arxiv.org/abs/2609.16247",
        },
    }
    output.with_suffix(".manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return {"rows": len(rows), "semantic_sets": len({row["semantic_set"] for row in rows}), "output": str(output)}
