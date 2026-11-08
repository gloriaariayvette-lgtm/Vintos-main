"""Pure contracts for the shadow behaviour witness; no I/O or implicit admission.

This instrument does not change legacy evidence eligibility or any live feed.
Receipt producers must supply observed facts; configured models are not served models.
"""
import hashlib
import math
from datetime import datetime

SCHEMA = "behaviour-witness-v1"
INFLUENCING = frozenset(("character_score", "behaviour_receipt", "judge_effect",
                         "tactical", "emotion_nudge"))
KINDS = INFLUENCING | frozenset(("context", "value_map", "ordinary_source", "reply"))
# Only external input or operator configuration may terminate ancestry. Generated
# material must retain its dependency graph, even when it has no influence marker.
SOURCE_ORIGINS = frozenset(("counterpart_verbatim", "sensor_observation", "operator_configuration"))


def digest(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def source_node(node_id, origin, at, content):
    """A producer-attested external leaf, bound to the exact version it read.

    This does not authenticate a producer or infer origin from content. Callers
    must know the source; generated and legacy unknown material cannot use it.
    """
    if not isinstance(origin, str) or origin not in SOURCE_ORIGINS or not isinstance(content, str):
        raise ValueError("external source origin and exact text required")
    return {"id": _name(node_id), "kind": "ordinary_source", "origin": origin,
            "source_sha256": digest(content), "at": instant(at), "complete": True, "parents": []}


def instant(value):
    """No host-local timezone guess and no boolean/NaN timestamps."""
    if isinstance(value, bool):
        raise ValueError("invalid timestamp")
    if isinstance(value, (int, float)):
        result = float(value)
    elif isinstance(value, str):
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError("timestamp needs an explicit offset")
        result = parsed.timestamp()
    else:
        raise ValueError("invalid timestamp")
    if not math.isfinite(result) or result < 0:
        raise ValueError("invalid timestamp")
    return result


def _name(value):
    if not isinstance(value, str) or not value or len(value) > 256:
        raise ValueError("invalid receipt identifier")
    return value


def _hash(value):
    if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise ValueError("invalid content digest")
    return value


def normalize_receipt(value):
    """Allowlisted copy. Malformed receipts remain explicitly unknown, never clean."""
    try:
        if not isinstance(value, dict) or value.get("schema") != SCHEMA:
            raise ValueError("unknown receipt schema")
        if value.get("status") not in (None, "recorded"):
            raise ValueError("unknown receipt")
        started, final = instant(value["started_at"]), instant(value["finalized_at"])
        if final < started or value.get("delivery") not in ("delivered", "not_delivered", "unknown"):
            raise ValueError("invalid delivery interval")
        attempts = value["generation"]["attempts"]
        if not isinstance(attempts, list) or not attempts or len(attempts) > 32:
            raise ValueError("invalid attempts")
        kept, seen = [], set()
        for a in attempts:
            if not isinstance(a, dict):
                raise ValueError("invalid attempt")
            key = _name(a["attempt_id"])
            if key in seen or a.get("outcome") not in ("selected", "failed", "discarded"):
                raise ValueError("ambiguous generation attempt")
            seen.add(key)
            evidence = a.get("identity_evidence", "unknown")
            if evidence not in ("response_metadata", "runtime_receipt", "unknown"):
                raise ValueError("unknown identity evidence")
            model = a.get("served_model") if evidence != "unknown" else None
            revision = a.get("served_revision") if evidence != "unknown" else None
            kept.append({"attempt_id": key, "outcome": a["outcome"],
                         "requested_model": _name(a["requested_model"]) if a.get("requested_model") else None,
                         "served_model": _name(model) if model else None,
                         "served_revision": _name(revision) if revision else None,
                         "identity_evidence": evidence})
            if "request_id" in a or "input_sha256" in a:
                kept[-1].update(request_id=_name(a["request_id"]), input_sha256=_hash(a["input_sha256"]))
        selected = _name(value["generation"]["selected_attempt_id"])
        if [a["attempt_id"] for a in kept if a["outcome"] == "selected"] != [selected]:
            raise ValueError("ambiguous selected attempt")
        return {"schema": SCHEMA, "status": "recorded", "turn_id": _name(value["turn_id"]),
                "surface": _name(value["surface"]), "started_at": started, "finalized_at": final,
                "delivery": value["delivery"], "response_sha256": _hash(value["response_sha256"]),
                "context_receipt_id": _name(value["context_receipt_id"]),
                "generation": {"attempts": kept, "selected_attempt_id": selected}}
    except (KeyError, TypeError, ValueError, OverflowError):
        return {"schema": SCHEMA, "status": "unknown"}


def receipt(turn_id, surface, started_at, finalized_at, final_response,
            context_receipt_id, attempts, selected_attempt_id, delivery="unknown"):
    """Construct after final output/delivery; never infer identity from request config."""
    return normalize_receipt({"schema": SCHEMA, "turn_id": turn_id, "surface": surface,
                             "started_at": started_at, "finalized_at": finalized_at,
                             "response_sha256": digest(final_response), "delivery": delivery,
                             "context_receipt_id": context_receipt_id,
                             "generation": {"attempts": attempts, "selected_attempt_id": selected_attempt_id}})


def lineage_status(root, nodes, before):
    """Memoize within a depth budget; check every edge clock before cache reuse."""
    try:
        root, before = _name(root), instant(before)
    except (TypeError, ValueError, OverflowError):
        return "unknown"
    if not isinstance(nodes, dict) or not isinstance(nodes.get(root), dict):
        return "unknown"
    if nodes[root].get("kind") != "context":
        return "unknown"
    memo, visiting = {}, set()

    def visit(key, latest):
        n = nodes.get(key)
        if not isinstance(n, dict) or n.get("id") != key:
            return "unknown"
        try:
            at = instant(n.get("at"))
        except (ValueError, TypeError, OverflowError):
            return "unknown"
        # This is edge-specific: a shared ancestor can precede one parent but
        # follow another. Do not cache an edge failure as the node's standing.
        if at > latest or key in visiting or len(visiting) >= 128:
            return "unknown"
        # A result proved near the root may need more depth than remains on
        # another path. Reuse only within the same remaining traversal budget.
        memo_key = (key, 128 - len(visiting))
        if memo_key in memo:
            return memo[memo_key]
        kind, parents = n.get("kind"), n.get("parents")
        if not isinstance(kind, str) or kind not in KINDS or not isinstance(parents, list):
            return "unknown"
        if any(not isinstance(p, str) or not p for p in parents):
            return "unknown"
        if not parents and kind != "ordinary_source":
            # Known effects stay visible without pretending their ancestry is complete.
            return "influenced_incomplete" if kind in INFLUENCING else "unknown"
        incomplete = n.get("complete") is not True
        own = "influenced" if kind in INFLUENCING else "clean"
        if kind == "reply":
            try:
                _name(n.get("turn_id"))
            except ValueError:
                return "unknown"
            context_id = n.get("context_receipt_id")
            context = nodes.get(context_id) if isinstance(context_id, str) else None
            if (context_id not in parents or not isinstance(context, dict)
                    or context.get("kind") != "context"
                    or n.get("influence") not in ("clean", "influenced", "unknown")):
                return "unknown"
            own = n["influence"]
            if any(n.get(k) for k in ("character_influenced", "tactical")):
                own = "influenced"
        elif kind == "ordinary_source" and (n.get("role") == "assistant" or any(k in n for k in (
                "context_receipt_id", "generation_provenance", "output_provenance", "influence",
                "turn_id", "reply_text", "response_sha256", "witness_receipt"))):
            # Generated outputs must use the reply contract, not an ordinary leaf.
            return "unknown"
        if kind == "ordinary_source":
            if not isinstance(n.get("origin"), str) or n["origin"] not in SOURCE_ORIGINS or parents:
                return "unknown"
            try:
                _hash(n.get("source_sha256"))
            except (TypeError, ValueError):
                return "unknown"
        visiting.add(key)
        states = [visit(p, at) for p in parents]
        visiting.remove(key)
        incomplete = incomplete or own == "unknown" or any(
            state in ("unknown", "influenced_incomplete") for state in states)
        influenced = own == "influenced" or any(
            state in ("influenced", "influenced_incomplete") for state in states)
        result = ("influenced_incomplete" if incomplete else "influenced") if influenced else (
            "unknown" if incomplete else "clean")
        memo[memo_key] = result
        return result
    return visit(root, before)


def joined_identity(row):
    """Join only agreeing explicit envelope/top-level IDs; never generate an ID."""
    ids = [row.get("turn_id")]
    ids += [row[k].get("turn_id") for k in ("generation_provenance", "provenance")
            if isinstance(row.get(k), dict)]
    ids = [value for value in ids if value is not None and value != ""]
    if any(not isinstance(value, str) or not value.strip() for value in ids) or len(set(ids)) > 1:
        return None, "conflicting_identity"
    return (ids[0], "identified") if ids else (None, "missing_stable_id")


def final_response(row):
    """Exact producer-attested final text; never heuristically strip store marks."""
    if "witness_final_text" in row or "witness_final_sha256" in row:
        text = row.get("witness_final_text")
        if not isinstance(text, str) or digest(text) != row.get("witness_final_sha256"):
            return None
        stored = row.get("content")
        ledger = row.get("_witness_adapter_kind") == "ledger" or row.get("source") == "ledger"
        if not isinstance(stored, str) or (stored != text and not (ledger and stored.startswith(text))):
            return None
        return text
    return row.get("content")


def envelope_status(row):
    """Strict opt-in consumer: neither legacy fallback nor another copy clears a denial."""
    values = [row[k] for k in ("generation_provenance", "provenance") if k in row]
    if not values:
        return "unknown_provenance"
    for p in values:
        if not isinstance(p, dict) or p.get("envelope_state") in ("absent_legacy", "malformed"):
            return "unknown_provenance"
        if p.get("output_provenance") != "ordinary_generation" or p.get("may_witness") is not True:
            return "ineligible_provenance"
        if not p.get("turn_id") or p["turn_id"] != row.get("turn_id"):
            return "conflicting_identity"
    return "explicit_witness"


def admission(row, nodes, cutoff):
    if not isinstance(row, dict) or row.get("role") != "assistant":
        return "not_reply"
    if any(row.get(k) for k in ("test_mode", "tactical", "withheld", "character_influenced",
                                 "dream_only", "imported", "transplanted", "timestamp_estimated",
                                 "forgotten", "deleted")):
        return "excluded_act"
    if any(row.get(k) is False for k in (
            "admitted", "eligible", "may_witness", "generated_output_witness_eligible")):
        return "excluded_act"
    from evidence_view import standing, ELIGIBLE
    from evidence_provenance import is_tactical
    if is_tactical(row.get("source")) or is_tactical(row.get("witness_origin_source")):
        return "tactical_source"
    turn_id, identity_status = joined_identity(row)
    if turn_id is None:
        return identity_status
    row = dict(row, turn_id=turn_id)
    status = envelope_status(row)
    if status != "explicit_witness":
        return status
    if standing(row) != ELIGIBLE:
        return "ineligible_evidence_standing"
    candidates = [row["witness_receipt"]] if "witness_receipt" in row else []
    candidates += [row[k]["witness_receipt"] for k in ("generation_provenance", "provenance")
                   if isinstance(row.get(k), dict) and "witness_receipt" in row[k]]
    if not candidates:
        return "unknown_receipt"
    normalized = [normalize_receipt(r) for r in candidates]
    if any(r != normalized[0] for r in normalized):
        return "conflicting_receipt"
    r = normalized[0]
    if r["status"] != "recorded":
        return "unknown_receipt"
    if r["turn_id"] != row.get("turn_id") or r["surface"] != row.get("surface"):
        return "conflicting_identity"
    text = final_response(row)
    if not isinstance(text, str) or not text.strip():
        return "missing_final_response"
    if r["response_sha256"] != digest(text):
        return "response_changed"
    if r["delivery"] != "delivered":
        return "unconfirmed_delivery"
    if r["finalized_at"] >= cutoff:
        return "outside_cutoff"
    selected = next(a for a in r["generation"]["attempts"] if a["outcome"] == "selected")
    if selected["served_model"] is None:
        return "unknown_served_model"
    state = lineage_status(r["context_receipt_id"], nodes, r["started_at"])
    return "eligible" if state == "clean" else state + "_lineage"


def row_receipt(row):
    if "witness_receipt" in row:
        return normalize_receipt(row["witness_receipt"])
    for k in ("generation_provenance", "provenance"):
        if isinstance(row.get(k), dict) and "witness_receipt" in row[k]:
            return normalize_receipt(row[k]["witness_receipt"])
    return {"schema": SCHEMA, "status": "unknown"}
