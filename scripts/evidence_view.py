#!/usr/bin/env python3
"""evidence_view.py — the consumer door for the evidence graph.

evidence_provenance protects a WRITE. This protects every READ after it.

Sol's finding: the envelope correctly marks the record, and then value-map,
causality, self-model-update and the rest reopen the raw file with json.load
and never look at the mark. A tactical act therefore becomes a value, a causal
hypothesis, a want, or an identity input one cron later — not because the
protection failed, but because nothing downstream was obliged to consult it.

Dozens of local `if may_witness` checks would be the wrong correction: the one
organ that forgets is the one that matters. So there is a door, and learning
organs are not to open raw ledger, imprint, or merged-chat files at all.

    record_view(...)    exact history. Everything that happened, including his
                        tactical act. For display, audit, and his own recall.
    witness_view(...)   only what may independently update a model of the world
                        or the self. Strictly a subset of record_view.
    derive(...)         a new record built from others inherits the LEAST
                        eligible of its ancestors, transitively.

Eligibility is three-valued, and HELD is not a synonym for ineligible:

    eligible     may witness
    ineligible   happened, and is known not to be independent evidence
    HELD         lineage is missing where it was required, or malformed.
                 Never silently ordinary; never silently discarded either.

Missing and malformed stay distinct, exactly as they are on the write side: a
record with no provenance field at all is a genuine pre-envelope record and
keeps its old standing, while a record that CARRIES lineage and got it wrong is
HELD.
"""
import json
import os

try:
    import evidence_provenance as EP
except Exception:                                        # standalone use
    EP = None

ELIGIBLE, INELIGIBLE, HELD = "eligible", "ineligible", "HELD"

# worst first — "least eligible" is a real ordering, not a boolean AND
_ORDER = {HELD: 0, INELIGIBLE: 1, ELIGIBLE: 2}

PROV_KEYS = ("generation_provenance", "provenance")
LINEAGE_KEYS = ("derived_from", "parents", "ancestors")


class NotADoor(RuntimeError):
    """A learning organ opened a raw evidence file."""


def _prov(rec):
    for k in PROV_KEYS:
        if k in rec:
            return rec[k]
    return None


def eligibility(rec):
    """Three-valued standing of ONE record, before lineage is considered."""
    if not isinstance(rec, dict):
        return HELD
    p = _prov(rec)
    if p is None:
        # No envelope was ever attached. Pre-envelope history and the
        # counterpart's own verbatim words both land here and stay ordinary.
        return ELIGIBLE
    if not isinstance(p, dict):
        return HELD
    if EP is not None:
        n = EP.normalize(p)
        if n.get("envelope_state") == "malformed":
            return HELD
        return ELIGIBLE if n.get("may_witness") else INELIGIBLE
    if "may_witness" not in p:
        return HELD
    return ELIGIBLE if p.get("may_witness") else INELIGIBLE


def _lineage(rec):
    for k in LINEAGE_KEYS:
        v = rec.get(k)
        if v is None:
            continue
        if isinstance(v, dict):
            v = [v]
        if not isinstance(v, list):
            return None                                  # malformed lineage
        return v
    return []


def standing(rec, resolve=None, _seen=None):
    """Transitive standing: this record, floored by its least-eligible ancestor.

    ``resolve(ref) -> record`` looks up an ancestor by whatever reference the
    record carries. An ancestor that cannot be resolved is not assumed
    innocent; it is missing lineage, and missing lineage is HELD.
    """
    own = eligibility(rec)
    if own == HELD or not isinstance(rec, dict):
        return HELD
    if "evidence_standing" in rec:
        # An already-compiled record. derive() stores compact ancestor REFS, not
        # the ancestors themselves, so re-walking a derived record without a
        # resolver would call its own lineage unresolvable and turn a correctly
        # computed "ineligible" into HELD one hop later. The compiled value is a
        # floor, never a licence: it can only lower the record's own standing.
        c = rec.get("evidence_standing")
        if c not in _ORDER:
            return HELD
        return c if _ORDER[c] < _ORDER[own] else own
    anc = _lineage(rec)
    if anc is None:
        return HELD
    if not anc:
        return own
    _seen = _seen or set()
    worst = own
    for ref in anc:
        key = json.dumps(ref, sort_keys=True, default=str)[:200]
        if key in _seen:                                 # a cycle is malformed lineage
            return HELD
        parent = ref if isinstance(ref, dict) and _prov(ref) is not None else None
        if parent is None and resolve is not None:
            try:
                parent = resolve(ref)
            except Exception:
                parent = None
        if parent is None:
            return HELD
        s = standing(parent, resolve, _seen | {key})
        if _ORDER[s] < _ORDER[worst]:
            worst = s
        if worst == HELD:
            break
    return worst


def record_view(records, resolve=None):
    """Exact history. Every record, each annotated with its standing."""
    out = []
    for r in records or []:
        if not isinstance(r, dict):
            continue
        e = dict(r)
        e["evidence_standing"] = standing(r, resolve)
        out.append(e)
    return out


def witness_view(records, resolve=None):
    """Only what may independently update a model. HELD never passes."""
    return [r for r in record_view(records, resolve)
            if r["evidence_standing"] == ELIGIBLE]


def held(records, resolve=None):
    """What is HELD — so a caller can surface it rather than lose it."""
    return [r for r in record_view(records, resolve) if r["evidence_standing"] == HELD]


def derive(new_record, parents, resolve=None):
    """Stamp a derived record with the least-eligible standing of its ancestors.

    A value, a causal hypothesis, a want, or a self-model line built from turns
    is exactly this: it must not be more eligible than the least eligible thing
    it was built from.
    """
    rec = dict(new_record or {})
    worst = ELIGIBLE
    refs = []
    for p in (parents or []):
        s = standing(p, resolve) if isinstance(p, dict) else HELD
        if _ORDER[s] < _ORDER[worst]:
            worst = s
        refs.append({"turn_id": p.get("turn_id", ""), "timestamp": p.get("timestamp", "")}
                    if isinstance(p, dict) else {"unresolved": str(p)[:80]})
    rec["derived_from"] = refs
    rec["evidence_standing"] = worst
    rec.setdefault("generation_provenance", {})
    if isinstance(rec["generation_provenance"], dict):
        rec["generation_provenance"] = dict(rec["generation_provenance"])
        rec["generation_provenance"]["may_witness"] = (worst == ELIGIBLE)
        rec["generation_provenance"].setdefault("output_provenance",
                                                "ordinary_generation" if worst == ELIGIBLE
                                                else "stratagem_influenced")
    return rec


# ------------------------------------------------------------------ the door
MEMORY = os.path.expanduser("~/.vintos/workspace/memory")

# Files a learning organ must not open directly. Reading them raw is how the
# protection gets skipped, so the door refuses rather than trusting discipline.
GUARDED = ("chat-history-merged.json", "chat-history.json",
           "avatar-overlay-chat.json", "voice-chat-history.json",
           "interaction-ledger.json",
           "turn-record.jsonl", "imprints.jsonl", "ledger.jsonl")


def is_guarded(path):
    return os.path.basename(str(path)) in GUARDED


def open_history(path, view="witness", resolve=None):
    """The ONLY sanctioned way a learning organ reads evidence.

    view="witness"  what may update a model (the default, because forgetting to
                    choose must not be the dangerous option)
    view="record"   exact history, for display, audit and his own recall
    """
    try:
        with open(path) as f:
            data = json.load(f)
    except Exception:
        data = []
        try:
            with open(path) as f:
                data = [json.loads(l) for l in f if l.strip()]
        except Exception:
            data = []
    if view == "record":
        return record_view(data, resolve)
    if view != "witness":
        raise ValueError("view must be 'witness' or 'record'")
    return witness_view(data, resolve)


HELD_LOG = os.path.join(MEMORY, "evidence-held.jsonl")


def held_read(path, organ="", reason="", log_path=None):
    """A gated read that could not be completed is HELD, not replaced by the raw file.

    Item 106 (2026-09-10): every consumer used to carry `except Exception: json.load(open(path))`
    under its door - the one failure mode the door exists for (evidence_view missing, malformed
    file, unresolvable lineage) walked straight past it. This records WHY the read was skipped
    and returns nothing to learn from. The organ runs empty, visibly, and the reason is on disk.
    """
    row = {"at": __import__("datetime").datetime.now().isoformat(), "organ": str(organ)[:60],
           "path": os.path.basename(str(path)), "standing": HELD, "reason": str(reason)[:200]}
    try:
        lp = log_path or HELD_LOG
        os.makedirs(os.path.dirname(lp), exist_ok=True)
        with open(lp, "a") as f:
            f.write(json.dumps(row, sort_keys=True) + "\n")
    except Exception:
        pass
    try:
        import sys as _sys
        print("[evidence-view] HELD %s for %s: %s" % (row["path"], organ or "?", row["reason"]), file=_sys.stderr)
    except Exception:
        pass
    return []


def door(path, organ="", view="witness", resolve=None):
    """The consumer door with no raw fallback. Guarded files come back through the view; an
    unguarded file is loaded plainly; any failure is HELD (recorded, empty) - never raw."""
    if not os.path.exists(str(path)):
        return []                                        # absent is empty, not HELD
    try:
        data = _load_any(path)
    except Exception as exc:
        return held_read(path, organ, "unreadable or malformed: %s" % str(exc)[:120])
    if view not in ("witness", "record"):
        return held_read(path, organ, "unknown view %r" % (view,))
    try:
        if os.path.basename(str(path)) == "interaction-ledger.json":
            return _ledger_rows(data, view)
        if is_guarded(path):
            return record_view(data, resolve) if view == "record" else witness_view(data, resolve)
        return data
    except Exception as exc:
        return held_read(path, organ, "view failed: %s" % str(exc)[:120])


def _load_any(path):
    """JSON, else JSONL. Raises on anything unparseable - the caller decides what that means."""
    with open(path) as f:
        raw = f.read()
    try:
        return json.loads(raw)
    except Exception:
        rows = []
        for l in raw.splitlines():
            if l.strip():
                rows.append(json.loads(l))
        return rows


def refuse_raw(path):
    """Call at the top of a learning organ that is about to open a file itself."""
    if is_guarded(path):
        raise NotADoor("%s must be read through evidence_view.open_history()"
                       % os.path.basename(str(path)))
    return True


# The interaction ledger is a special shape: ONE record holds both her verbatim
# words and his reply. Her words are always eligible — nothing he does makes
# what she said stop being evidence — so dropping the whole entry would throw
# away her half to protect against his. The entry is kept and his half is
# withheld, visibly.
LEDGER = os.path.join(MEMORY, "interaction-ledger.json")


def ledger_view(path=None, view="witness"):
    try:
        with open(path or LEDGER) as f:
            data = json.load(f)
    except Exception:
        return []
    return _ledger_rows(data, view)


def _ledger_rows(data, view="witness"):
    if not isinstance(data, list):
        return []
    if view == "record":
        return record_view(data)
    out = []
    for e in data:
        if not isinstance(e, dict):
            continue
        s = standing(e)
        if s == ELIGIBLE:
            r = dict(e)
        else:
            r = dict(e)
            r["vintos"] = ""
            r["vintos_withheld"] = True
        r["evidence_standing"] = s
        out.append(r)
    return out
