"""Align and compare frozen residual measurements with frozen EmoClaw history.

The module never imports or invokes a live organ.  Dense EmoClaw history is a
cumulative state sampled on a cadence, not a per-turn score receipt.  Alignment
therefore keeps that distinction explicit and admits a primary row only when one
and only one conversation turn falls between the surrounding state snapshots.
"""

from __future__ import annotations

from bisect import bisect_left
from datetime import datetime
from pathlib import Path
import re
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np

from .io import append_jsonl, read_jsonl
from .measure import measure


DIMENSIONS = (
    "Valence", "Arousal", "Dominance", "Safety", "Desire", "Connection",
    "Playfulness", "Curiosity", "Warmth", "Tension", "Groundedness",
)


def _timestamp(value: Any, naive_timezone: str) -> float:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=ZoneInfo(naive_timezone))
    return parsed.timestamp()


def align_history(
    ledger_path: Path,
    trajectory_path: Path,
    output_path: Path,
    *,
    max_follow_seconds: float = 900.0,
    naive_timezone: str = "America/Chicago",
    limit: int | None = None,
) -> dict[str, int]:
    """Freeze unambiguous turn-to-cumulative-state alignments for extraction.

    `input_text` contains the whole delivered exchange because avatar chat moves
    EmoClaw once for her input and once for his reply, while voice reads the same
    combined exchange.  The associated vector is still labelled cumulative.
    """
    ledger_raw = json_load(ledger_path)
    ledger = ledger_raw.get("entries", []) if isinstance(ledger_raw, dict) else ledger_raw
    trajectory = json_load(trajectory_path)
    if not isinstance(ledger, list) or not isinstance(trajectory, list):
        raise ValueError("ledger and trajectory must be arrays (or ledger.entries)")
    dense = sorted(
        [(_timestamp(row["t"], naive_timezone), row) for row in trajectory if isinstance(row, dict) and "t" in row],
        key=lambda item: item[0],
    )
    if not dense:
        raise ValueError("dense trajectory is empty")
    dense_times = [item[0] for item in dense]
    turns: list[tuple[float, dict[str, Any]]] = []
    for row in ledger:
        if not isinstance(row, dict) or not str(row.get("gloria", "")).strip() or not str(row.get("vintos", "")).strip():
            continue
        try:
            turns.append((_timestamp(row["timestamp"], naive_timezone), row))
        except (KeyError, TypeError, ValueError):
            continue
    turns.sort(key=lambda item: item[0])
    candidates: list[dict[str, Any]] = []
    for turn_index, (turn_time, row) in enumerate(turns):
        after_index = bisect_left(dense_times, turn_time)
        if after_index >= len(dense):
            continue
        delay = dense_times[after_index] - turn_time
        if delay < 0 or delay > max_follow_seconds:
            continue
        before_index = after_index - 1
        before_time = dense_times[before_index] if before_index >= 0 else float("-inf")
        turns_in_interval = sum(1 for other_time, _ in turns if before_time < other_time <= dense_times[after_index])
        candidates.append({
            "turn_index": turn_index,
            "snapshot_index": after_index,
            "turns_in_snapshot_interval": turns_in_interval,
            "delay_seconds": delay,
            "row": row,
        })
    multiplicity: dict[int, int] = {}
    for candidate in candidates:
        index = int(candidate["snapshot_index"])
        multiplicity[index] = multiplicity.get(index, 0) + 1
    admitted = [
        item for item in candidates
        if item["turns_in_snapshot_interval"] == 1 and multiplicity[int(item["snapshot_index"])] == 1
    ]
    if limit is not None:
        admitted = admitted[-max(0, int(limit)):]
    rows: list[dict[str, Any]] = []
    for item in admitted:
        source = item["row"]
        after_index = int(item["snapshot_index"])
        after_time, after = dense[after_index]
        vector = after.get("v")
        if not isinstance(vector, list) or len(vector) != len(DIMENSIONS):
            continue
        scores = {name: float(vector[index]) for index, name in enumerate(DIMENSIONS)}
        deltas: dict[str, float] = {}
        before_at = None
        if after_index > 0:
            before_time, before = dense[after_index - 1]
            before_vector = before.get("v")
            if isinstance(before_vector, list) and len(before_vector) == len(DIMENSIONS):
                deltas = {name: float(vector[index]) - float(before_vector[index]) for index, name in enumerate(DIMENSIONS)}
                before_at = datetime.fromtimestamp(before_time, ZoneInfo(naive_timezone)).isoformat()
        rows.append({
            "turn_id": str(source.get("turn_id") or f"ledger-{item['turn_index']}"),
            "timestamp": str(source.get("timestamp") or ""),
            "surface": source.get("surface"),
            "input_text": "She said:\n" + str(source.get("gloria", "")).strip() + "\n\nHe replied:\n" + str(source.get("vintos", "")).strip(),
            "scores": scores,
            "state_delta": deltas,
            "alignment": {
                "state_before_at": before_at,
                "state_after_at": datetime.fromtimestamp(after_time, ZoneInfo(naive_timezone)).isoformat(),
                "follow_delay_seconds": round(float(item["delay_seconds"]), 3),
                "turns_in_snapshot_interval": 1,
                "snapshot_shared_by_turns": 1,
            },
            "truth_status": "historical_cumulative_state_aligned_not_per_turn_score",
        })
    output_path.unlink(missing_ok=True)
    append_jsonl(output_path, rows)
    return {"ledger_turns": len(turns), "candidate_alignments": len(candidates), "unambiguous": len(rows)}


def json_load(path: Path) -> Any:
    import json
    return json.loads(path.read_text(encoding="utf-8"))


def prepare_extraction(rows_path: Path, work_dir: Path) -> dict[str, int]:
    """Prepare one-line paired input files for the pinned residual extractor.

    The negative side intentionally repeats the positive side.  We are asking the
    extractor for per-prompt residuals, not fitting a new direction, and this keeps
    its required paired-file contract without inventing a comparison sentence.
    """
    rows = read_jsonl(rows_path)
    work_dir.mkdir(parents=True, exist_ok=True)
    prompts = [str(row.get("input_text", "")).replace("\\", "\\\\").replace("\n", "\\n") for row in rows]
    if not prompts or any(not prompt.strip() for prompt in prompts):
        raise ValueError("comparison rows require non-empty input_text")
    rendered = "".join(prompt + "\n" for prompt in prompts)
    (work_dir / "target.txt").write_text(rendered, encoding="utf-8")
    (work_dir / "control.txt").write_text(rendered, encoding="utf-8")
    (work_dir / "rows.jsonl").write_text(rows_path.read_text(encoding="utf-8"), encoding="utf-8")
    return {"turns": len(rows), "paired_extractor_inputs": len(rows) * 2}


def measure_cohort(rows_path: Path, dumps_dir: Path, direction_dirs: dict[str, Path], output_path: Path) -> dict[str, int]:
    """Measure frozen turn dumps against named, human-admitted directions."""
    rows = read_jsonl(rows_path)
    measured: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        dump = dumps_dir / f"{index:06d}_target_mean.f32"
        if not dump.exists():
            raise ValueError(f"missing residual dump: {dump}")
        values: dict[str, Any] = {}
        for name, direction_dir in direction_dirs.items():
            result = measure(dump, direction_dir)
            if result["concept"] != name:
                raise ValueError(f"direction path for {name} contains {result['concept']}")
            values[name] = result
        measured.append({
            "turn_id": row["turn_id"], "timestamp": row.get("timestamp"),
            "measurements": values,
            "truth_status": "offline_residual_measurements_not_self_report_not_feeling_claim",
        })
    output_path.unlink(missing_ok=True)
    append_jsonl(output_path, measured)
    return {"turns": len(measured), "directions": len(direction_dirs)}


def _rank(values: np.ndarray) -> np.ndarray:
    order = np.argsort(values, kind="mergesort")
    ranked = np.empty(values.size, dtype=np.float64)
    start = 0
    while start < values.size:
        stop = start + 1
        while stop < values.size and values[order[stop]] == values[order[start]]:
            stop += 1
        ranked[order[start:stop]] = (start + stop - 1) / 2.0
        start = stop
    return ranked


def _correlation(left: np.ndarray, right: np.ndarray, *, rank: bool = False) -> float | None:
    if left.size < 3 or right.size != left.size:
        return None
    if rank:
        left, right = _rank(left), _rank(right)
    if float(np.std(left)) <= 1e-12 or float(np.std(right)) <= 1e-12:
        return None
    return float(np.corrcoef(left, right)[0, 1])


def summarize(joined_path: Path, output_path: Path) -> dict[str, Any]:
    """Report scale-free association; never rename association as agreement."""
    rows = read_jsonl(joined_path)
    dimensions: dict[str, Any] = {}
    residual_series: dict[str, np.ndarray] = {}
    state_series: dict[str, np.ndarray] = {}
    for name in DIMENSIONS:
        usable = [row for row in rows if name in row.get("emoclaw_scores", {}) and name in row.get("residual_measurements", {})]
        residual = np.asarray([row["residual_measurements"][name]["control_z"] for row in usable], dtype=np.float64)
        state = np.asarray([row["emoclaw_scores"][name] for row in usable], dtype=np.float64)
        delta = np.asarray([row.get("emoclaw_state_delta", {}).get(name, np.nan) for row in usable], dtype=np.float64)
        finite_delta = np.isfinite(delta)
        residual_series[name] = residual
        state_series[name] = state
        dimensions[name] = {
            "n": int(residual.size),
            "residual_control_z": {"mean": float(np.mean(residual)), "std": float(np.std(residual))} if residual.size else None,
            "emoclaw_state": {"mean": float(np.mean(state)), "std": float(np.std(state))} if state.size else None,
            "spearman_residual_vs_cumulative_state": _correlation(residual, state, rank=True),
            "pearson_residual_vs_cumulative_state": _correlation(residual, state),
            "spearman_residual_vs_snapshot_delta": _correlation(residual[finite_delta], delta[finite_delta], rank=True),
            "pearson_residual_vs_snapshot_delta": _correlation(residual[finite_delta], delta[finite_delta]),
        }
    cross_state: dict[str, dict[str, float | None]] = {}
    for residual_name in DIMENSIONS:
        values = {state_name: _correlation(residual_series[residual_name], state_series[state_name], rank=True)
                  for state_name in DIMENSIONS}
        cross_state[residual_name] = values
        ordered = sorted(values.items(), key=lambda item: abs(item[1]) if item[1] is not None else -1.0, reverse=True)
        dimensions[residual_name]["cumulative_state_specificity"] = {
            "same_name_absolute_rank": next(index for index, item in enumerate(ordered, 1) if item[0] == residual_name),
            "strongest_association": {"dimension": ordered[0][0], "spearman": ordered[0][1]},
        }
    internal = {left: {right: _correlation(residual_series[left], residual_series[right], rank=True)
                       for right in DIMENSIONS} for left in DIMENSIONS}
    own_pattern = re.compile(r"\bown(?:s|ed|ing)?\b", re.IGNORECASE)
    own_rows = [index for index, row in enumerate(rows) if own_pattern.search(str(row.get("input_text", "")))]
    own_row_set = set(own_rows)
    other_rows = [index for index in range(len(rows)) if index not in own_row_set]
    own_monitor: dict[str, Any] = {"turns_with_own": len(own_rows), "turns_without_own": len(other_rows), "directions": {}}
    for name in ("Safety", "Tension"):
        complete = residual_series[name].size == len(rows)
        own_values = residual_series[name][own_rows] if complete else np.asarray([], dtype=np.float64)
        other_values = residual_series[name][other_rows] if complete else np.asarray([], dtype=np.float64)
        own_monitor["directions"][name] = {
            "mean_control_z_with_own": float(np.mean(own_values)) if own_values.size else None,
            "mean_control_z_without_own": float(np.mean(other_values)) if other_values.size else None,
            "difference": float(np.mean(own_values) - np.mean(other_values)) if own_values.size and other_values.size else None,
        }
    own_monitor["safety_tension_residual_spearman"] = internal["Safety"]["Tension"]
    own_monitor["interpretation"] = "lexical co-occurrence is confounded by turn topic and does not prove the token caused either projection"
    result = {
        "schema": 1,
        "turns": len(rows),
        "dimensions": dimensions,
        "cross_dimension_cumulative_state_spearman": cross_state,
        "residual_projection_spearman": internal,
        "own_token_monitor": own_monitor,
        "interpretation_boundary": [
            "EmoClaw values are cumulative sampled state, not per-turn labels.",
            "Snapshot deltas may include decay or background-organ nudges even when the conversation alignment is unique.",
            "Association is exploratory and is not agreement, accuracy, consciousness, or causality.",
        ],
        "monitor": [
            {"direction": "Safety", "token": "own", "reason": "accepted promoted token with more than twice the next token's score"},
            {"direction": "Tension", "token": "own", "reason": "accepted shared promoted token; monitor cross-direction behavior"},
        ],
        "truth_status": "offline_exploratory_association_against_cumulative_emoclaw_history",
    }
    from .io import atomic_json
    atomic_json(output_path, result)
    return result


def join(emoclaw_path: Path, residual_path: Path, output_path: Path) -> dict[str, int]:
    emoclaw = {str(row["turn_id"]): row for row in read_jsonl(emoclaw_path)}
    residual = {str(row["turn_id"]): row for row in read_jsonl(residual_path)}
    ids = sorted(emoclaw.keys() & residual.keys())
    rows = [{
        "turn_id": turn_id,
        "timestamp": residual[turn_id].get("timestamp") or emoclaw[turn_id].get("timestamp"),
        "input_text": residual[turn_id].get("input_text") or emoclaw[turn_id].get("input_text", ""),
        "emoclaw_scores": emoclaw[turn_id].get("scores", {}),
        "emoclaw_state_delta": emoclaw[turn_id].get("state_delta", {}),
        "residual_measurements": residual[turn_id].get("measurements", {}),
        "agreement": "not_computed_scale_not_calibrated",
        "divergence_points": [],
        "truth_status": "offline_join_no_outcome_claim",
    } for turn_id in ids]
    output_path.unlink(missing_ok=True)
    append_jsonl(output_path, rows)
    return {"emoclaw": len(emoclaw), "residual": len(residual), "joined": len(rows)}
