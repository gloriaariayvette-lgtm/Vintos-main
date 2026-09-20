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

from residual_emotion.analysis import auc, fit_direction, grouped_layer_curve, nested_grouped_validation, paper_protocol, paper_variant_fit, paper_variant_matrix
from residual_emotion.authoring import (
    _declared_category_count, _deterministic_selection, _load_full_candidate_pool, _repair_review_ids, _review_prompt, _validate_candidates, _validate_full_selection,
    apply_review_receipt, author_batch_requests, expand_reviewed, expand_reviewed_suite,
    merge_reviewed_repair, render_human_review_sheets,
)
from residual_emotion.compare import join
from residual_emotion.dataset import prepare, prepare_paper_protocol, validate
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
    (prepared / "extraction-model-lock.json").write_text(json.dumps({"identity": "fixture", "sha256": "0" * 64, "llama_cpp_revision": "fixture"}))

    # Gloria's review receipt is applied literally: rejects disappear, named
    # replacements enter, and the balanced suite expands without live writes.
    reviewed_base = scratch / "reviewed.jsonl"
    receipt_result = apply_review_receipt(
        ROOT / "drafts" / "eleven-dimensions-base.jsonl",
        ROOT / "review-receipts" / "2026-09-20-gloria-bulk-review.json",
        reviewed_base,
    )
    reviewed_rows = read_jsonl(reviewed_base)
    reviewed_ids = {item["candidate_id"] for item in reviewed_rows}
    check(receipt_result == {"rows": 2200, "explicit_accepts": 38, "explicit_rejects": 2,
                             "bulk_accept_remaining": 2160, "replacements": 2},
          "review receipt counts are exact")
    check("cand-2eaaf768fa61b949" not in reviewed_ids and "cand-62d291936051a05d" not in reviewed_ids,
          "explicitly rejected candidates do not survive")
    check({"cand-396a9a66259c18c6", "cand-25543f84de5dff89"}.issubset(reviewed_ids),
          "named reviewer-approved replacements enter")
    duplicate_receipt = json.loads((ROOT / "review-receipts" / "2026-09-20-gloria-bulk-review.json").read_text())
    duplicate_receipt["replacements"].append(dict(duplicate_receipt["replacements"][0]))
    duplicate_path = scratch / "duplicate-replacement.json"
    duplicate_path.write_text(json.dumps(duplicate_receipt))
    try:
        apply_review_receipt(ROOT / "drafts" / "eleven-dimensions-base.jsonl",
                             duplicate_path, scratch / "must-not-exist.jsonl")
        raise AssertionError("duplicate replacement was accepted")
    except ValueError:
        pass
    expanded_suite = expand_reviewed_suite(reviewed_base, scratch / "reviewed-suite", "Gloria")
    check(expanded_suite["concepts"] == 11 and expanded_suite["expanded_rows"] == 13200,
          "reviewed suite expands into eleven balanced datasets")

    # A bounded reviewer shard requires its own exact chunks, not all 165
    # chunks from the original eleven-concept authoring campaign.
    shard_plan = scratch / "shard-plan.json"
    shard_plan.write_text(json.dumps({"concepts": {"Safety": {
        "targets": ["one", "two", "verified shield"],
        "controls": ["a", "b", "matched ease without shield"],
    }}}))
    author_dirs = []
    for author_index, model in enumerate(("anthropic/claude-sonnet-5", "x-ai/grok-4.6"), 1):
        author_dir = scratch / f"author-{author_index}"; author_dir.mkdir(); author_dirs.append(author_dir)
        for chunk in (1, 2, 3):
            candidates = []
            for version in ("S1", "S2"):
                for number in range(1, 11):
                    candidates.append({
                        "version": version, "candidate_number": number,
                        "target_1p": f"I rest behind a verified barrier {chunk}-{number}.",
                        "control_1p": f"I rest while the barrier is absent {chunk}-{number}.",
                        "target_3p": f"She rests behind a verified barrier {chunk}-{number}.",
                        "control_3p": f"She rests while the barrier is absent {chunk}-{number}.",
                    })
            (author_dir / f"author__{author_index}__{chunk}.json").write_text(json.dumps({
                "truth_status": "machine_authored_candidate_chunk_not_reviewed",
                "concept": "Safety", "slot": 3, "chunk": chunk, "value": {"candidates": candidates},
            }))
    shard = _load_full_candidate_pool(shard_plan, author_dirs, only_keys={("Safety", 3)})
    check(set(shard) == {("Safety", 3)} and len(shard[("Safety", 3)]) == 120,
          "review loader accepts a complete bounded category shard")
    counted_stage = scratch / "counted-stage"; counted_stage.mkdir()
    (counted_stage / "manifest.json").write_text(json.dumps({
        "schema": 1, "truth_status": "blind_machine_review_stage_partial_not_human_curated",
        "category_count": 2,
    }))
    check(_declared_category_count(counted_stage) == 2,
          "bounded stage count comes from its manifest rather than a full-campaign constant")

    # Human sheets are deterministic views, not curation receipts.
    sheet_draft = scratch / "sheet-draft.jsonl"
    sheet_rows = []
    for version in ("S1", "S2"):
        sheet_rows.append({
            "draft_id": f"safety-03-{version.lower()}-0001", "concept": "Safety", "slot": 3,
            "version": version, "target_category": "functioning protection",
            "control_category": "failed protection", "target_1p": "I feel the harness catch.",
            "control_1p": "I feel the harness slip.", "target_3p": "She feels the harness catch.",
            "control_3p": "She feels the harness slip.", "review_verdict": "pass",
            "review_scores": {"construct_specificity": 4, "confound_match": 4, "surface_match": 4,
                              "person_fidelity": 4, "naturalness": 4},
            "review_state": "unreviewed_machine_draft",
        })
    sheet_draft.write_text("".join(json.dumps(item) + "\n" for item in sheet_rows))
    sheets = render_human_review_sheets(sheet_draft, scratch / "sheets")
    sheet_text = (scratch / "sheets" / "safety-03.md").read_text()
    check(sheets["truth_status"] == "rendered_for_human_review_not_curated"
          and "Nothing here is accepted" in sheet_text and "[ ] accept" in sheet_text,
          "human-review rendering preserves the explicit curation gate")

    # A bounded repair campaign uses the same literal review law without being
    # mistaken for the original 55-category suite.
    bounded_base = scratch / "bounded-base.jsonl"
    bounded_rows = []
    for version in ("S1", "S2"):
        for number in range(20):
            bounded_rows.append({
                **sheet_rows[0], "draft_id": f"safety-03-{version.lower()}-{number:04d}",
                "candidate_id": f"candidate-{version}-{number}", "version": version,
            })
    bounded_base.write_text("".join(json.dumps(item) + "\n" for item in bounded_rows))
    rejected = bounded_rows[-1]
    replacement = {**rejected, "replaces": rejected["draft_id"],
                   "draft_id": "safety-03-s2-replacement", "candidate_id": "candidate-S2-alternate"}
    bounded_receipt = scratch / "bounded-receipt.json"
    bounded_receipt.write_text(json.dumps({
        "reviewer": "Gloria", "bulk_accept_remaining": True,
        "explicit_decisions": [{"code": rejected["draft_id"], "decision": "reject"}],
        "replacements": [replacement],
    }))
    bounded_output = scratch / "bounded-reviewed.jsonl"
    bounded_result = apply_review_receipt(bounded_base, bounded_receipt, bounded_output)
    check(bounded_result["rows"] == 40 and bounded_result["replacements"] == 1,
          "bounded human review preserves 20-per-version balance with a named alternate")
    original_complete = scratch / "original-complete.jsonl"
    original_rows = []
    for slot in (1, 2):
        for version in ("S1", "S2"):
            for number in range(20):
                original_rows.append({**bounded_rows[0], "slot": slot, "version": version,
                                      "draft_id": f"original-{slot}-{version}-{number}",
                                      "candidate_id": f"original-candidate-{slot}-{version}-{number}",
                                      "review_state": "accepted"})
    original_complete.write_text("".join(json.dumps(item) + "\n" for item in original_rows))
    repair_complete = scratch / "repair-complete.jsonl"
    repair_rows = [{**item, "slot": 2, "draft_id": f"repair-{item['version']}-{index}",
                    "candidate_id": f"repair-candidate-{item['version']}-{index}",
                    "review_state": "accepted"}
                   for index, item in enumerate(bounded_rows)]
    repair_complete.write_text("".join(json.dumps(item) + "\n" for item in repair_rows))
    merged_path = scratch / "merged-reviewed.jsonl"
    merged_result = merge_reviewed_repair(original_complete, repair_complete, merged_path)
    merged_rows = read_jsonl(merged_path)
    check(merged_result["repaired_slots"] == [2] and len(merged_rows) == 80
          and not any(str(item["draft_id"]).startswith("original-2-") for item in merged_rows),
          "complete reviewed slots replace originals without mixing category versions")

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
    paper_work = scratch / "paper-work"
    paper_summary = prepare_paper_protocol(pain, paper_work)
    (paper_work / "extraction-model-lock.json").write_text(json.dumps({
        "identity": "fixture", "sha256": "0" * 64, "llama_cpp_revision": "fixture",
    }))
    paper_rows = read_jsonl(paper_work / "rows.jsonl")
    check(paper_summary["rows"] == 200 and len(paper_rows) == 200, "paper subset has only required pairs")
    check({row["version"] for row in paper_rows} == {"S2"}, "paper subset is S2")
    check({row["suffix"] for row in paper_rows} == {"feel_colon"}, "paper subset is colon prompts")

    # The exact paper scorer keeps persons separate and averages their layer curves.
    paper_control = np.zeros((200, 2, 8), dtype=np.float64)
    paper_target = paper_control.copy(); paper_target[:, 1, 0] += 2.0
    replicated = paper_protocol(paper_rows, paper_target, paper_control)
    check(replicated["status"] == "replicated" and replicated["selected_layer"] == 1,
          "paper scorer reproduces a held signal")

    # Ablations remain separate estimates and require every published prompt variant.
    full_target = np.zeros((1200, 2, 8), dtype=np.float64); full_target[:, 1, 0] += 2.0
    full_control = np.zeros_like(full_target)
    variants = paper_variant_matrix(imported_rows, full_target, full_control)
    check(variants["variant_count"] == 6 and variants["passing_variants"] == 6,
          "all six prompt variants are scored independently")
    check({(v["variant"]["version"], v["variant"]["suffix"]) for v in variants["variants"]}
          == {(version, suffix) for version in ("S1", "S2") for suffix in ("feel_colon", "feel", "none")},
          "variant matrix is complete")
    reviewed_shape_rows = [{key: value for key, value in item.items() if key != "source_set"}
                           for item in imported_rows]
    reviewed_shape_variants = paper_variant_matrix(reviewed_shape_rows, full_target, full_control)
    check(reviewed_shape_variants["passing_variants"] == 6,
          "reviewed datasets group variants by semantic_set without Pain-only source_set")

    # Paper mode remains final-token by default, while content experiments may
    # explicitly score the mean pooling selected by their primary validation.
    for index in range(1200):
        for pooling, values in (("final", full_control), ("mean", full_target)):
            for side, source_values in (("target", values), ("control", full_control)):
                path = paper_work / "dumps" / f"{index:06d}_{side}_{pooling}.f32"
                path.parent.mkdir(parents=True, exist_ok=True)
                with path.open("wb") as handle:
                    handle.write(struct.pack("<IIII", MAGIC, 1, 2, 8)); source_values[index].astype("<f4").tofile(handle)
    (paper_work / "rows.jsonl").write_text("".join(json.dumps(value) + "\n" for value in imported_rows))
    final_report = paper_variant_fit(paper_work, scratch / "final-variants.json")
    mean_report = paper_variant_fit(paper_work, scratch / "mean-variants.json", pooling="mean")
    check(final_report["pooling"] == "final" and mean_report["pooling"] == "mean",
          "prompt ablation pooling is explicit and paper default stays final-token")

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

    # Machine-authored base pairs cannot expand until every one has a named human decision.
    draft = scratch / "draft.jsonl"; expanded = scratch / "expanded.jsonl"
    base = [{
        "draft_id": f"warmth-s2-1-{index:02d}", "candidate_id": f"candidate-{index}",
        "concept": "Warmth", "version": "S2", "target_category": "affection",
        "control_category": "familiarity", "target_1p": "I held the moment gently.",
        "control_1p": "I recognized the moment clearly.", "target_3p": "She held the moment gently.",
        "control_3p": "She recognized the moment clearly.",
        "review_state": "accepted" if index else "unreviewed_machine_draft",
    } for index in range(2)]
    draft.write_text("".join(json.dumps(value) + "\n" for value in base))
    try:
        expand_reviewed(draft, expanded, "fixture-reviewer")
        raise AssertionError("unreviewed machine prose was admitted")
    except ValueError:
        pass
    base[0]["review_state"] = "accepted"
    draft.write_text("".join(json.dumps(value) + "\n" for value in base))
    expanded_summary = expand_reviewed(draft, expanded, "fixture-reviewer")
    check(expanded_summary["rows"] == 12 and len(read_jsonl(expanded)) == 12, "accepted pairs expand to six variants")
    check(json.loads(expanded.with_suffix(".manifest.json").read_text())["reviewers"] == ["fixture-reviewer"],
          "human reviewer remains explicit")

    # Full authoring keeps a three-times candidate pool without paying for hidden high-effort reasoning.
    plan_path = ROOT / "dataset-plan.json"
    sonnet_requests = author_batch_requests(plan_path, "anthropic/claude-sonnet-5")
    grok_requests = author_batch_requests(plan_path, "x-ai/grok-4.6")
    check(len(sonnet_requests) == 165 and len({item["custom_id"] for item in sonnet_requests}) == 165,
          "author requests cover every concept/category/chunk once")
    supplement = author_batch_requests(plan_path, "anthropic/claude-sonnet-5", chunks=(4, 5),
                                       only_keys={("Safety", 2), ("Connection", 1)})
    check(len(supplement) == 4 and all(item["custom_id"].endswith(("|4", "|5")) for item in supplement),
          "targeted supplements add disjoint checkpoint chunks only for requested category slots")
    check(sonnet_requests[0]["body"]["reasoning"] == {"enabled": False}, "Sonnet drafting disables hidden reasoning")
    check(grok_requests[0]["body"]["reasoning"] == {"effort": "low"}, "Grok drafting uses lowest supported effort")
    candidate_fields = set(sonnet_requests[0]["body"]["response_format"]["json_schema"]["schema"]
                           ["properties"]["candidates"]["items"]["properties"])
    check("design_note" not in candidate_fields and "target_3p" in candidate_fields,
          "author schema removes redundant prose without dropping person variants")

    # Blind review gets the sentences and opaque id, never model or source bookkeeping.
    visible_candidate = {"candidate_id": "opaque", "version": "S1", "candidate_number": 1,
                         "target_1p": "I settled into the familiar chair.",
                         "control_1p": "I recognized the familiar chair.",
                         "target_3p": "She settled into the familiar chair.",
                         "control_3p": "She recognized the familiar chair.",
                         "author_model": "SECRET-MODEL", "author_index": 2, "author_chunk": 3}
    blind_prompt = _review_prompt("Warmth", "affiliative tenderness", "affection", "familiarity", [visible_candidate])
    check("SECRET-MODEL" not in blind_prompt and "author_index" not in blind_prompt and "author_chunk" not in blind_prompt,
          "review prompt is author blind")

    leaking = {"candidates": [{"version": version, "candidate_number": number,
                                "target_1p": "I felt warmth settle in.", "control_1p": "I knew the room.",
                                "target_3p": "She felt warmth settle in.", "control_3p": "She knew the room."}
                               for version in ("S1", "S2") for number in range(1, 3)]}
    try:
        _validate_candidates(leaking, "Warmth", "fixture", per_version=2, compact=True)
        raise AssertionError("concept label leakage was admitted")
    except ValueError:
        pass

    # Fable's id-only selection must preserve both versions and both blind source buckets.
    eligible = []
    for version in ("S1", "S2"):
        for index in range(20):
            eligible.append({"candidate_id": f"{version}-{index}", "version": version,
                             "source_bucket": "north" if index < 10 else "south"})
    selection = {"selected": [{"candidate_id": row["candidate_id"], "version": row["version"],
                                "source_bucket": row["source_bucket"]} for row in eligible]}
    check(len(_validate_full_selection(selection, eligible)) == 40, "balanced opaque-id selection passes")
    scarce = []
    for version in ("S1", "S2"):
        scarce.extend({"candidate_id": f"{version}-north-{index}", "version": version, "source_bucket": "north"}
                      for index in range(3))
        scarce.extend({"candidate_id": f"{version}-south-{index}", "version": version, "source_bucket": "south"}
                      for index in range(25))
    scarce_selection = {"selected": [{"candidate_id": row["candidate_id"], "version": row["version"],
                                       "source_bucket": row["source_bucket"]}
                                      for version in ("S1", "S2")
                                      for row in ([item for item in scarce if item["version"] == version and item["source_bucket"] == "north"]
                                                  + [item for item in scarce if item["version"] == version and item["source_bucket"] == "south"][:17])]}
    check(len(_validate_full_selection(scarce_selection, scarce)) == 40,
          "adaptive quotas retain every reviewer-approved scarce-source candidate without resurrecting rejects")

    deterministic_pool = []
    for row in scarce:
        deterministic_pool.append({**row, "target_1p": f"I examined artifact {row['candidate_id']} carefully.",
                                   "control_1p": f"I catalogued artifact {row['candidate_id']} carefully.",
                                   "review_verdict": "pass", "review_scores": {
                                       "construct_specificity": 4, "confound_match": 4, "surface_match": 4,
                                       "person_fidelity": 4, "naturalness": 4}})
    chosen_once, alternates_once = _deterministic_selection(deterministic_pool)
    chosen_twice, alternates_twice = _deterministic_selection(deterministic_pool)
    check(chosen_once == chosen_twice and alternates_once == alternates_twice,
          "transparent selector is stable across repeated runs")
    check(len(chosen_once) == 40 and len(alternates_once) == len(deterministic_pool) - 40,
          "transparent selector preserves exact selection count and all eligible alternates")

    typo_value = {"reviews": [{"candidate_id": "cand-abcc"}]}
    typo_candidates = [{"candidate_id": "cand-abc"}]
    repairs = _repair_review_ids(typo_value, typo_candidates)
    check(typo_value["reviews"][0]["candidate_id"] == "cand-abc" and repairs[0]["law"] == "unique_one_edit_opaque_id",
          "unique one-edit opaque ID typo is traceably repaired")
    ambiguous_value = {"reviews": [{"candidate_id": "cand-abd"}]}
    check(not _repair_review_ids(ambiguous_value, [{"candidate_id": "cand-abc"}, {"candidate_id": "cand-abe"}]),
          "ambiguous ID typo is never guessed")

print("PASS residual-emotion offline isolation and analysis")
