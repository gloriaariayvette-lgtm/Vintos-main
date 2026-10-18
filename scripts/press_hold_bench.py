#!/usr/bin/env python3
"""Offline press/hold trial ledger. Explicit stores only; no sensing or scoring I/O."""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import json
import math
import os
from pathlib import Path
import re
import sys
import uuid


SCHEMA_VERSION = 1
LABELS = ("press", "hold")
STATUSES = ("scored", "unscored", "failed")
REQUIRED = {"trial_id", "word", "requested_duration_ms", "expected_label", "status"}
OPTIONAL = {"measured_duration_ms", "observed_label", "score", "score_method", "error_code", "retry_of"}
PAYLOAD_FIELDS = REQUIRED | OPTIONAL
META_FIELDS = {"schema_version", "run_id", "data_kind", "recorded_at_utc"}
MANIFEST_FIELDS = {"schema_version", "run_id", "data_kind", "created_at_utc", "words",
                   "durations_ms", "source_commit"}


def _text(value, name, limit=128):
    if not isinstance(value, str) or not value or value != value.strip() or len(value) > limit or not value.isprintable():
        raise ValueError("%s must be nonempty printable text, without surrounding whitespace (max %d)" % (name, limit))
    return value


def _identifier(value, name):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", value):
        raise ValueError("%s must use 1-64 ASCII letters, digits, underscores or hyphens" % name)
    return value


def _number(value, name, positive=False):
    try:
        finite = type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        finite = False
    if not finite or (value <= 0 if positive else value < 0):
        raise ValueError("%s must be a finite %s number" % (name, "positive" if positive else "nonnegative"))
    return int(value) if value == int(value) else value


def _now():
    return datetime.now(timezone.utc).isoformat()


def _timestamp(value):
    if not isinstance(value, str):
        raise ValueError("timestamp must be a UTC ISO string")
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset().total_seconds() != 0:
        raise ValueError("timestamp must be a UTC ISO string")


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _json(raw):
    def invalid_constant(value):
        raise ValueError("nonfinite JSON number")
    return json.loads(raw, object_pairs_hook=_unique, parse_constant=invalid_constant)


def _matrix(words, durations_ms):
    if not isinstance(words, (list, tuple)) or len(words) != 8:
        raise ValueError("a run requires exactly eight words")
    words = [_text(word, "word", 64) for word in words]
    if len(set(words)) != 8:
        raise ValueError("run words must be distinct (case sensitive)")
    if not isinstance(durations_ms, (list, tuple)) or len(durations_ms) != 5:
        raise ValueError("a run requires exactly five durations_ms")
    durations = [_number(value, "duration_ms", positive=True) for value in durations_ms]
    if len(set(durations)) != 5:
        raise ValueError("run durations_ms must be distinct")
    return {"words": words, "durations_ms": durations}


def _config(words, durations_ms, data_kind, source_commit):
    matrix = _matrix(words, durations_ms)
    if data_kind not in ("synthetic", "observed"):
        raise ValueError("data_kind must be synthetic or observed")
    if source_commit is not None and (not isinstance(source_commit, str) or not re.fullmatch(r"[0-9a-f]{40}", source_commit)):
        raise ValueError("source_commit must be a full lowercase Git SHA or null")
    return dict(matrix, data_kind=data_kind, source_commit=source_commit)


def _directory(store, run_id):
    _identifier(run_id, "run_id")
    if not isinstance(store, (str, os.PathLike)) or not str(store).strip():
        raise ValueError("store must be an explicit nonempty directory path")
    directory = Path(store).expanduser().resolve() / run_id
    if directory.is_symlink():
        raise ValueError("run directory must not be a symlink")
    return directory


def _open(path, flags, mode):
    fd = os.open(path, flags | getattr(os, "O_NOFOLLOW", 0), 0o600)
    return os.fdopen(fd, mode, encoding="utf-8", newline="")


def load_plan(path):
    """Read an unobserved plan; a plan is configuration, never trial evidence."""
    with _open(path, os.O_RDONLY, "r") as stream:
        plan = _json(stream.read())
    fields = {"schema_version", "record_type", "plan_id", "provenance", "words",
              "durations_ms", "planned_cell_count", "planned_rows", "observations", "scores"}
    if not isinstance(plan, dict) or set(plan) != fields:
        raise ValueError("invalid run plan fields")
    if type(plan["schema_version"]) is not int or plan["schema_version"] != SCHEMA_VERSION or plan["record_type"] != "paper_derived_run_plan":
        raise ValueError("invalid run plan identity/version")
    _identifier(plan["plan_id"], "plan_id")
    matrix = _matrix(plan["words"], plan["durations_ms"])
    count = len(matrix["words"]) * len(matrix["durations_ms"])
    if type(plan["planned_cell_count"]) is not int or plan["planned_cell_count"] != count:
        raise ValueError("planned_cell_count must match the 40-cell matrix")
    if plan["observations"] != [] or plan["scores"] != []:
        raise ValueError("run plan observations and scores must be empty lists")
    rows = plan["planned_rows"]
    if not isinstance(rows, list) or len(rows) != count:
        raise ValueError("run plan must contain exactly 40 planned rows")
    expected = {(word, duration) for word in matrix["words"] for duration in matrix["durations_ms"]}
    empty_fields = {"measured_duration_ms", "expected_label", "observed_label", "score", "score_method"}
    seen = set()
    for row in rows:
        if not isinstance(row, dict) or set(row) != empty_fields | {"word", "requested_duration_ms", "status"}:
            raise ValueError("invalid planned row fields")
        _text(row["word"], "planned word", 64)
        cell = (row["word"], _number(row["requested_duration_ms"], "planned duration_ms", positive=True))
        if cell not in expected or cell in seen:
            raise ValueError("planned rows must cover every word-duration cell exactly once")
        if row["status"] != "planned" or any(row[key] is not None for key in empty_fields):
            raise ValueError("planned rows must have empty observations, labels and scores")
        seen.add(cell)
    provenance = plan["provenance"]
    if not isinstance(provenance, dict) or set(provenance) != {"basis", "citation"}:
        raise ValueError("run plan requires explicit provenance")
    _text(provenance["basis"], "provenance basis", 512)
    if provenance["citation"] is not None:
        _text(provenance["citation"], "citation", 2000)
    return dict(plan, **matrix)


def create_run(store, *, words=None, durations_ms=None, data_kind, run_id=None, source_commit=None, plan=None):
    """Create a new immutable manifest and empty ledger; existing runs are refused."""
    selected_plan = None
    if plan is not None:
        if words is not None or durations_ms is not None:
            raise ValueError("use either a run plan or explicit words/durations, not both")
        selected_plan = load_plan(plan)
        words, durations_ms = selected_plan["words"], selected_plan["durations_ms"]
    config = _config(words, durations_ms, data_kind, source_commit)
    run_id = _identifier(run_id if run_id is not None else uuid.uuid4().hex, "run_id")
    directory = _directory(store, run_id)
    manifest = dict(config, schema_version=SCHEMA_VERSION, run_id=run_id, created_at_utc=_now())
    if selected_plan is not None:
        manifest["plan_id"] = selected_plan["plan_id"]
    directory.parent.mkdir(parents=True, exist_ok=True)
    directory.mkdir()  # Exclusive creation: never replace a previous run.
    with _open(directory / "manifest.json", os.O_WRONLY | os.O_CREAT | os.O_EXCL, "w") as stream:
        stream.write(json.dumps(manifest, ensure_ascii=False, allow_nan=False, indent=2) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    with _open(directory / "scores.jsonl", os.O_WRONLY | os.O_CREAT | os.O_EXCL, "w") as stream:
        stream.flush()
        os.fsync(stream.fileno())
    return {"manifest": manifest, "manifest_path": str(directory / "manifest.json"),
            "scores_path": str(directory / "scores.jsonl")}


def _manifest(directory, run_id):
    with _open(directory / "manifest.json", os.O_RDONLY, "r") as stream:
        manifest = _json(stream.read())
    if not isinstance(manifest, dict) or set(manifest) not in (MANIFEST_FIELDS, MANIFEST_FIELDS | {"plan_id"}):
        raise ValueError("invalid run manifest fields")
    if type(manifest["schema_version"]) is not int or manifest["schema_version"] != SCHEMA_VERSION or manifest["run_id"] != run_id:
        raise ValueError("run manifest identity/version mismatch")
    _timestamp(manifest["created_at_utc"])
    _config(manifest["words"], manifest["durations_ms"], manifest["data_kind"], manifest["source_commit"])
    if "plan_id" in manifest:
        _identifier(manifest["plan_id"], "plan_id")
    return manifest


def _payload(manifest, values):
    if not REQUIRED <= set(values) or set(values) - PAYLOAD_FIELDS:
        raise ValueError("invalid trial fields")
    row = {key: values.get(key) for key in sorted(PAYLOAD_FIELDS)}
    _identifier(row["trial_id"], "trial_id")
    _text(row["word"], "word", 64)
    if row["word"] not in manifest["words"]:
        raise ValueError("word is not in this run")
    row["requested_duration_ms"] = _number(row["requested_duration_ms"], "requested_duration_ms", positive=True)
    if row["requested_duration_ms"] not in manifest["durations_ms"]:
        raise ValueError("requested_duration_ms is not in this run")
    if row["measured_duration_ms"] is not None:
        row["measured_duration_ms"] = _number(row["measured_duration_ms"], "measured_duration_ms")
    if row["expected_label"] not in LABELS or (row["observed_label"] is not None and row["observed_label"] not in LABELS):
        raise ValueError("labels must be press or hold (observed_label may be null when not scored)")
    if row["status"] not in STATUSES:
        raise ValueError("status must be scored, unscored or failed")
    if row["status"] == "scored":
        if row["measured_duration_ms"] is None or row["observed_label"] is None:
            raise ValueError("scored trials require measured_duration_ms and observed_label")
        score = _number(row["score"], "score")
        if score > 1:
            raise ValueError("scored trials require a finite normalized score in [0, 1]")
        row["score"] = score
        _text(row["score_method"], "score_method")
    elif row["score"] is not None or row["score_method"] is not None:
        raise ValueError("failed/unscored trials must have null score and score_method")
    if row["status"] == "failed":
        _identifier(row["error_code"], "error_code")
    elif row["error_code"] is not None:
        raise ValueError("only failed trials may have error_code")
    if row["retry_of"] is not None:
        _identifier(row["retry_of"], "retry_of")
    return row


def _cell(row):
    return row["word"], row["requested_duration_ms"]


def _check_history(row, previous):
    for prior in previous.values():
        if _cell(prior) == _cell(row) and prior["expected_label"] != row["expected_label"]:
            raise ValueError("expected_label must remain consistent within a word-duration cell")
    if row["retry_of"] is not None:
        prior = previous.get(row["retry_of"])
        if prior is None or prior["status"] == "scored" or _cell(prior) != _cell(row):
            raise ValueError("retry_of must name a prior failed/unscored trial in the same cell")
        if any(other["retry_of"] == row["retry_of"] for other in previous.values()):
            raise ValueError("retry already has a successor; retry the latest failed/unscored attempt")


@contextmanager
def _ledger(directory, writing):
    flags = os.O_RDWR | os.O_APPEND if writing else os.O_RDONLY
    with _open(directory / "scores.jsonl", flags, "a+" if writing else "r") as stream:
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX if writing else fcntl.LOCK_SH)
        stream.seek(0)
        yield stream


def _history(stream, manifest):
    previous = {}
    for number, line in enumerate(stream, 1):
        try:
            if not line.endswith("\n"):
                raise ValueError("unterminated record")
            row = _json(line)
            if not isinstance(row, dict) or set(row) != PAYLOAD_FIELDS | META_FIELDS:
                raise ValueError("invalid record fields")
            if (type(row["schema_version"]) is not int or row["schema_version"] != SCHEMA_VERSION
                    or row["run_id"] != manifest["run_id"] or row["data_kind"] != manifest["data_kind"]):
                raise ValueError("record identity/version mismatch")
            _timestamp(row["recorded_at_utc"])
            payload = _payload(manifest, {key: row[key] for key in PAYLOAD_FIELDS})
            if payload["trial_id"] in previous:
                raise ValueError("duplicate stored trial_id")
            _check_history(payload, previous)
            previous[payload["trial_id"]] = row
        except (ValueError, TypeError, KeyError) as exc:
            raise ValueError("invalid ledger record at line %d: %s; ledger unchanged" % (number, exc)) from exc
    return previous


def record_trial(store, run_id, **values):
    """Append one supplied observation; identical trial-ID replays are no-ops."""
    directory = _directory(store, run_id)
    manifest = _manifest(directory, run_id)
    payload = _payload(manifest, values)
    with _ledger(directory, True) as stream:
        previous = _history(stream, manifest)
        existing = previous.get(payload["trial_id"])
        if existing is not None:
            if payload != {key: existing[key] for key in PAYLOAD_FIELDS}:
                raise ValueError("trial_id already exists with different data")
            return {"appended": False, "record": existing}
        _check_history(payload, previous)
        row = dict(payload, schema_version=SCHEMA_VERSION, run_id=run_id,
                   data_kind=manifest["data_kind"], recorded_at_utc=_now())
        stream.write(json.dumps(row, ensure_ascii=False, allow_nan=False, separators=(",", ":")) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    return {"appended": True, "record": row}


def coverage(store, run_id):
    """Coverage is scored cells, not score quality; failures never count as scores."""
    directory = _directory(store, run_id)
    manifest = _manifest(directory, run_id)
    with _ledger(directory, False) as stream:
        rows = list(_history(stream, manifest).values())
    cells = [(word, duration) for word in manifest["words"] for duration in manifest["durations_ms"]]
    attempted = {_cell(row) for row in rows}
    measured = {_cell(row) for row in rows if row["measured_duration_ms"] is not None}
    scored = {_cell(row) for row in rows if row["status"] == "scored"}
    def missing(found):
        return [{"word": word, "requested_duration_ms": duration} for word, duration in cells if (word, duration) not in found]
    return {"schema_version": SCHEMA_VERSION, "run_id": run_id, "data_kind": manifest["data_kind"],
            "expected_cells": len(cells), "trial_count": len(rows), "attempted_cells": len(attempted),
            "measured_cells": len(measured), "scored_cells": len(scored), "complete": len(scored) == len(cells),
            "status_counts": {status: sum(row["status"] == status for row in rows) for status in STATUSES},
            "retry_count": sum(row["retry_of"] is not None for row in rows),
            "missing_scored_cells": missing(scored), "unattempted_cells": missing(attempted)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init", help="create an eight-word/five-duration run; no experiment is run")
    init.add_argument("--store", required=True)
    init.add_argument("--run-id")
    init.add_argument("--words", nargs=8)
    init.add_argument("--durations-ms", nargs=5, type=float)
    init.add_argument("--plan", help="unobserved JSON run plan, instead of explicit words/durations")
    init.add_argument("--data-kind", choices=("synthetic", "observed"), required=True)
    init.add_argument("--source-commit")
    record = sub.add_parser("record", help="append supplied trial data; does not acquire or compute it")
    record.add_argument("--store", required=True)
    record.add_argument("--run-id", required=True)
    for key in ["trial-id", "word", "expected-label", "status"]:
        record.add_argument("--" + key, required=True)
    record.add_argument("--requested-duration-ms", type=float, required=True)
    record.add_argument("--measured-duration-ms", type=float)
    record.add_argument("--observed-label")
    record.add_argument("--score", type=float)
    for key in ["score-method", "error-code", "retry-of"]:
        record.add_argument("--" + key)
    check = sub.add_parser("coverage", help="report this run's 40-cell coverage without writing")
    check.add_argument("--store", required=True)
    check.add_argument("--run-id", required=True)
    check.add_argument("--require-complete", action="store_true", help="exit 1 if scored coverage is incomplete")
    args = vars(parser.parse_args(argv))
    command = args.pop("command")
    require_complete = args.pop("require_complete", False)
    try:
        result = {"init": create_run, "record": record_trial, "coverage": coverage}[command](**args)
    except (OSError, ValueError) as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, allow_nan=False, indent=2))
    return 1 if require_complete and not result["complete"] else 0


if __name__ == "__main__":
    sys.exit(main())
