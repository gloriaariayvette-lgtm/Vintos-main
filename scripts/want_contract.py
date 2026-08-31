#!/usr/bin/env python3
"""Pure want-to-plan contracts.

The planner may propose steps; it may not redefine what completion means.
This module derives the minimum route from the want's own literal verbs and
objects, then normalizes a proposed plan without inventing a new desire.
"""
import re


_OUTWARD = re.compile(
    r"\b(?:tell|ask|show|share|send|give|bring|say|write|explain|report|let)\b.{0,45}"
    r"\bgloria\b|\bgloria\b.{0,45}\b(?:tell|ask|show|share|send|give|say)\b",
    re.I,
)
_PAST_REVIEW = re.compile(
    r"\b(?:review(?:ed|ing)?|reread|revisit(?:ed|ing)?|look(?:ed|ing)? back|"
    r"earlier|previous|past|last time|did not|didn't)\b",
    re.I,
)
_HOUSE_RECORD = re.compile(
    r"\b(?:self[- ]?model|journal|interaction|ledger|imprint|causality|"
    r"value[- ]?map|memory|record|file|review)\b",
    re.I,
)
_CREATIVE = re.compile(
    r"\b(?:creative|compose|paint|draw|film|poem|poetry|story|fiction|scene|"
    r"image|art|music|video)\b",
    re.I,
)

_ALIASES = {
    "tell_gloria": "gloria",
    "route_to_gloria": "gloria",
    "journal": "write_journal",
    "read_files": "read_memory",
    "search_files": "read_memory",
}

GENERATED_SOURCES = {
    "structural", "latent_thread", "emotional-reflection", "wants-check",
    "web-search", "evolution", "idle-journal",
}


def admission_state(source, candidate_kind="", present_pull=""):
    """Shape screen only. Roots remain the evidence; generated prose is not."""
    if str(source or "").lower() not in GENERATED_SOURCES:
        return "ADMIT_AUTHORED_OR_UNCLASSIFIED"
    kind = str(candidate_kind or "").lower()
    pull = str(present_pull or "").strip()
    if kind != "current_desire" or not pull or pull.upper() == "NONE":
        return "HELD_NO_PRESENT_PULL"
    return "ADMIT_CURRENT_CANDIDATE"


def contract_for(want_text):
    text = str(want_text or "").strip()
    low = text.lower()
    outward = bool(_OUTWARD.search(text))
    evidence_first = bool(_PAST_REVIEW.search(text) and _HOUSE_RECORD.search(text))
    creative = bool(_CREATIVE.search(text))
    records = []
    if "self-model" in low or "self model" in low:
        records.append("SELF-MODEL.md")
    if "journal" in low or evidence_first:
        records.append("contemporaneous journal and interaction records")
    if not records and evidence_first:
        records.append("the named house records")
    return {
        "outward_to_gloria": outward,
        "evidence_first": evidence_first,
        "creative_requested": creative,
        "records": records,
        "terminal": "gloria" if outward else None,
    }


def _step(capability, note):
    return {"capability": capability, "note": note[:300], "status": "pending"}


def normalize_steps(want_text, proposed):
    """Return (steps, changes). The literal want owns the terminal condition."""
    contract = contract_for(want_text)
    clean, changes = [], []
    for raw in proposed or []:
        if not isinstance(raw, dict):
            changes.append("dropped_non_step")
            continue
        cap = _ALIASES.get(str(raw.get("capability", "")).strip().lower(),
                           str(raw.get("capability", "")).strip().lower())
        note = str(raw.get("note", "")).strip()
        if not cap or not note:
            changes.append("dropped_incomplete_step")
            continue
        if cap == "creative_write" and not contract["creative_requested"]:
            changes.append("dropped_uncommissioned_creative_write")
            continue
        clean.append(_step(cap, note))

    # Journaling and introspection are two renderings of the same reflective
    # move here. Keeping both is padding, not sequence.
    reflective = [i for i, s in enumerate(clean)
                  if s["capability"] in ("introspect", "write_journal")]
    if len(reflective) > 1:
        keep = next((i for i in reflective if clean[i]["capability"] == "introspect"),
                    reflective[0])
        clean = [s for i, s in enumerate(clean)
                 if i == keep or i not in reflective]
        changes.append("collapsed_duplicate_reflection")

    if contract["evidence_first"]:
        existing = next((s for s in clean if s["capability"] == "read_memory"), None)
        clean = [s for s in clean if s["capability"] != "read_memory"]
        if existing is None:
            named = ", ".join(contract["records"])
            existing = _step(
                "read_memory",
                "Read %s around the original review; separate what was recorded then "
                "from interpretations added later." % named,
            )
            changes.append("added_required_evidence_step")
        clean.insert(0, existing)

    if contract["outward_to_gloria"]:
        existing = next((s for s in clean if s["capability"] == "gloria"), None)
        clean = [s for s in clean if s["capability"] != "gloria"]
        if existing is None:
            existing = _step(
                "gloria",
                "Bring the actual finding to Gloria directly, distinguishing the earlier "
                "observation from what is still wanted now.",
            )
            changes.append("added_required_gloria_terminal")
        clean.append(existing)

    # Preserve the required first and last steps. Remove padding from the
    # middle rather than silently dropping the act that would fulfill the want.
    while len(clean) > 4:
        candidates = range(1 if contract["evidence_first"] else 0,
                           len(clean) - (1 if contract["outward_to_gloria"] else 0))
        drop = next((i for i in candidates
                     if clean[i]["capability"] in ("write_journal", "creative_write")), None)
        if drop is None:
            drop = next(iter(candidates), None)
        if drop is None:
            break
        clean.pop(drop)
        changes.append("trimmed_nonterminal_padding")
    return clean, changes


def satisfies_contract(want_text, steps):
    contract = contract_for(want_text)
    caps = [s.get("capability") for s in (steps or []) if isinstance(s, dict)]
    if contract["evidence_first"] and (not caps or caps[0] != "read_memory"):
        return False
    if contract["outward_to_gloria"] and (not caps or caps[-1] != "gloria"):
        return False
    if not contract["creative_requested"] and "creative_write" in caps:
        return False
    return True
