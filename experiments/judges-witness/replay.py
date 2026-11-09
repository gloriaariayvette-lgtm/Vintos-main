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
from witness_receipts import admission, digest, envelope_status, instant, row_receipt, joined_identity, final_response, normalize_receipt, lineage_status, final_reply_status


def value_map_write_observations(nodes, builds, cutoff):
    """Compare supplied write observations, never infer origin or add ancestry.

    Locator plus full entry content is necessary for this comparison, but does
    not identify a writer. Copies, missing writers and reused paths remain
    possible. Keep every causal match; never prefer the nearest or latest one.
    This does not validate model-call provenance or affect witness admission.
    """
    cutoff = instant(cutoff)
    if not isinstance(builds, list):
        raise ValueError("value-map builds must be a list")
    versions, index = {}, defaultdict(list)
    legacy = 0

    def hashed(value):
        return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None

    for build in builds:
        if not isinstance(build, dict) or not isinstance(build.get("build_id"), str) or not build["build_id"]:
            raise ValueError("invalid value-map build identity")
        try:
            version = json.dumps(build, sort_keys=True, separators=(",", ":"), allow_nan=False)
        except (TypeError, ValueError):
            raise ValueError("invalid value-map build record") from None
        key = build["build_id"]
        if key in versions:
            if versions[key] != version:
                raise ValueError("conflicting value-map build identity")
            continue
        versions[key] = version
        write = build.get("write")
        schema = build.get("schema")
        try:
            start, end = instant(build.get("started_at")), instant(build.get("ended_at"))
        except (TypeError, ValueError, OverflowError):
            raise ValueError("invalid value-map build clock") from None
        if (schema not in ("value-map-build-v1", "value-map-build-v2") or start > end
                or build.get("upstream_complete") is not False
                or build.get("attempt_coverage_complete") is not False
                or not isinstance(write, dict) or write.get("scope") != "entry_write_closed"
                or write.get("mode") not in ("append", "replace")
                or write.get("durability") != "unconfirmed" or write.get("whole_file") != "unverified"
                or not hashed(write.get("entry_sha256")) or not hashed(write.get("stripped_entry_sha256"))
                or type(write.get("entry_chars")) is not int or not 0 < write["entry_chars"] <= 4194304
                or (schema == "value-map-build-v2" and not hashed(write.get("resource_sha256")))):
            raise ValueError("invalid value-map write observation")
        if schema == "value-map-build-v1":
            legacy += 1
        elif end < cutoff:
            index[(write["resource_sha256"], write["stripped_entry_sha256"])].append((end, key))
    states, details = Counter(), []
    for key, node in sorted(nodes.items()):
        if node.get("observation") != "value_map_read":
            continue
        candidates = []
        try:
            at = instant(node.get("at"))
        except (TypeError, ValueError, OverflowError):
            raise ValueError("invalid value-map read clock") from None
        if at >= cutoff:
            state = "outside_cutoff"
        elif not all(hashed(node.get(field)) for field in ("resource_sha256", "stripped_entry_sha256")):
            state = "read_identity_unavailable"
        else:
            candidates = sorted(build_id for ended, build_id in
                index[(node["resource_sha256"], node["stripped_entry_sha256"])] if ended <= at)
            state = ("no_matching_write" if not candidates else
                     "one_matching_write" if len(candidates) == 1 else "multiple_matching_writes")
        states[state] += 1
        details.append({"read_node_id": key, "state": state, "candidate_build_ids": candidates})
    return ({"scope": "matching_write_observations_not_origin", "admission_effect": "none",
             "unique_builds": len(versions), "builds_without_resource_identity": legacy,
             "reads": len(details), "states": dict(sorted(states.items()))}, details)


def value_map_build_links(builds, calls, cutoff):
    """Check explicit supplied IDs and hashes only; never grant clean ancestry."""
    def clock(value):
        try:
            return instant(value)
        except (TypeError, ValueError, OverflowError):
            raise ValueError("invalid producer clock") from None

    cutoff = clock(cutoff)
    # Reuse write-receipt validation, including conflicting duplicate identities.
    value_map_write_observations({}, builds, cutoff)

    def index(records, field):
        if not isinstance(records, list):
            raise ValueError("producer records must be a list")
        result, versions = {}, {}
        for rec in records:
            if not isinstance(rec, dict) or not isinstance(rec.get(field), str) or not 0 < len(rec[field]) <= 256:
                raise ValueError("invalid producer identity")
            try:
                encoded = json.dumps(rec, sort_keys=True, separators=(",", ":"), allow_nan=False)
            except (TypeError, ValueError):
                raise ValueError("invalid producer record") from None
            key = rec[field]
            if key in versions and versions[key] != encoded:
                raise ValueError("conflicting producer identity")
            versions[key], result[key] = encoded, rec
        return result

    def hashed(value):
        return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None

    stages = ("draft_a", "draft_b", "synthesis")
    def reference(ref):
        if (not isinstance(ref, dict) or set(ref) != {"stage", "state", "request_id", "returned_sha256"}
                or ref.get("stage") not in stages or not hashed(ref.get("returned_sha256"))
                or ref.get("state") not in ("bound", "unavailable")
                or (ref["state"] == "unavailable" and ref.get("request_id") is not None)
                or (ref["state"] == "bound" and (not isinstance(ref.get("request_id"), str) or not 0 < len(ref["request_id"]) <= 256))):
            raise ValueError("invalid producer reference")

    by_build, by_call = index(builds, "build_id"), index(calls, "request_id")
    for call in by_call.values():
        start, end = clock(call.get("started_at")), clock(call.get("ended_at"))
        if (call.get("schema") != "value-map-call-v1" or start > end
                or call.get("scope") != "one_http_invocation" or not hashed(call.get("input_sha256"))
                or call.get("upstream_complete") is not False or call.get("internal_attempts_complete") is not False
                or call.get("outcome") not in ("returned", "rejected", "failed")
                or (call["outcome"] == "returned" and not hashed(call.get("returned_sha256")))
                or (call["outcome"] != "returned" and call.get("returned_sha256") is not None)):
            raise ValueError("invalid completed producer call")
        if "build_id" in call:
            deps = call.get("dependencies")
            if (not isinstance(call["build_id"], str) or not call["build_id"] or call.get("stage") not in stages
                    or not isinstance(deps, list) or len(deps) > 2):
                raise ValueError("invalid producer call binding")
            for dep in deps: reference(dep)
            if sorted(d["stage"] for d in deps) != (["draft_a", "draft_b"] if call["stage"] == "synthesis" else []):
                raise ValueError("invalid producer dependency stages")
    for build in by_build.values():
        reference(build.get("selection"))
        records, entries = build.get("calls"), build.get("stage_entries")
        if (type(build.get("calls_truncated")) is not bool or not isinstance(records, list) or len(records) > 8
                or not isinstance(entries, dict) or any(k not in stages or type(v) is not int or v < 1 for k,v in entries.items())):
            raise ValueError("invalid producer build observations")
        ids = set()
        for rec in records:
            if (not isinstance(rec, dict) or not isinstance(rec.get("request_id"), str) or not rec["request_id"]
                    or rec["request_id"] in ids or rec.get("stage") not in stages
                    or type(rec.get("packet_published")) is not bool
                    or rec.get("outcome") not in ("returned", "rejected", "failed", "unobserved")):
                raise ValueError("invalid producer call observation")
            ids.add(rec["request_id"])

    stage_calls = defaultdict(list)
    for call in by_call.values():
        if "build_id" in call:
            stage_calls[(call["build_id"], call["stage"])].append(call)

    def check(build, ref, latest):
        if ref["state"] != "bound":
            return "unavailable"
        call = by_call.get(ref["request_id"])
        if call is None:
            return "missing_call"
        records = [r for r in build["calls"] if r["stage"] == ref["stage"]]
        # Also inspect supplied calls omitted by the build's call summary. Never
        # let an incomplete summary select one of several same-stage attempts.
        supplied = stage_calls[(build["build_id"], ref["stage"])]
        good = (not build["calls_truncated"] and build["stage_entries"].get(ref["stage"]) == 1
                and len(records) == 1 and len(supplied) == 1
                and records[0]["request_id"] == ref["request_id"]
                and records[0]["packet_published"] is True and records[0]["outcome"] == "returned"
                and call.get("build_id") == build["build_id"] and call.get("stage") == ref["stage"]
                and call["outcome"] == "returned" and call["returned_sha256"] == ref["returned_sha256"]
                and clock(build["started_at"]) <= clock(call["started_at"]) <= clock(call["ended_at"]) <= latest
                and clock(call["ended_at"]) < cutoff)
        return "consistent" if good else "inconsistent_call"

    # Count the explicit response identity separately from link consistency.
    # Configuration, text hashes and shared build IDs never supply identity.
    identities = Counter()
    for call in by_call.values():
        if clock(call["ended_at"]) >= cutoff:
            continue
        if "served_model" not in call and "identity_evidence" not in call:
            state = "missing"
        elif "served_model" not in call or "identity_evidence" not in call:
            state = "malformed"
        elif call["identity_evidence"] == "unknown" and call["served_model"] is None:
            state = "unknown"
        elif (call["outcome"] == "returned" and call["identity_evidence"] == "response_metadata"
              and isinstance(call["served_model"], str) and call["served_model"].strip()
              and len(call["served_model"]) <= 256 and hashed(call.get("response_sha256"))):
            state = "response_reported"
        else:
            state = "malformed"
        identities[state] += 1

    selections, dependencies, details = Counter(), Counter(), []
    for key, build in sorted(by_build.items()):
        if clock(build["ended_at"]) >= cutoff:
            continue
        ref = build["selection"]
        state = check(build, ref, clock(build["ended_at"]))
        selections[state] += 1
        detail = {"build_id": key, "selected_request_id": ref["request_id"], "selection_state": state, "dependencies": []}
        if state == "consistent":
            call = by_call[ref["request_id"]]
            for dep in call.get("dependencies", []):
                status = check(build, dep, clock(call["started_at"]))
                dependencies[status] += 1
                detail["dependencies"].append({"stage": dep["stage"], "request_id": dep["request_id"], "state": status})
        details.append(detail)
    return ({"scope": "explicit_build_call_consistency_only", "admission_effect": "none",
             "builds_before_cutoff": len(details),
             "calls_before_cutoff": sum(clock(c["ended_at"]) < cutoff for c in by_call.values()),
             "call_identity_coverage": dict(sorted(identities.items())),
             "selection_states": dict(sorted(selections.items())), "dependency_states": dict(sorted(dependencies.items()))}, details)


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
        if key in nodes:
            # Dictionary equality aliases true/1 and false/0, although the
            # lineage contract requires explicit booleans. Compare the complete
            # JSON attestations without allowing the last copy to pick a type.
            if (not repeated or
                    json.dumps(nodes[key], sort_keys=True, separators=(",", ":"), allow_nan=False) !=
                    json.dumps(node, sort_keys=True, separators=(",", ":"), allow_nan=False)):
                raise ValueError("duplicate or conflicting lineage identity")
            return
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


def evidence_coverage(row, nodes):
    """Independent per-copy coverage, never an admission or completeness verdict.

    An early delivery hold must not conceal missing ancestry or request binding.
    Conflicting receipts contribute no selected facts. Recorded facts on excluded
    acts remain coverage observations, not evidence eligible for learning.
    """
    candidates = [row["witness_receipt"]] if "witness_receipt" in row else []
    candidates += [row[k]["witness_receipt"] for k in ("generation_provenance", "provenance")
                   if isinstance(row.get(k), dict) and "witness_receipt" in row[k]]
    receipts = [normalize_receipt(r) for r in candidates]
    status = ("absent" if not receipts else "conflicting" if any(r != receipts[0] for r in receipts)
              else "recorded" if receipts[0]["status"] == "recorded" else "unknown")
    result = dict.fromkeys(("identity_binding", "served_identity", "request_binding",
                           "delivery", "response_binding", "context_lineage", "final_reply_lineage"), "not_evaluated")
    result["receipt"] = status
    if status != "recorded":
        return result
    r = receipts[0]
    selected = next(a for a in r["generation"]["attempts"] if a["outcome"] == "selected")
    identity, _ = joined_identity(row)
    text = final_response(row)
    result.update(
        identity_binding="matched" if identity == r["turn_id"] and row.get("surface") == r["surface"] else "mismatch",
        served_identity="observed" if selected["served_model"] is not None else "unknown",
        request_binding="recorded" if selected.get("request_id") and selected.get("input_sha256") else "unknown",
        delivery=r["delivery"],
        response_binding="matched" if isinstance(text, str) and digest(text) == r["response_sha256"] else "missing_or_changed",
        context_lineage=lineage_status(r["context_receipt_id"], nodes, r["started_at"]),
        final_reply_lineage=final_reply_status(row, nodes, r) if "reply_node" in row else "not_supplied")
    return result


def census(sources, nodes, cutoff):
    groups, reasons, envelopes = defaultdict(list), Counter(), Counter()
    source_counts, identity_joins, duplicate_reasons = {}, 0, Counter()
    coverage, coverage_n = defaultdict(Counter), 0
    for kind, rows in sources:
        adapted = list(adapt(rows, kind))
        source_counts[kind] = source_counts.get(kind, 0) + len(adapted)
        for row in adapted:
            if row.get("role") != "assistant":
                reasons["not_reply"] += 1
                continue
            coverage_n += 1
            for field, status in evidence_coverage(row, nodes).items():
                coverage[field][status] += 1
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
               "envelope_id_joins": identity_joins,
               "evidence_coverage": {"assistant_copies": coverage_n,
                   "fields": {k: dict(v) for k, v in sorted(coverage.items())},
                   "meaning": "per-copy independent coverage, including excluded acts; not eligibility or complete-stream proof"},
               "behaviour": {
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
        try:
            # Numeric equality aliases explicit booleans and integer ratings.
            # Select only identical JSON attestations, independent of input order.
            versions = {json.dumps(r, sort_keys=True, separators=(",", ":"), allow_nan=False)
                        for r in rows}
        except (TypeError, ValueError, OverflowError):
            held["invalid_feedback_evidence"] += 1
            continue
        if len(versions) != 1:
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
    held, candidates, declared = Counter(), defaultdict(list), defaultdict(list)
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
            selected = next(a for a in r["generation"]["attempts"] if a["outcome"] == "selected")
            if not selected.get("served_model") or selected.get("identity_evidence") == "unknown":
                held["unknown_target_generator"] += 1
                continue
            group = (checkpoint, encoder, r["surface"], "on_message", head["source"],
                     selected["served_model"], selected.get("served_revision") or "")
            # Establish ordering from identified producer records before any
            # vector/causality filtering can discard the earliest prediction.
            claim = {"at": None, "sha256": None}
            declared[(row["turn_id"], group)].append(claim)
            claim["at"] = made = instant(f["ts"])
            claim["sha256"] = digest(json.dumps(f, sort_keys=True, separators=(",", ":"), allow_nan=False))
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
            # Equal errors are not equal forecasts. Retain a private digest of
            # the complete producer record, including vector and context claims.
            forecast_sha = claim["sha256"]
            candidates[(row["turn_id"], group)].append({
                "turn_id": row["turn_id"], "response_sha256": r["response_sha256"],
                "group": group, "forecast_at": made, "forecast_sha256": forecast_sha, "finalized_at": r["finalized_at"],
                "error": error,
                "controls": context_controls(f, row, matches[0]["emb"], targets, cache, encoder)})
        except (KeyError, TypeError, ValueError, OverflowError):
            held["missing_or_invalid_forecast_evidence"] += 1
    scored = []
    for key, choices in candidates.items():
        claims = declared[key]
        if any(c["at"] is None for c in claims):
            held["unknown_forecast_order"] += 1
            continue
        earliest = min(c["at"] for c in claims)
        first_claims = [c for c in claims if c["at"] == earliest]
        if any(c["sha256"] is None for c in first_claims):
            held["unscorable_earliest_forecast"] += 1
            continue
        if len({c["sha256"] for c in first_claims}) != 1:
            held["conflicting_forecast"] += 1
            continue
        tied = [c for c in choices if c["forecast_at"] == earliest]
        if not tied:
            held["unscorable_earliest_forecast"] += 1
            continue
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


def self_input_baselines(scored, admitted, forecasts, target_embeddings, config, cutoff):
    """Optional descriptive controls for exact producer-observed excerpt inputs.

    No admission changes or text/time-nearest joins. This first version accepts
    only inputs whose normalized full text equals an already admitted final reply.
    Source normalization that changed bytes requires separate evidence, not a guess.
    """
    cutoff = instant(cutoff)
    invalid = lambda: ValueError("invalid self-input baseline evidence")
    def canonical(value):
        try:
            return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
        except (TypeError, ValueError, OverflowError):
            raise invalid() from None
    def hashed(value):
        return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None
    def named(value):
        return isinstance(value, str) and bool(value.strip()) and len(value) <= 256
    if (not isinstance(config, dict) or set(config) != {"receipts", "embeddings", "blocks"}
            or any(not isinstance(config[k], list) for k in config)):
        raise invalid()
    packets, versions = {}, {}
    for packet in config["receipts"]:
        try:
            if (not isinstance(packet, dict) or set(packet) != {"schema", "forecast_row_sha256", "forecast_at",
                    "arrived_at", "boundary", "durability", "observations", "state", "inputs", "complete_forecast_context"}
                    or packet["schema"] != "self-forecast-inputs-v1" or not hashed(packet["forecast_row_sha256"])
                    or packet["boundary"] != "forecast_log_close" or packet["durability"] != "unconfirmed"
                    or packet["complete_forecast_context"] is not False
                    or type(packet["observations"]) is not int or packet["observations"] < 0
                    or packet["state"] not in ("observed", "unavailable")
                    or instant(packet["arrived_at"]) > instant(packet["forecast_at"])):
                raise invalid()
            inputs = packet["inputs"]
            if packet["state"] == "unavailable":
                if inputs is not None: raise invalid()
            else:
                if (packet["observations"] != 1 or not isinstance(inputs, dict)
                        or set(inputs) != {"scope", "as_of_exchange_at", "transform", "selection", "reply_refs",
                                           "source_identity", "encoder_identity", "upstream_complete", "complete_forecast_context"}
                        or inputs["scope"] != "recent_own_reply_feature_inputs"
                        or inputs["transform"] != "normalized_exchange_his_first_400_codepoints"
                        or inputs["selection"] != "last_six_nonempty_his_in_supplied_exchange_order"
                        or inputs["source_identity"] != "unverified" or inputs["encoder_identity"] != "unobserved"
                        or inputs["upstream_complete"] is not False or inputs["complete_forecast_context"] is not False
                        or instant(inputs["as_of_exchange_at"]) >= instant(packet["arrived_at"])
                        or not isinstance(inputs["reply_refs"], list) or not 1 <= len(inputs["reply_refs"]) <= 6):
                    raise invalid()
                for ref in inputs["reply_refs"]:
                    if (not isinstance(ref, dict) or set(ref) != {"observed_turn_id", "exchange_at", "normalized_reply_sha256",
                                                               "encoder_input_sha256", "encoder_input_chars"}
                            or ref["observed_turn_id"] is not None and not named(ref["observed_turn_id"])
                            or not hashed(ref["normalized_reply_sha256"]) or not hashed(ref["encoder_input_sha256"])
                            or type(ref["encoder_input_chars"]) is not int or not 1 <= ref["encoder_input_chars"] <= 400
                            or instant(ref["exchange_at"]) > instant(inputs["as_of_exchange_at"])):
                        raise invalid()
            key, version = packet["forecast_row_sha256"], canonical(packet)
            if key in versions and versions[key] != version: raise invalid()
            versions[key] = version
            packets[key] = packet
        except (KeyError, TypeError, ValueError, OverflowError):
            raise invalid() from None
    blocks, block_versions = [], {}
    for block in config["blocks"]:
        try:
            if (not isinstance(block, dict) or set(block) != {"block_id", "declared_at", "start", "end"}
                    or not named(block["block_id"])
                    or not instant(block["declared_at"]) < instant(block["start"]) < instant(block["end"])):
                raise invalid()
            key, version = block["block_id"], canonical(block)
            if key in block_versions:
                if block_versions[key] != version: raise invalid()
                continue
            block_versions[key] = version
            blocks.append(block)
        except (KeyError, TypeError, ValueError, OverflowError):
            raise invalid() from None
    blocks.sort(key=lambda b: instant(b["start"]))
    if any(instant(a["end"]) > instant(b["start"]) for a, b in zip(blocks, blocks[1:])):
        raise invalid()
    # Retain malformed identifiable cache copies so they cannot hide behind valid ones.
    cache = defaultdict(list)
    for entry in config["embeddings"]:
        if not isinstance(entry, dict) or not named(entry.get("turn_id")):
            raise invalid()
        cache[entry["turn_id"]].append(entry)
    originals = {digest(canonical(f)): f for f in forecasts}
    targets = {r["turn_id"]: r for r in admitted}
    held, paired, details = Counter(), defaultdict(list), []
    for score in scored:
        key = score["forecast_sha256"]
        result = {"forecast_sha256": key, "turn_id": score["turn_id"], "status": "unavailable"}
        def hold(reason):
            result["reason"] = reason
            held[reason] += 1
            details.append(result)
        if instant(score["finalized_at"]) >= cutoff:
            hold("outside_cutoff"); continue
        f, packet = originals.get(key), packets.get(key)
        if f is None or packet is None:
            hold("missing_exact_forecast_receipt"); continue
        if (instant(packet["forecast_at"]) != instant(f["ts"])
                or instant(packet["arrived_at"]) != instant(f["arrived_at"])):
            hold("forecast_clock_mismatch"); continue
        if packet["state"] != "observed":
            hold("producer_inputs_unavailable"); continue
        inputs = packet["inputs"]
        as_of = instant(inputs["as_of_exchange_at"])
        if as_of != instant(f["self"]["context_last_ts"]):
            hold("context_clock_mismatch"); continue
        matched_blocks = [b for b in blocks if instant(b["start"]) <= instant(f["arrived_at"])
                          and instant(score["finalized_at"]) < instant(b["end"]) <= cutoff]
        if len(matched_blocks) != 1:
            hold("missing_complete_declared_block"); continue
        block = matched_blocks[0]
        vectors, seen, last_final = [], set(), -1.
        reason = None
        for ref in inputs["reply_refs"]:
            prior_id = ref["observed_turn_id"]
            if prior_id is None or prior_id in seen or prior_id == score["turn_id"]:
                reason = "missing_duplicate_or_target_input_identity"; break
            seen.add(prior_id)
            previous = targets.get(prior_id)
            if previous is None:
                reason = "input_reply_not_admitted"; break
            r, text = row_receipt(previous), final_response(previous)
            if r["surface"] != score["group"][2]:
                reason = "input_surface_mismatch"; break
            # A matching normalized hash is accepted only when no normalization changed the final bytes.
            if digest(text) != ref["normalized_reply_sha256"] or digest(text) != r["response_sha256"]:
                reason = "unverified_normalized_reply_version"; break
            prefix = text[:400]
            if digest(prefix) != ref["encoder_input_sha256"] or len(prefix) != ref["encoder_input_chars"]:
                reason = "input_transform_mismatch"; break
            if not last_final < r["finalized_at"] <= as_of:
                reason = "noncausal_or_ambiguous_input_order"; break
            last_final = r["finalized_at"]
            encoder = score["group"][1]
            matches = [e for e in cache[prior_id] if e.get("encoder_id") == encoder
                       and e.get("response_sha256") == r["response_sha256"]
                       and e.get("encoder_input_sha256") == ref["encoder_input_sha256"]]
            try:
                if not matches or any(e.get("emb") != matches[0].get("emb") for e in matches):
                    raise ValueError()
                for entry in matches:
                    if entry.get("transform") != "final_reply_first_400_codepoints": raise ValueError()
                    cosine_error(entry.get("emb"), f["self"]["emb"])
                vector = matches[0]["emb"]
                norm = math.hypot(*vector)
                vectors.append([x / norm for x in vector])
            except (TypeError, ValueError, OverflowError):
                reason = "missing_or_invalid_input_embedding"; break
        if reason:
            hold(reason); continue
        # Reuse the same full-target cache supplied to innovation(), not a second
        # vector inferred from an equal scalar error or the excerpt cache.
        actual_entries = [e for e in target_embeddings if isinstance(e, dict)
                          and e.get("turn_id") == score["turn_id"] and e.get("encoder_id") == score["group"][1]
                          and e.get("response_sha256") == score["response_sha256"]]
        try:
            if not actual_entries or any(e.get("emb") != actual_entries[0].get("emb") for e in actual_entries):
                raise ValueError()
            for entry in actual_entries:
                if cosine_error(f["self"]["emb"], entry.get("emb")) != score["error"]: raise ValueError()
            actual = actual_entries[0]["emb"]
        except (TypeError, ValueError, OverflowError):
            hold("missing_or_conflicting_actual_embedding"); continue
        try:
            mean = [sum(v[i] for v in vectors) / len(vectors) for i in range(len(actual))]
            last_error, mean_error = cosine_error(vectors[-1], actual), cosine_error(mean, actual)
        except (TypeError, ValueError, OverflowError, IndexError):
            hold("invalid_control_geometry"); continue
        result.update(status="available", evaluation_block=block["block_id"], context_n=len(vectors),
                      head_error=score["error"], last_reply_error=last_error, recent_mean_error=mean_error,
                      last_reply_improvement=last_error-score["error"], recent_mean_improvement=mean_error-score["error"])
        details.append(result)
        paired[(tuple(score["group"]), block["block_id"])].append(result)
    comparisons = []
    group_numbers = {group: i + 1 for i, group in enumerate(dict.fromkeys(tuple(s["group"]) for s in scored))}
    for (group, block), rows in paired.items():
        comparisons.append({"comparison_group": len(comparisons)+1, "checkpoint_group": group_numbers[group], "n": len(rows),
                            **{k: statistics.mean(r[k] for r in rows) for k in
                               ("head_error", "last_reply_error", "recent_mean_error", "last_reply_improvement", "recent_mean_improvement")}})
    return {"paired_groups": comparisons, "unavailable": dict(held), "admission_effect": "none",
            "meaning": "descriptive paired excerpt-input controls; supplied block declarations, not verified preregistration or a pass verdict"}, details


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


def decode_snapshot(raw):
    """Reject contradictory JSON before a parser can discard an evidence field."""
    def object_pairs(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                # Keys may themselves contain private data. Never echo one.
                raise ValueError("duplicate JSON object key")
            result[key] = value
        return result

    def nonfinite(_value):
        raise ValueError("nonfinite JSON constant")

    def finite_float(token):
        value = float(token)
        if not math.isfinite(value):
            raise ValueError("nonfinite JSON constant")
        return value

    value = json.loads(raw, object_pairs_hook=object_pairs, parse_constant=nonfinite,
                       parse_float=finite_float)
    if not isinstance(value, dict):
        raise ValueError("snapshot must be a JSON object")
    return value


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
    bundle = decode_snapshot(source_bytes)
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
    private_self_inputs = None
    if "self_input_controls" in bundle:
        report["self_input_baselines"], private_self_inputs = self_input_baselines(
            details, admitted, bundle.get("forecasts", []), bundle.get("embeddings", []),
            bundle["self_input_controls"], args.cutoff)
    private_map_writes = None
    if "value_map_builds" in bundle:
        report["value_map_write_observations"], private_map_writes = value_map_write_observations(
            nodes, bundle["value_map_builds"], args.cutoff)
    private_build_links = None
    if "value_map_calls" in bundle:
        if "value_map_builds" not in bundle:
            raise ValueError("value_map_calls requires an explicit value_map_builds list")
        report["value_map_build_links"], private_build_links = value_map_build_links(
            bundle["value_map_builds"], bundle["value_map_calls"], args.cutoff)
    if scoring_hashes() != code_hashes:
        raise ValueError("scoring source changed during replay")
    output.mkdir(mode=0o700)
    outputs = [("aggregate.json", report), ("private-innovation.json", details),
               ("private-feedback.json", private_feedback)]
    if private_self_inputs is not None:
        outputs.append(("private-self-input-controls.json", private_self_inputs))
    if private_behaviour is not None:
        outputs.append(("private-behaviour.json", private_behaviour))
    if private_map_writes is not None:
        outputs.append(("private-value-map-writes.json", private_map_writes))
    if private_build_links is not None:
        outputs.append(("private-value-map-links.json", private_build_links))
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
