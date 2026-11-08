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
KINDS = INFLUENCING | frozenset(("context", "value_map", "ordinary_source"))


def digest(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


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
    """Resolve every ancestor; missing, cyclic, future or incomplete paths are unknown."""
    if not isinstance(nodes, dict):
        return "unknown"
    def visit(key, stack, latest):
        if key in stack or len(stack) >= 128:
            return "unknown"
        n = nodes.get(key)
        if not isinstance(n, dict) or n.get("id") != key or n.get("complete") is not True:
            return "unknown"
        try:
            at = instant(n.get("at"))
        except (ValueError, TypeError, OverflowError):
            return "unknown"
        kind, parents = n.get("kind"), n.get("parents")
        if at > latest or kind not in KINDS or not isinstance(parents, list):
            return "unknown"
        if any(not isinstance(p, str) or not p for p in parents):
            return "unknown"
        states = [visit(p, stack | {key}, at) for p in parents]
        if kind in INFLUENCING or "influenced" in states:
            return "influenced"
        if "unknown" in states:
            return "unknown"
        return "clean"
    return visit(root, set(), before)


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
    if any(row.get(k) for k in ("test_mode", "tactical", "withheld", "character_influenced")):
        return "excluded_act"
    if row.get("admitted") is False or row.get("eligible") is False or row.get("may_witness") is False:
        return "excluded_act"
    status = envelope_status(row)
    if status != "explicit_witness":
        return status
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
    if not isinstance(row.get("content"), str) or not row["content"].strip():
        return "missing_final_response"
    if r["response_sha256"] != digest(row["content"]):
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
