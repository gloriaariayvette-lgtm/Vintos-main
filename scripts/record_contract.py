#!/usr/bin/env python3
"""record_contract.py - the shared vocabulary for records that cross organs, and an audit that says
which producers keep it.

Review items 34, 39, 51 (2026-09-10). Three things were spelled differently in every organ: the
IDENTITY a record carries, the LAYER it belongs to (what arrived, what an organ made of it, what was
asked of the world, what the world answered), and the RESPONSE STATE of an attempt. They are named
once here. Nothing is rewritten by this module; `audit()` reads the checkout and reports which
producers already carry each, so the gaps are visible instead of assumed.

    IDENTITY[kind]      the id field a record of that kind carries, and where it is minted
    LAYERS              raw | derived | requested | acknowledged, with what belongs in each
    RESPONSE_STATES     the one vocabulary for how an attempt ended
    normalize_state(s)  a legacy word mapped into that vocabulary (or ValueError)
    audit()             {"identity": [...], "states": [...]} - producers and whether they conform
"""
import os, re, json

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)

IDENTITY = {
    "turn":        {"field": "turn_id",       "minted_by": "turn_coordinator.begin", "shape": "t-<16 hex>"},
    "prediction":  {"field": "prediction_id", "minted_by": "prediction_ledger.new_id / the producer", "shape": "<XX>-<8 hex>"},
    "grade":       {"field": "grade_id",      "minted_by": "grading_contract.record", "shape": "G-<8 hex>"},
    "effect":      {"field": "effect_id",     "minted_by": "effect_gate.authorize", "shape": "EF-<hex>"},
    "want":        {"field": "want_id",       "minted_by": "emoclaw_utils.generate_want (as `id` on the want row; `want_id` wherever it travels)", "shape": "W-<hex>"},
    "artifact":    {"field": "sha256",        "minted_by": "artifact_manifest.build", "shape": "sha256 of the bytes"},
    "moment":      {"field": "occurrence_id", "minted_by": "the organ that witnessed it (a turn id or a ledger row)", "shape": "free"},
    "broker_event":{"field": "seq",           "minted_by": "broker._ev (hash-chained)", "shape": "int + prev hash"},
    "checkpoint":  {"field": "checkpoint_id", "minted_by": "want_checkpoints.create (as `id` on the row)", "shape": "CP-<6 hex>"},
    "correction":  {"field": "correction_id", "minted_by": "the hallucination flag route", "shape": "HC-<8 hex>"},
    "question":    {"field": "question_id",   "minted_by": "causality.queue_question / thread_store.admit (as `id` on the row)", "shape": "CQ-/T-/UQ-/TN-"},
    "reaction":    {"field": "reaction_id",   "minted_by": "sensor_reactions.observe", "shape": "SR-<8 hex>"},
    "build":       {"field": "build_id",      "minted_by": "self_review_builder.build", "shape": "SRB-<10 hex>"},
}

LAYERS = {
    "raw":          "what arrived, verbatim and unedited (her words, a file's bytes, a sensor reading with its own timestamp)",
    "derived":      "what an organ made of it (a summary, a salience, an inference, an embedding) - never presented as raw",
    "requested":    "what was asked of the world (a device command, a send, a render, a provider call)",
    "acknowledged": "what the world answered (a transport receipt, her rating, a file on disk, a played clip)",
}

# The response vocabulary governs one thing only: how an ATTEMPT ended. A lifecycle state (a plan that
# is open, a landing in progress, a somatic reading, a health verdict) is a domain state and has its own
# words on purpose - the audit lists those separately rather than calling them violations.
RESPONSE_STATES = ("successful", "invalid", "absent", "declined", "held", "timed_out", "unavailable")
RESPONSE_PRODUCERS = ("scripts/deliver.py", "scripts/effect_gate.py", "scripts/toy_link.py", "bin/gen_result.py",
                      "bin/model_router.py", "scripts/grading_contract.py", "scripts/compute_admission.py",
                      "scripts/want_completion.py", "bin/vintos_claude_shim.py")
_LEGACY = {
    "ok": "successful", "valid": "successful", "moved": "successful", "done": "successful", "true": "successful",
    "error": "invalid", "malformed": "invalid", "corrupt": "invalid", "unsupported": "invalid",
    "empty": "absent", "none": "absent", "missing": "absent", "not_found": "absent", "unmoved": "absent",
    "refused": "declined", "denied": "declined", "not_requested": "declined", "no": "declined",
    "pending": "held", "waiting": "held", "held_incomplete": "held", "queued": "held",
    "timeout": "timed_out", "deadline": "timed_out",
    "down": "unavailable", "unreachable": "unavailable", "failed": "unavailable",
}


def normalize_state(s):
    """A word from any organ, mapped into the one vocabulary. Raises on something with no meaning here."""
    w = str(s or "").strip().lower()
    if w in RESPONSE_STATES:
        return w
    if w in _LEGACY:
        return _LEGACY[w]
    raise ValueError("%r is not a response state and has no mapping; add it to record_contract._LEGACY" % s)


def _files():
    for d in ("scripts", "bin"):
        dd = os.path.join(REPO, d)
        for f in sorted(os.listdir(dd)) if os.path.isdir(dd) else []:
            p = os.path.join(dd, f)
            if f.endswith(".py") and os.path.isfile(p) and not os.path.islink(p):
                yield os.path.join(d, f), open(p, errors="replace").read()


def audit():
    """Which files write each identity field, and which use a state word outside the vocabulary."""
    ident = {k: [] for k in IDENTITY}
    stray, domain = [], []
    for rel, s in _files():
        for kind, spec in IDENTITY.items():
            if re.search(r'["\']%s["\']\s*:' % re.escape(spec["field"]), s):
                ident[kind].append(rel)
        for m in re.finditer(r'"state"\s*:\s*"([a-z_]+)"', s):
            if rel not in RESPONSE_PRODUCERS:
                domain.append({"file": rel, "state": m.group(1)}); continue
            try:
                normalize_state(m.group(1))
            except ValueError:
                stray.append({"file": rel, "state": m.group(1)})
    return {"identity": {k: {"field": IDENTITY[k]["field"], "writers": v} for k, v in ident.items()},
            "unmapped_states": stray, "domain_states": domain, "layers": sorted(LAYERS)}


if __name__ == "__main__":
    a = audit()
    for k, v in a["identity"].items():
        print("%-13s %-15s %d writer(s)" % (k, v["field"], len(v["writers"])))
    print("response producers using a word outside the vocabulary:", a["unmapped_states"] or "none")
    print("domain (lifecycle) states elsewhere, by design:", len(a["domain_states"]))
