#!/usr/bin/env python3
"""Carry selected local Lab findings into a frontier session, with receipts.

The local reader may nominate an occasion but cannot certify its own importance.
Priority is computed here from independent, inspectable signals: a successful
source query, new source accessions, lexical contact with the Living Trajectory,
and an already-recorded cross-organ collision. Repetition subtracts priority.
The number is a routing score, never evidence that a biological claim is true.

Notebook history stays append-only. Delivery and acknowledgment are later events,
not retroactive booleans written into an old row. A finding is ``delivered`` when
its exact ID entered a frontier prompt and ``acknowledged`` only when the returned
plan names that offered ID as affecting its choice. Model acknowledgment is an
attestation, not proof of comprehension. Unacknowledged items remain visible debt.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timezone

import chemistry_lab as lab

INTEREST = os.path.join(lab.ROOT, "frontier-interest.jsonl")
SURFACES = os.path.join(lab.ROOT, "frontier-surfaces.jsonl")
COLLISIONS = os.path.join(lab.MEM, "self-review-collisions.jsonl")
FLAG_THRESHOLD = 0.35
MAX_FLAGGED = 4
BLOCK_CHARS = 1800


def _digest(*parts):
    return hashlib.sha256("\x1f".join(str(x) for x in parts).encode("utf-8", "ignore")).hexdigest()


def _words(value):
    return set(re.findall(r"[a-z]{4,}", str(value or "").lower()))


def _trajectory_overlap(text):
    trajectory = lab._load(os.path.join(lab.MEM, "living-trajectory.json"), {})
    target = json.dumps(trajectory, ensure_ascii=False) if trajectory else ""
    left, right = _words(text), _words(target)
    return len(left & right) / float(len(left | right) or 1)


def _collision_witness(accessions):
    needles = {str(x).upper() for x in accessions if x}
    if not needles: return None
    for row in reversed(lab._jsonl(COLLISIONS)[-500:]):
        sides = (row.get("source_a") or {}, row.get("source_b") or {})
        if not any(side.get("system") == "chemistry_lab" for side in sides): continue
        text = " ".join(str(side.get("content_summary") or "") for side in sides).upper()
        if any(item in text for item in needles): return row.get("collision_id")
    return None


def _latest_interest():
    latest = {}
    for row in lab._jsonl(INTEREST):
        if row.get("entry_id"): latest[row["entry_id"]] = row
    return latest


def _evidence_key(row):
    return row.get("evidence_sha256") or _digest(
        sorted(set(str(x) for x in row.get("source_accessions", []) if x)),
        str(row.get("finding") or "").lower().strip())


def assess(reflection, *, source_query_succeeded=False):
    """Append one grounded routing assessment for a completed reflection."""
    accessions = [str(x)[:40] for x in reflection.get("source_accessions", []) if x]
    finding = str(reflection.get("factual_observation") or "")[:1000]
    reading = str(reflection.get("attention") or reflection.get("speculative_reading") or "")[:1000]
    question = str(reflection.get("next_question") or "")[:1000]
    entry_id = str(reflection.get("entry_id") or ("CLF-" + _digest(
        reflection.get("at"), accessions, finding, question)[:16]))
    prior = list(_latest_interest().values())
    seen_accessions = {a for row in prior for a in row.get("source_accessions", [])}
    novel = [a for a in accessions if a not in seen_accessions]
    repeated_question = any(_digest(question.lower().strip()) == row.get("question_sha256")
                            for row in prior if question)
    evidence_sha256 = _digest(sorted(set(accessions)), finding.lower().strip())
    repeated_evidence = any(_evidence_key(row) == evidence_sha256 for row in prior)
    overlap = _trajectory_overlap(" ".join((finding, reading, question)))
    collision_id = _collision_witness(accessions)
    components = {
        "sourced_record": 0.15 if accessions else 0.0,
        "source_query_succeeded": 0.20 if source_query_succeeded else 0.0,
        "new_source_accessions": round(0.20 * len(novel) / float(len(accessions) or 1), 4),
        "trajectory_contact": round(min(0.25, overlap * 4.0), 4),
        "cross_organ_collision": 0.20 if collision_id else 0.0,
        "repetition_penalty": -0.20 if repeated_question else 0.0,
    }
    score = round(max(0.0, min(1.0, sum(components.values()))), 4)
    reasons = [name for name, value in components.items() if value > 0]
    if repeated_question: reasons.append("repeated_question_penalty")
    if repeated_evidence: reasons.append("duplicate_evidence_suppressed")
    row = {
        "entry_id": entry_id, "at": reflection.get("at") or lab.now_iso(),
        "finding": finding, "reflection": reading, "next_question": question,
        "source_accessions": accessions, "interest_score": score,
        "reason_for_score": reasons, "score_components": components,
        "flagged_for_next_lab_session": score >= FLAG_THRESHOLD and not repeated_evidence,
        "source_query_succeeded": bool(source_query_succeeded),
        "collision_id": collision_id, "question_sha256": _digest(question.lower().strip()) if question else None,
        "evidence_sha256": evidence_sha256,
        "truth_status": "routing_priority_from_independent_receipts_not_truth_or_importance",
    }
    lab._append(INTEREST, row)
    return row


def _acknowledged_ids():
    found = set()
    for row in lab._jsonl(SURFACES):
        found.update(str(x) for x in row.get("acknowledged_entry_ids", []) if x)
    return found


def frontier_block(limit=MAX_FLAGGED, budget=BLOCK_CHARS):
    """Return a bounded priority block plus the exact IDs placed in it."""
    acknowledged = _acknowledged_ids()
    candidates = [row for row in _latest_interest().values()
                  if row.get("flagged_for_next_lab_session") and row.get("entry_id") not in acknowledged]
    candidates.sort(key=lambda row: (float(row.get("interest_score") or 0), str(row.get("at") or "")), reverse=True)
    chosen, used = [], 0
    seen_evidence = set()
    for row in candidates:
        evidence = _evidence_key(row)
        if evidence and evidence in seen_evidence: continue
        compact = {key: row.get(key) for key in
                   ("entry_id", "at", "finding", "next_question", "source_accessions", "interest_score")}
        encoded = json.dumps(compact, ensure_ascii=False, sort_keys=True)
        if chosen and used + len(encoded) > int(budget): break
        chosen.append(compact); used += len(encoded)
        if evidence: seen_evidence.add(evidence)
        if len(chosen) >= max(1, int(limit)): break
    if not chosen: return "", []
    return ("[FLAGGED LOCAL LAB FINDINGS — routing priority, not biological truth]\n" +
            json.dumps(chosen, ensure_ascii=False, sort_keys=True)[:int(budget)]), [x["entry_id"] for x in chosen]


def add_to_context(context, receipt):
    block, ids = frontier_block()
    if not block: return context, receipt, []
    merged = (context + "\n\n" + block).strip()
    out = dict(receipt)
    out["frontier_interest_entry_ids"] = ids
    out["frontier_interest_sha256"] = hashlib.sha256(block.encode()).hexdigest()
    out["sources"] = list(receipt.get("sources", [])) + [{
        "name": "flagged_lab_findings", "path": "memory/chemistry-lab/frontier-interest.jsonl",
        "chars": len(block), "sha256": out["frontier_interest_sha256"], "entry_ids": ids}]
    out["total_chars"] = len(merged)
    out["context_sha256"] = hashlib.sha256(merged.encode()).hexdigest()
    out["at"] = lab.now_iso(); out["kind"] = "frontier_context"
    lab._append(lab.RECEIPTS, out)
    return merged, out, ids


def record_delivery(session_id, lens, offered_ids, acknowledged_ids, *, state="responded"):
    offered = [str(x) for x in offered_ids if x]
    acknowledged = [str(x) for x in acknowledged_ids if str(x) in set(offered)]
    previous = lab._jsonl(SURFACES)
    attempts = {item: sum(item in row.get("offered_entry_ids", []) for row in previous) + 1
                for item in offered}
    row = {"surface_id": "CLFS-" + _digest(session_id, lens, offered, len(previous))[:16],
           "at": lab.now_iso(), "session_id": str(session_id)[:80], "lens": str(lens)[:20],
           "state": str(state)[:40], "offered_entry_ids": offered,
           "acknowledged_entry_ids": acknowledged,
           "unacknowledged_entry_ids": [x for x in offered if x not in acknowledged],
           "delivery_attempts": attempts,
           "backlog_bug": any(attempts[x] >= 3 and x not in acknowledged for x in offered),
           "truth_status": "prompt_delivery_receipt_and_frontier_acknowledgment_attestation"}
    lab._append(SURFACES, row)
    return row


def status():
    latest = _latest_interest(); acknowledged = _acknowledged_ids()
    flagged = [row for row in latest.values() if row.get("flagged_for_next_lab_session")]
    pending = [row for row in flagged if row.get("entry_id") not in acknowledged]
    return {"assessed": len(latest), "flagged": len(flagged), "acknowledged": len(flagged) - len(pending),
            "pending": len(pending), "oldest_pending_at": min((x.get("at") for x in pending), default=None),
            "backlog_bug": any(row.get("backlog_bug") for row in lab._jsonl(SURFACES)[-50:])}
