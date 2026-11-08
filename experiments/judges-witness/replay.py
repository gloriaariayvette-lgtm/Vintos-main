#!/usr/bin/env python3
"""Offline witness census and chat innovation. Standard library; no model calls.

Only explicitly supplied scratch snapshots are read. No backup discovery, live
stores, fitting, feed writes, emotion verdicts, or identity verdicts.
"""
import argparse
import hashlib
from collections import Counter, defaultdict
import json
import math
import os
import re
from pathlib import Path
import statistics
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from witness_receipts import admission, digest, envelope_status, instant, row_receipt, joined_identity, final_response


def adapt(rows, kind):
    if not isinstance(rows, list):
        raise ValueError("snapshot must contain a list of records")
    if kind not in ("canonical", "merged", "ledger", "capture"):
        raise ValueError("unsupported source adapter")
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("record must be an object")
        if kind == "capture" and row.get("schema") != "witness-capture-v1":
            raise ValueError("unsupported capture packet schema")
        out = dict(row)
        out["_witness_adapter_kind"] = kind
        if kind == "ledger":
            # This census concerns finalized assistant acts, never her input text.
            out.update(role="assistant", content=row.get("vintos"))
        yield out


def snapshot_nodes(sources, lineage):
    """Join explicit ancestry and packet nodes without silently overwriting either.

    Reading a capture does not attest delivery, complete its ancestry, or make
    its reply an ordinary source. Identical node copies are harmless;
    conflicting attestations abort the snapshot rather than selecting a winner.
    """
    nodes = {}

    def add(node, repeated=False):
        if not isinstance(node, dict) or not isinstance(node.get("id"), str) or not node["id"]:
            raise ValueError("invalid lineage identity")
        key = node["id"]
        if key in nodes and (not repeated or nodes[key] != node):
            raise ValueError("duplicate or conflicting lineage identity")
        nodes[key] = node

    if not isinstance(lineage, list):
        raise ValueError("lineage must be a list")
    for node in lineage:
        add(node)
    for kind, rows in sources:
        if kind != "capture":
            continue
        for packet in adapt(rows, kind):
            parents = packet.get("lineage")
            reply = packet.get("reply_node")
            if (not isinstance(parents, list) or not isinstance(reply, dict)
                    or reply.get("kind") != "reply" or not packet.get("turn_id")
                    or reply.get("turn_id") != packet["turn_id"]):
                raise ValueError("capture requires its explicit reply node and lineage")
            for node in parents:
                add(node, repeated=True)
            add(reply, repeated=True)
    return nodes


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



def behaviour_receipt(admitted, start, cutoff, surfaces, snapshot_sha256=None):
    """Bounded descriptive receipt; private member manifest, no learned verdict.

    The caller supplies census-admitted unique replies. Surface scope is explicit;
    neither empty inputs nor missing days prove there was no behaviour outside
    the supplied snapshot. Model/revision groups never share a reference mean.
    """
    start, cutoff = instant(start), instant(cutoff)
    if start >= cutoff:
        raise ValueError("behaviour window must have positive duration")
    if (not isinstance(surfaces, (list, tuple)) or not surfaces
            or any(not isinstance(x, str) or not x.strip() for x in surfaces)):
        raise ValueError("behaviour requires explicit nonempty surface scope")
    surfaces = sorted(set(surfaces))
    seen, groups, held = set(), defaultdict(list), Counter()
    for row in admitted:
        r = row_receipt(row)
        if r.get("status") != "recorded" or r["turn_id"] != row.get("turn_id"):
            raise ValueError("behaviour requires admitted receipt identities")
        if r["turn_id"] in seen:
            raise ValueError("behaviour requires unique admitted replies")
        seen.add(r["turn_id"])
        if not start <= r["finalized_at"] < cutoff:
            held["outside_window"] += 1
            continue
        if r["surface"] not in surfaces:
            held["outside_surface_scope"] += 1
            continue
        selected = [a for a in r["generation"]["attempts"] if a["outcome"] == "selected"]
        if (len(selected) != 1 or not selected[0].get("served_model")
                or selected[0].get("identity_evidence") not in ("response_metadata", "runtime_receipt")):
            raise ValueError("behaviour requires observed served identity")
        text = final_response(row)
        if not isinstance(text, str) or digest(text) != r["response_sha256"]:
            raise ValueError("behaviour requires exact finalized content")
        a = selected[0]
        key = (r["surface"], a["served_model"], a.get("served_revision") or "")
        member = {"turn_id":r["turn_id"], "response_sha256":r["response_sha256"],
                  "context_receipt_id":r["context_receipt_id"], "finalized_at":r["finalized_at"],
                  "generation_receipt_sha256":digest(json.dumps(r, sort_keys=True, separators=(",", ":"))),
                  "word_count":len(text.split()), "has_question_mark":"?" in text}
        groups[key].append(member)
    public, private = [], []
    for key in sorted(groups):
        members = sorted(groups[key], key=lambda r:(r["finalized_at"],r["turn_id"]))
        lengths = [r["word_count"] for r in members]
        ordinal = len(public) + 1
        public.append({"group":ordinal, "n":len(members),
                       "mean_words":statistics.mean(lengths), "median_words":statistics.median(lengths),
                       "question_mark_fraction":sum(r["has_question_mark"] for r in members)/len(members)})
        private.append({"group":ordinal,"surface":key[0],"served_model":key[1],
                        "served_revision":key[2] or None,"members":members})
    # The private digest includes exact membership/versions/window and scope, not
    # generation wall time or input ordering. Removing a source rebuilds it.
    receipt = {"schema":"judges-behaviour-receipt-v1", "window":{"start":start,"cutoff":cutoff},
               "surface_scope":surfaces, "groups":private, "statistics":public}
    receipt["source_bundle_sha256"] = snapshot_sha256
    receipt["receipt_id"] = "behaviour:" + digest(json.dumps(receipt, sort_keys=True, separators=(",", ":")))
    summary = {"schema":"judges-behaviour-summary-v1", "status":"descriptive" if public else "no_eligible_observations",
               "eligible_observations":sum(g["n"] for g in public), "groups":public, "not_in_summary":dict(held),
               "coverage":"explicit snapshot only; stream completeness and missing-day activity unknown",
               "meaning":"word lengths and literal question marks, not authenticity, emotion or relationship quality"}
    return summary, receipt


def feedback_receipts(admitted, events, cutoff):
    """Explicit positive markers, not inferred mood or negative outcomes.

    Timeline positions and origin are producer attestations. Never reconstruct
    adjacency from the admitted subset: an excluded/intervening turn still breaks
    the join. Practice ratings require an exact versioned practice target.
    """
    cutoff = instant(cutoff)
    targets = {r["turn_id"]:r for r in admitted}
    if len(targets) != len(admitted):
        raise ValueError("feedback needs unique admitted targets")
    if not isinstance(events, list): raise ValueError("feedback_events must be a list")
    copies, held = defaultdict(list), Counter()
    for event in events:
        if not isinstance(event, dict) or not isinstance(event.get("event_id"), str) or not event["event_id"]:
            held["missing_event_identity"] += 1
            continue
        copies[event["event_id"]].append(event)
    unique = {}
    for key, rows in copies.items():
        if any(r != rows[0] for r in rows):
            held["conflicting_event_identity"] += 1
        else: unique[key] = rows[0]
    # Include every claimed position, even excluded/conflicting/unknown events.
    # They cannot disappear and create apparently immediate neighbours.
    positions = defaultdict(set)
    for e in events:
        if (isinstance(e, dict) and isinstance(e.get("stream_id"), str) and e["stream_id"]
                and type(e.get("position")) is int and e["position"] >= 0):
            key = e.get("event_id")
            # An unidentified event still occupies its claimed position. None
            # cannot equal a valid event ID and cannot resolve to a predecessor.
            positions[(e["stream_id"],e["position"])].add(
                key if isinstance(key, str) and key else None)

    def direct_witness(event):
        return event.get("witnessed") is True and not any(event.get(k) for k in
            ("inferred", "deleted", "forgotten", "timestamp_estimated", "imported", "transplanted"))
    observations = []
    for key, event in sorted(unique.items()):
        kind = event.get("kind")
        predecessor_sha256 = None
        if kind == "assistant_reply": continue
        try:
            if event.get("schema") != "witness-feedback-v1":
                held["unsupported_feedback_schema"] += 1; continue
            if not direct_witness(event):
                held["feedback_not_direct_witness"] += 1; continue
            at = instant(event["at"])
            if at >= cutoff:
                held["feedback_at_or_after_cutoff"] += 1; continue
            if kind == "counterpart_message":
                if event.get("origin") != "authenticated_owner_message":
                    held["unknown_feedback_origin"] += 1; continue
                text = event["text"]
                if not isinstance(text,str) or digest(text) != event["content_sha256"]:
                    held["feedback_version_mismatch"] += 1; continue
                stream, position = event["stream_id"], event["position"]
                if (not isinstance(stream,str) or not stream or type(position) is not int or position < 1
                        or event.get("sequence_complete") is not True):
                    held["unknown_adjacency"] += 1; continue
                here, prior = positions[(stream,position)], positions[(stream,position-1)]
                if here != {key} or len(prior) != 1:
                    held["ambiguous_or_missing_predecessor"] += 1; continue
                previous = unique.get(next(iter(prior)))
                if not previous or previous.get("kind") != "assistant_reply":
                    held["predecessor_not_reply"] += 1; continue
                if (previous.get("schema") != "witness-feedback-v1" or previous.get("sequence_complete") is not True
                        or event.get("previous_event_id") != previous["event_id"]):
                    held["unknown_adjacency"] += 1; continue
                if not direct_witness(previous):
                    held["predecessor_not_direct_witness"] += 1; continue
                predecessor_sha256 = digest(json.dumps(previous,sort_keys=True,separators=(",", ":")))
                target = targets.get(previous.get("turn_id"))
                if target is None:
                    held["target_not_eligible"] += 1; continue
                r = row_receipt(target)
                if (previous.get("content_sha256") != r["response_sha256"]
                        or previous.get("surface") != r["surface"] or event.get("surface") != r["surface"]
                        or instant(previous["at"]) != r["finalized_at"]):
                    held["target_version_surface_or_clock_mismatch"] += 1; continue
                # The owner's literal marker rule, not an emotion classifier.
                positive = bool(re.search(r"(?<!\w)(?:ha){2,}h?(?!\w)",text,re.I))
                reason = "literal_haha_marker" if positive else "no_explicit_positive_marker"
                value = None
            elif kind == "practice_rating":
                if event.get("origin") != "authenticated_owner_rating":
                    held["unknown_feedback_origin"] += 1; continue
                target = targets.get(event.get("target_turn_id"))
                if target is None:
                    held["target_not_eligible"] += 1; continue
                r = row_receipt(target)
                if (r["surface"] != "humor_practice" or event.get("surface") != r["surface"]
                        or event.get("target_sha256") != r["response_sha256"]):
                    held["practice_target_mismatch"] += 1; continue
                value = event["stars"]
                if type(value) is not int or not 1 <= value <= 5:
                    held["invalid_rating"] += 1; continue
                positive = value >= 4
                reason = "explicit_high_practice_rating" if positive else "rating_not_a_negative_label"
            else:
                held["unsupported_feedback_kind"] += 1; continue
            if not r["finalized_at"] < at:
                held["feedback_not_after_target"] += 1; continue
            observations.append({"feedback_event_id":key,"kind":kind,"at":at,
                "feedback_sha256":digest(json.dumps(event,sort_keys=True,separators=(",", ":"))),
                "predecessor_sha256":predecessor_sha256,
                "target_turn_id":r["turn_id"],"target_sha256":r["response_sha256"],
                "label":"positive" if positive else "unknown","reason":reason,"stars":value})
        except (KeyError, TypeError, ValueError, OverflowError):
            held["invalid_feedback_evidence"] += 1
    observations.sort(key=lambda r:(r["at"],r["feedback_event_id"]))
    positive_targets = {r["target_turn_id"] for r in observations if r["label"] == "positive"}
    counts = Counter((r["reason"] for r in observations))
    report = {"schema":"judges-feedback-summary-v1","observations":len(observations),
              "positive_targets":len(positive_targets),"targets_without_positive_evidence":len(targets)-len(positive_targets),
              "observation_reasons":dict(counts),"held":dict(held),
              "meaning":"explicit markers only; absence, lower ratings and missing history are unknown, never negative",
              "coverage":"producer-attested origin and adjacency; no independent authentication or complete-stream claim"}
    return report, observations

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


def context_controls(forecast, target, actual, targets, embeddings, encoder):
    """Controls from an explicit forecast-time context receipt, never guessed history.

    The receipt attests the complete assistant-reply subset of this forecast's
    context (up to six). This reader checks identities/versions and causal order;
    it cannot manufacture an upstream producer attestation from a timestamp.
    """
    unavailable = lambda reason: {"status": "unavailable", "reason": reason}
    context = forecast.get("self", {}).get("context")
    if not isinstance(context, dict):
        return unavailable("missing_context_receipt")
    try:
        if context.get("schema") != "forecast-reply-context-v1" or context.get("complete") is not True:
            return unavailable("incomplete_context_receipt")
        if context.get("scope") != "forecast_context_assistant_replies":
            return unavailable("wrong_context_scope")
        block = context.get("evaluation_block")
        if not isinstance(block, str) or not block.strip() or len(block) > 128:
            return unavailable("missing_evaluation_block")
        as_of = instant(context["as_of"])
        if as_of != instant(forecast["self"]["context_last_ts"]) or as_of >= instant(forecast["arrived_at"]):
            return unavailable("noncausal_context_receipt")
        refs = context["reply_refs"]
        if not isinstance(refs, list) or not 1 <= len(refs) <= 6:
            return unavailable("missing_or_oversized_context")
        seen, vectors, last_at = set(), [], -1.0
        for ref in refs:
            key = ref["turn_id"]
            if not isinstance(key, str) or key in seen or key == target["turn_id"]:
                return unavailable("duplicate_or_target_context")
            seen.add(key)
            previous = targets.get(key)
            if previous is None:
                return unavailable("context_reply_not_admitted")
            r = row_receipt(previous)
            if r["surface"] != row_receipt(target)["surface"]:
                return unavailable("context_surface_mismatch")
            if ref.get("response_sha256") != r["response_sha256"]:
                return unavailable("context_version_mismatch")
            at = r["finalized_at"]
            if not last_at < at <= as_of:
                return unavailable("ambiguous_or_noncausal_context_order")
            last_at = at
            matches = [e for e in embeddings[key] if e.get("encoder_id") == encoder
                       and e.get("response_sha256") == r["response_sha256"]]
            if not matches or any(e.get("emb") != matches[0].get("emb") for e in matches):
                return unavailable("missing_or_conflicting_context_embedding")
            # Python numeric equality can hide booleans behind 0/1 in a later
            # duplicate. Every matching copy must independently be a valid vector.
            for match in matches:
                cosine_error(match.get("emb"), actual)
            vector = matches[0]["emb"]
            norm = math.hypot(*vector)
            vectors.append([x / norm for x in vector])
        mean = [sum(v[i] for v in vectors) / len(vectors) for i in range(len(actual))]
        return {"status": "available", "evaluation_block": block, "context_n": len(vectors),
                "last_reply_error": cosine_error(vectors[-1], actual),
                "recent_mean_error": cosine_error(mean, actual)}
    except (KeyError, TypeError, ValueError, OverflowError):
        return unavailable("invalid_context_evidence")


MINIMUM_INNOVATION_HISTORY = 20


def innovation(admitted, forecasts, embeddings, checkpoints, minimum_history=MINIMUM_INNOVATION_HISTORY):
    """Match a pre-finalization on-message forecast to one finalized output.

    Checkpoint identities/encoder/training times must come from an independently
    retained manifest. Historical forecast logs alone cannot prove these facts.
    Percentiles use outcomes finalized strictly before the forecast was made,
    within the same checkpoint and observed target-generator group.
    """
    if minimum_history < 1:
        raise ValueError("history minimum must be positive")
    if not isinstance(forecasts, list) or not isinstance(embeddings, list) or not isinstance(checkpoints, dict):
        raise ValueError("forecast/embedding lists and checkpoint mapping required")
    targets = {r["turn_id"]: r for r in admitted}
    cache = defaultdict(list)
    held, candidates = Counter(), defaultdict(list)
    for e in embeddings:
        if not isinstance(e, dict) or not isinstance(e.get("turn_id"), str) or not e["turn_id"]:
            held["missing_embedding_identity"] += 1
            continue
        # Keep identifiable malformed copies: dropping them could hide a
        # conflicting vector behind a valid copy for the same target/version.
        cache[e["turn_id"]].append(e)
    for f in forecasts:
        try:
            if not isinstance(f, dict):
                raise ValueError("forecast must be a record")
            row = targets.get(f.get("turn_id"))
            if row is None:
                held["no_eligible_final_reply"] += 1
                continue
            r, head = row_receipt(row), f["self"]
            if not isinstance(head, dict):
                raise ValueError("forecast head must be a record")
            if f.get("mode") != "on_message" or head.get("mode") != "on_message":
                held["wrong_mode"] += 1
                continue
            if f.get("surface") != r["surface"]:
                held["wrong_surface"] += 1
                continue
            checkpoint = head["checkpoint_id"]
            if not isinstance(checkpoint, str) or not checkpoint:
                raise ValueError("checkpoint identity must be explicit")
            manifest = checkpoints[checkpoint]
            if not isinstance(manifest, dict):
                raise ValueError("checkpoint manifest must be a record")
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
            # Validate all copies before selecting one; equality alone does not
            # establish numeric validity (True == 1 and False == 0).
            errors = [cosine_error(head["emb"], match.get("emb")) for match in matches]
            error = errors[0]
            selected = next(a for a in r["generation"]["attempts"] if a["outcome"] == "selected")
            if not selected.get("served_model") or selected.get("identity_evidence") == "unknown":
                held["unknown_target_generator"] += 1
                continue
            group = (checkpoint, encoder, r["surface"], "on_message", head["source"],
                     selected["served_model"], selected.get("served_revision") or "")
            # Equal errors are not equal forecasts. Retain a private digest of
            # the complete producer record, including vector and context claims.
            forecast_sha = digest(json.dumps(f, sort_keys=True, separators=(",", ":"), allow_nan=False))
            candidates[(row["turn_id"], group)].append({
                "turn_id": row["turn_id"], "response_sha256": r["response_sha256"],
                "group": group, "forecast_at": made, "forecast_sha256": forecast_sha, "finalized_at": r["finalized_at"],
                "error": error,
                "controls": context_controls(f, row, matches[0]["emb"], targets, cache, encoder)})
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
        prior = [r["error"] for r in histories[group] if r["finalized_at"] < row["forecast_at"]]
        row["prior_n"] = len(prior)
        row["innovation_percentile"] = (
            100 * sum((v < row["error"]) + .5 * (v == row["error"]) for v in prior) / len(prior)
            if len(prior) >= minimum_history else None)
        histories[group].append(row)
    # Never pool checkpoints, surfaces or observed target generators into one claim.
    aggregate = []
    for group, rows in histories.items():
        aggregate.append({"checkpoint_group": len(aggregate) + 1, "n": len(rows),
                          "mean_cosine_error": statistics.mean(r["error"] for r in rows),
                          "percentiles_available": sum(r["innovation_percentile"] is not None for r in rows)})
    paired, control_held = defaultdict(list), Counter()
    for row in scored:
        controls = row["controls"]
        if controls["status"] != "available":
            control_held[controls["reason"]] += 1
            continue
        paired[(tuple(row["group"]), controls["evaluation_block"])].append(row)
        controls["last_reply_improvement"] = controls["last_reply_error"] - row["error"]
        controls["recent_mean_improvement"] = controls["recent_mean_error"] - row["error"]
    comparisons = []
    group_numbers = {group: i + 1 for i, group in enumerate(histories)}
    for (group, block), rows in paired.items():
        # Pair all three scores on exactly the same targets; never mix blocks.
        comparisons.append({"comparison_group": len(comparisons) + 1,
            "checkpoint_group": group_numbers[group], "n": len(rows),
            "paired_head_mean_error": statistics.mean(r["error"] for r in rows),
            **{key: statistics.mean(r["controls"][key] for r in rows) for key in (
                "last_reply_error", "recent_mean_error", "last_reply_improvement", "recent_mean_improvement")}})
    return {"groups": aggregate, "held": dict(held),
            "baselines": {"paired_groups": comparisons, "unavailable": dict(control_held),
                          "meaning": "positive improvement favours head; descriptive paired errors, not a pass verdict"},
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


# The local scoring implementation, not provider dependencies or live stores.
SCORING_FILES = ("experiments/judges-witness/replay.py", "scripts/witness_receipts.py",
                 "scripts/evidence_provenance.py", "scripts/evidence_view.py")


def scoring_hashes():
    repo = Path(__file__).resolve().parents[2]
    return {name: hashlib.sha256((repo / name).read_bytes()).hexdigest() for name in SCORING_FILES}


def run_manifest(source_bytes, code, options, outputs):
    """Private reproducibility receipt; fingerprints do not authenticate a source."""
    body = {"schema": "judges-replay-run-v1", "input_sha256": hashlib.sha256(source_bytes).hexdigest(),
            "input_bytes": len(source_bytes), "scoring_files": code, "options": options,
            "outputs": outputs, "python_version": list(sys.version_info[:3]),
            "python_implementation": sys.implementation.name}
    return dict(body, run_sha256=digest(json.dumps(body, sort_keys=True, separators=(",", ":"), allow_nan=False)))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--scratch", required=True)
    p.add_argument("--input", required=True, help="explicit synthetic or admitted snapshot bundle JSON")
    p.add_argument("--output", required=True, help="new private output directory")
    p.add_argument("--cutoff", required=True, help="exclusive timestamp with explicit timezone")
    p.add_argument("--behaviour-start", help="inclusive window start with timezone; requires --behaviour-surface")
    p.add_argument("--behaviour-surface", action="append", default=[], help="explicit surface to summarize; repeatable")
    args = p.parse_args()
    if bool(args.behaviour_start) != bool(args.behaviour_surface):
        p.error("behaviour start and surface scope must be supplied together")
    root = scratch_root(args.scratch)
    source, output = inside(root, args.input), inside(root, args.output)
    if output.exists() or output in source.parents:
        raise ValueError("output must be new and cannot contain input")
    install_guard(root, output)
    code_hashes = scoring_hashes()
    source_bytes = source.read_bytes()
    bundle = json.loads(source_bytes)
    if bundle.get("input_kind") not in ("synthetic", "retained_snapshot"):
        raise ValueError("input_kind must explicitly distinguish synthetic from retained_snapshot")
    # No discovery or historical fallback. Missing components are explicit empty evidence.
    sources = [(s["kind"], s["rows"]) for s in bundle.get("sources", [])]
    nodes = snapshot_nodes(sources, bundle.get("lineage", []))
    summary, admitted = census(sources, nodes, instant(args.cutoff))
    scores, details = innovation(admitted, bundle.get("forecasts", []),
                                 bundle.get("embeddings", []), bundle.get("checkpoints", {}))
    behaviour = {"status":"not_configured", "meaning":"explicit window and surface scope required"}
    private_behaviour = None
    if args.behaviour_start:
        behaviour, private_behaviour = behaviour_receipt(admitted, args.behaviour_start, args.cutoff, args.behaviour_surface,
            digest(json.dumps(bundle, sort_keys=True, separators=(",", ":"))))
    feedback, private_feedback = feedback_receipts(admitted, bundle.get("feedback_events", []), args.cutoff)
    report = {"schema": "judges-shadow-v1", "input_kind": bundle.get("input_kind", "unspecified"),
              "census": summary, "innovation": scores, "behaviour_receipt":behaviour, "feedback":feedback}
    if scoring_hashes() != code_hashes:
        raise ValueError("scoring source changed during replay")
    output.mkdir(mode=0o700)
    outputs = [("aggregate.json", report), ("private-innovation.json", details),
               ("private-feedback.json", private_feedback)]
    if private_behaviour is not None:
        outputs.append(("private-behaviour.json", private_behaviour))
    output_hashes = {}
    for name, value in outputs:
        payload = (json.dumps(value, indent=2, allow_nan=False) + "\n").encode("utf-8")
        with (output / name).open("xb") as f:
            os.chmod(f.name, 0o600)
            f.write(payload)
        output_hashes[name] = {"sha256": hashlib.sha256(payload).hexdigest(), "bytes": len(payload)}
    manifest = run_manifest(source_bytes, code_hashes,
        {"input_kind": bundle["input_kind"], "cutoff": instant(args.cutoff),
         "behaviour_start": instant(args.behaviour_start) if args.behaviour_start else None,
         "behaviour_surfaces": sorted(set(args.behaviour_surface)), "minimum_innovation_history": MINIMUM_INNOVATION_HISTORY}, output_hashes)
    # Written last. Missing, partial or mismatching receipts cannot establish a complete run.
    with (output / "private-run.json").open("x") as f:
        os.chmod(f.name, 0o600)
        json.dump(manifest, f, indent=2, allow_nan=False)
        f.write("\n")
    print(json.dumps({"eligible_replies": len(admitted), "forecast_groups": len(scores["groups"])}))


if __name__ == "__main__":
    main()
