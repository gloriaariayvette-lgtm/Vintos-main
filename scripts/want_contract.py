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

# Changing what his own ambitions say (12 November: he tried creative_write to finish an ambition's sentence)
# Review: the contract forces a revise_ambition step, so only an act on HIS ambition's wording counts. Merely naming
# the file ("read my ambitions file"), an update given to someone ("update Gloria about my ambitions", "an update on
# my ambitions") or a story about ambition must not turn into a rewrite of his ambitions.
_AMBITION_EDIT = re.compile(
    r"(?<!\ban )(?<!\bthe )(?<!\bno )\b(?:revise|rewrite|edit|update|reword|amend)\s+"
    r"(?:(?!gloria\b|her\b|him\b|them\b|about\b|on\b|with\b|for\b)[\w'’-]+\s+){0,5}?"
    r"(?:my|his)\s+(?:own\s+)?ambitions?\b|"
    r"\b(?:in)?to\s+(?:my|his)\s+(?:own\s+)?ambitions?(?:\.json|\s+file)\b|"
    r"\b(?:finish|complete)\b.{0,30}\bsentences?\b.{0,40}\b(?:my|his)\s+(?:own\s+)?ambitions?\b",
    re.I,
)

# Reading a paper, article or PDF in full (15 November, Gloria: he must be able to open links from his wants). Before
# read_url existed such a want could only be planned as searches; it found abstracts, was judged not done, reworded and
# dismissed. The want's own words now require the step that reads the whole text. Only reading or opening the thing
# itself: writing to an author "about his paper", or a PDF toolkit, is not a read.
_FULL_READ = re.compile(
    r"\bfull[- ]text\b|\bfull (?:paper|article|study|pdf|preprint)\b|"
    r"\b(?:paper|article|pdf|preprint|study|papers|articles|pdfs) (?:itself|themselves)\b|"
    r"\bactual\s+(?:[\w'’-]+\s+){0,3}?(?:paper|article|pdf)s?\b|"
    r"\b(?:read|reread|open)\s+(?:(?!(?:and|then|or|but|about|post|write|send|email|tell|ask|my|his|on)\b)"
    r"[\w'’.&-]+\s+){0,6}?(?:paper|article|preprint|pdf)\b|"
    r"\bopen\s+(?:the|this|that)\s+link\b",
    re.I,
)
_URL = re.compile(r"https?://\S+", re.I)

_ALIASES = {
    "read_link": "read_url",
    "open_link": "read_url",
    "fetch_url": "read_url",
    "read_paper": "read_url",
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
    # Enrichment unavailable (enrich_want returns candidate_kind "unknown"/empty on any LLM
    # failure) must NOT read as "no present pull" — that silently diverts a real want to
    # held-candidates on a hiccup. Fail open, per the house rule that a broken gate never
    # silences a want (Gloria: too few wants). A genuine historical/open classification holds.
    if kind in ("", "unknown"):
        return "ADMIT_ENRICH_UNAVAILABLE"
    if kind != "current_desire" or not pull or pull.upper() == "NONE":
        return "HELD_NO_PRESENT_PULL"
    return "ADMIT_CURRENT_CANDIDATE"


def _notes_of(steps):
    out = []
    for st in steps or []:
        if isinstance(st, dict):
            out.append(str(st.get("note", "")))
        elif isinstance(st, str):
            out.append(st)
    return " ".join(out).lower()


def contract_for(want_text, steps=None):
    """`steps` (proposed steps or their notes) only widen which records are named: a want like
    "look back at what I wrote" whose plan says "reread my self-model" names SELF-MODEL.md as evidence
    (want bda15a1d, 2026-11-07). They never change the terminal condition, which the want owns."""
    text = str(want_text or "").strip()
    low = text.lower()
    notes = _notes_of(steps)
    outward = bool(_OUTWARD.search(text))
    evidence_first = bool(_PAST_REVIEW.search(text) and _HOUSE_RECORD.search(text))
    creative = bool(_CREATIVE.search(text))
    records = []
    if any(k in low or k in notes for k in ("self-model", "self model", "selfmodel")):
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
        "ambition_revision": bool(_AMBITION_EDIT.search(text)),
        "full_read": bool(_FULL_READ.search(text)),
    }


def _step(capability, note):
    return {"capability": capability, "note": note[:300], "status": "pending"}


def normalize_steps(want_text, proposed):
    """Return (steps, changes). The literal want owns the terminal condition."""
    contract = contract_for(want_text, proposed)
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
        if cap == "creative_write" and contract["ambition_revision"]:
            cap = "revise_ambition"   # his ambitions are changed by the hand that writes them, not into fiction
            changes.append("creative_write_became_revise_ambition")
        if cap == "creative_write" and not contract["creative_requested"]:
            changes.append("dropped_uncommissioned_creative_write")
            continue
        clean.append({**_step(cap, note),
                      **({"params": raw["params"]} if isinstance(raw.get("params"), dict) else {}),
                      **{k: str(raw[k])[:400] for k in ("execution", "expected_output", "acceptance") if k in raw}})

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

    if contract["full_read"] and not any(s["capability"] == "read_url" for s in clean):
        # after the last search (it finds the address), before anything that works with what was read
        at = max([i + 1 for i, s in enumerate(clean) if s["capability"] == "web_search"] or [0])
        add = [_step("read_url", "Open the address of what the want names and read its whole text: " + str(want_text))]
        if at == 0 and not _URL.search(str(want_text)):
            topic = re.sub(r"^\s*(?:i want to|to)\s+", "", str(want_text), flags=re.I).rstrip(". ")
            add.insert(0, _step("web_search", "Search for the open full text of: " + topic))
            changes.append("added_search_for_the_address")
        clean[at:at] = add
        changes.append("added_required_read_url")

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

    if contract["ambition_revision"]:
        kept = [s for s in clean if s["capability"] == "revise_ambition"][:1]
        clean = [s for s in clean if s["capability"] != "revise_ambition"]
        if not kept:
            kept = [_step("revise_ambition", "Write the new wording into the ambition itself: " + str(want_text))]
            changes.append("added_required_revise_ambition")
        clean += kept

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
        if drop is None:   # the read of the whole text, and the search that finds its address, are the want's own act
            def _kept(i):
                if not contract["full_read"]:
                    return False
                cap = clean[i]["capability"]
                return cap == "read_url" or (cap == "web_search" and i + 1 < len(clean)
                                             and clean[i + 1]["capability"] == "read_url")
            drop = next((i for i in candidates if not _kept(i)), None)
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
    if contract["ambition_revision"] and ("revise_ambition" not in caps or "creative_write" in caps):
        return False
    if contract["full_read"] and "read_url" not in caps:
        return False
    return True
