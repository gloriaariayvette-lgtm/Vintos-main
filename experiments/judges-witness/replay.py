#!/usr/bin/env python3
"""Offline witness census and chat innovation. Standard library; no model calls.

Only explicitly supplied scratch snapshots are read. No backup discovery, live
stores, fitting, feed writes, emotion verdicts, or identity verdicts.
"""
import argparse
from collections import Counter, defaultdict
import json
import math
import os
from pathlib import Path
import statistics
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from witness_receipts import admission, digest, envelope_status, instant, row_receipt, joined_identity, final_response


def adapt(rows, kind):
    if not isinstance(rows, list):
        raise ValueError("snapshot must contain a list of records")
    if kind not in ("canonical", "merged", "ledger"):
        raise ValueError("unsupported source adapter")
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("record must be an object")
        out = dict(row)
        if kind == "ledger":
            # This census concerns finalized assistant acts, never her input text.
            out.update(role="assistant", content=row.get("vintos"))
        yield out


def census(sources, nodes, cutoff):
    groups, reasons, envelopes = defaultdict(list), Counter(), Counter()
    source_counts, identity_joins, duplicate_reasons = {}, 0, Counter()
    for kind, rows in sources:
        adapted = list(adapt(rows, kind))
        source_counts[kind] = source_counts.get(kind, 0) + len(adapted)
        for row in adapted:
            if row.get("role") != "assistant":
                reasons["not_reply"] += 1
                continue
            key, identity_status = joined_identity(row)
            if key is None:
                envelopes[envelope_status(row)] += 1
                reasons[identity_status] += 1
                continue
            if not row.get("turn_id"):
                identity_joins += 1
            row = dict(row, turn_id=key)
            envelopes[envelope_status(row)] += 1
            groups[key].append(row)
    admitted = []
    for copies in groups.values():
        # An explicitly excluded duplicate cannot be laundered through another store.
        states = [admission(r, nodes, cutoff) for r in copies]
        if any(s != "eligible" for s in states):
            reasons["duplicate_held" if len(copies) > 1 else states[0]] += 1
            if len(copies) > 1:
                duplicate_reasons.update(s for s in states if s != "eligible")
            continue
        first = copies[0]
        if any(final_response(r) != final_response(first) or row_receipt(r) != row_receipt(first)
               for r in copies[1:]):
            reasons["conflicting_duplicate"] += 1
            continue
        admitted.append(first)
    admitted.sort(key=lambda r: (row_receipt(r)["finalized_at"], r["turn_id"]))
    lengths = [len(final_response(r).split()) for r in admitted]
    summary = {"source_rows": source_counts, "envelope_rows": dict(envelopes),
               "unique_identified_replies": len(groups), "eligible_replies": len(admitted),
               "held": dict(reasons), "duplicate_held_copy_reasons": dict(duplicate_reasons),
               "envelope_id_joins": identity_joins, "behaviour": {
                   "mean_words": statistics.mean(lengths) if lengths else None,
                   "question_fraction": sum("?" in final_response(r) for r in admitted) / len(admitted)
                   if admitted else None},
               "meaning": "descriptive behaviour only; no authenticity or emotion verdict"}
    return summary, admitted


def cosine_error(a, b):
    if not isinstance(a, list) or not isinstance(b, list) or not a or len(a) != len(b):
        raise ValueError("incompatible embeddings")
    if any(isinstance(x, bool) or not isinstance(x, (float, int)) or not math.isfinite(x)
           for x in a + b):
        raise ValueError("nonfinite embeddings")
    na, nb = math.hypot(*a), math.hypot(*b)
    if not na or not nb or not math.isfinite(na * nb):
        raise ValueError("invalid embedding norm")
    return 1 - max(-1, min(1, sum((x / na) * (y / nb) for x, y in zip(a, b))))


def innovation(admitted, forecasts, embeddings, checkpoints, minimum_history=20):
    """Match a pre-finalization on-message forecast to one finalized output.

    Checkpoint identities/encoder/training times must come from an independently
    retained manifest. Historical forecast logs alone cannot prove these facts.
    Percentiles use strictly earlier outcomes in this replay, never the target.
    """
    if minimum_history < 1:
        raise ValueError("history minimum must be positive")
    targets = {r["turn_id"]: r for r in admitted}
    cache = defaultdict(list)
    for e in embeddings:
        cache[e.get("turn_id")].append(e)
    held, candidates = Counter(), defaultdict(list)
    for f in forecasts:
        try:
            row = targets.get(f.get("turn_id"))
            if row is None:
                held["no_eligible_final_reply"] += 1
                continue
            r, head = row_receipt(row), f["self"]
            if f.get("mode") != "on_message" or head.get("mode") != "on_message":
                held["wrong_mode"] += 1
                continue
            if f.get("surface") != r["surface"]:
                held["wrong_surface"] += 1
                continue
            checkpoint = head["checkpoint_id"]
            manifest = checkpoints[checkpoint]
            encoder = manifest["encoder_id"]
            if (not isinstance(encoder, str) or not encoder or not isinstance(head.get("source"), str)
                    or not head["source"]):
                raise ValueError("missing checkpoint or forecast identity")
            if manifest.get("source") != head["source"]:
                held["checkpoint_source_mismatch"] += 1
                continue
            made = instant(f["ts"])
            arrived = instant(f["arrived_at"])
            if not (instant(manifest["trained_at"]) < made < r["finalized_at"]
                    and arrived <= made and arrived <= r["started_at"]
                    and instant(head["context_last_ts"]) < arrived):
                held["noncausal_forecast"] += 1
                continue
            matches = [e for e in cache[row["turn_id"]]
                       if e.get("response_sha256") == digest(final_response(row))
                       and e.get("encoder_id") == encoder]
            if not matches or any(e.get("emb") != matches[0].get("emb") for e in matches):
                held["missing_or_conflicting_embedding"] += 1
                continue
            error = cosine_error(head["emb"], matches[0]["emb"])
            group = (checkpoint, encoder, r["surface"], "on_message", head["source"])
            candidates[(row["turn_id"], group)].append({
                "turn_id": row["turn_id"], "response_sha256": r["response_sha256"],
                "group": group, "forecast_at": made, "finalized_at": r["finalized_at"],
                "error": error})
        except (KeyError, TypeError, ValueError, OverflowError):
            held["missing_or_invalid_forecast_evidence"] += 1
    scored = []
    for choices in candidates.values():
        earliest = min(c["forecast_at"] for c in choices)
        tied = [c for c in choices if c["forecast_at"] == earliest]
        if any(c != tied[0] for c in tied):
            held["conflicting_forecast"] += 1
            continue
        held["duplicate_forecasts"] += len(choices) - 1
        scored.append(tied[0])
    scored.sort(key=lambda r: (r["finalized_at"], r["turn_id"], r["group"]))
    histories = defaultdict(list)
    for row in scored:
        group = tuple(row["group"])
        prior = [r["error"] for r in histories[group] if r["finalized_at"] < row["finalized_at"]]
        row["prior_n"] = len(prior)
        row["innovation_percentile"] = (
            100 * sum((v < row["error"]) + .5 * (v == row["error"]) for v in prior) / len(prior)
            if len(prior) >= minimum_history else None)
        histories[group].append(row)
    # Never pool different checkpoints/surfaces into one performance claim.
    aggregate = []
    for group, rows in histories.items():
        aggregate.append({"checkpoint_group": len(aggregate) + 1, "n": len(rows),
                          "mean_cosine_error": statistics.mean(r["error"] for r in rows),
                          "percentiles_available": sum(r["innovation_percentile"] is not None for r in rows)})
    return {"groups": aggregate, "held": dict(held), "baselines": "not supplied",
            "meaning": "prediction innovation, not authenticity or a pass verdict"}, scored


def scratch_root(value):
    raw = Path(value).absolute()
    root = raw.resolve(strict=True)
    repo = Path(__file__).resolve().parents[2]
    if (root != raw or not root.is_dir() or root in (Path("/"), Path.home(), repo)
            or root in repo.parents or repo in root.parents
            or any(p in (".vintos", ".openclaw") for p in root.parts)
            or os.environ.get("SPARK_WORKSPACE") != str(root)):
        raise ValueError("requires a separate explicit private scratch workspace")
    if root.stat().st_mode & 0o077:
        raise ValueError("scratch workspace must have mode 0700")
    return root


def inside(root, value):
    path = Path(value).absolute()
    resolved = path.resolve()
    if resolved != path or root not in resolved.parents:
        raise ValueError("path must be strictly inside scratch without symlink traversal")
    return resolved


def install_guard(root, output):
    """Guard all writes (including rename) plus subprocesses and network."""
    def write_path(value):
        if not isinstance(value, (str, bytes, os.PathLike)):
            raise PermissionError("descriptor writes are not admitted")
        path = inside(root, os.fsdecode(value))
        if path != output and output not in path.parents:
            raise PermissionError("writes restricted to new output directory")
    def hook(event, args):
        if event.startswith(("socket.", "subprocess.", "os.exec", "os.spawn")) or event in ("os.system", "os.fork", "os.forkpty"):
            raise PermissionError("offline replay forbids network and subprocesses")
        if event == "open":
            mode, flags = args[1], args[2]
            if (isinstance(mode, str) and any(c in mode for c in "wax+")) or (
                    isinstance(flags, int) and flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)):
                write_path(args[0])
        if event in ("os.rename", "os.link", "os.symlink"):
            raise PermissionError("replay does not need link or rename operations")
        if event in ("os.remove", "os.rmdir", "os.mkdir", "os.chmod", "os.chown", "os.truncate", "os.utime"):
            write_path(args[0])
    sys.addaudithook(hook)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--scratch", required=True)
    p.add_argument("--input", required=True, help="explicit synthetic or admitted snapshot bundle JSON")
    p.add_argument("--output", required=True, help="new private output directory")
    p.add_argument("--cutoff", required=True, help="exclusive timestamp with explicit timezone")
    args = p.parse_args()
    root = scratch_root(args.scratch)
    source, output = inside(root, args.input), inside(root, args.output)
    if output.exists() or output in source.parents:
        raise ValueError("output must be new and cannot contain input")
    install_guard(root, output)
    with source.open() as f:
        bundle = json.load(f)
    if bundle.get("input_kind") not in ("synthetic", "retained_snapshot"):
        raise ValueError("input_kind must explicitly distinguish synthetic from retained_snapshot")
    # No discovery or historical fallback. Missing components are explicit empty evidence.
    nodes = {}
    for node in bundle.get("lineage", []):
        if node["id"] in nodes:
            raise ValueError("duplicate lineage identity")
        nodes[node["id"]] = node
    summary, admitted = census([(s["kind"], s["rows"]) for s in bundle.get("sources", [])],
                               nodes, instant(args.cutoff))
    scores, details = innovation(admitted, bundle.get("forecasts", []),
                                 bundle.get("embeddings", []), bundle.get("checkpoints", {}))
    report = {"schema": "judges-shadow-v1", "input_kind": bundle.get("input_kind", "unspecified"),
              "census": summary, "innovation": scores}
    output.mkdir(mode=0o700)
    for name, value in (("aggregate.json", report), ("private-innovation.json", details)):
        with (output / name).open("x") as f:
            os.chmod(f.name, 0o600)
            json.dump(value, f, indent=2, allow_nan=False)
            f.write("\n")
    print(json.dumps({"eligible_replies": len(admitted), "forecast_groups": len(scores["groups"])}))


if __name__ == "__main__":
    main()
