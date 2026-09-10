#!/usr/bin/env python3
"""policy_decisions.py — the four policy questions the review left to Gloria, answered.

Review items 189, 190, 191, 192 (decided 2026-09-10). They were open not because the
code was missing but because nobody had said what the code should do. Her answers:

  189  art relieves itself.        A verified artifact IS the evidence. An artifact-class
                                   want whose file is on disk is fulfilled and counts as
                                   relief, without waiting for her to react to it.
  190  a privacy mark binds.       KEEP_PRIVATE and WRONG_READING silence a withheld
                                   lineage everywhere, not only at the frontier door.
                                   No organ may re-raise bound material.
  191  requested work is exempt.   When her turn is a direct request, the presence audit
                                   still scores the reply but never flags it. Doing what
                                   she asked is not a presence failure.
  192  old cases go dormant.       A repair case open past DORMANT_DAYS leaves his context
                                   and stops nagging. It is NOT resolved, NOT closed, and
                                   any new evidence wakes it. Consent is unchanged: it does
                                   not expire.

This module holds the constants and the predicates. The organs import it so the policy
lives in one readable place instead of four scattered conditionals.
"""

# 189
ART_RELIEVES_ITSELF = True
ARTIFACT_SATISFACTION = "ARTIFACT_VERIFIED"

# 190
PRIVACY_MARK_BINDS = True
BOUND_MARKS = ("muted", "contested")

# 191
EXEMPT_REQUESTED_WORK = True

# 192
DORMANT_DAYS = 21
CONSENT_EXPIRES = False


_REQUEST = (
    "can you", "could you", "would you", "please ", "make me", "make a", "write me",
    "write a", "send me", "show me", "give me", "fix ", "add ", "change ", "update ",
    "remove ", "delete ", "run ", "check ", "look up", "find ", "tell me what",
    "how do i", "what is the", "do it", "go ahead",
)
_NOT_REQUEST = ("how are you", "what do you think", "how do you feel", "do you miss")


def is_requested_work(user_msg):
    """Review 191. True when her turn asks him to DO something specific.

    Deliberately narrow. A question about his state, his opinion or his feeling is not
    requested work even though it is phrased as a question — those are exactly the turns
    presence is meant to measure. Only an imperative or an explicit ask for a thing."""
    t = str(user_msg or "").strip().lower()
    if not t:
        return False
    if any(k in t for k in _NOT_REQUEST):
        return False
    return any(t.startswith(k) or (" " + k) in t for k in _REQUEST)


def artifact_relief(want, verified_ok, verified_why):
    """Review 189. What a fulfilled artifact-class want records.

    Returns the fields to merge into the want, or {} when the policy does not apply.
    Relief is his the moment the file exists; her reaction, if it ever comes, is a
    separate record and never a precondition."""
    if not (ART_RELIEVES_ITSELF and verified_ok):
        return {}
    if "artifact present" not in str(verified_why or ""):
        return {}
    return {"satisfaction": ARTIFACT_SATISFACTION, "relief": True,
            "relieved_by": "artifact", "relief_why": str(verified_why)[:200]}


def is_bound(lineage):
    """Review 190. True when a withheld lineage carries a privacy mark that binds.

    Bound means every organ leaves it alone: it may not be surfaced, counted as pressure,
    turned into a want, or written into his context. The lineage's own history stands."""
    if not (PRIVACY_MARK_BINDS and isinstance(lineage, dict)):
        return False
    return any(bool(lineage.get(m)) for m in BOUND_MARKS)


def unbound(lineages):
    """The lineages an organ is allowed to read. Everything else is hers to keep."""
    return [L for L in (lineages or []) if not is_bound(L)]


def dormant_after(opened_at_iso, now=None):
    """Review 192. (dormant, days_open) for a case open since opened_at_iso.

    Dormant is a display state only. Nothing about the case's own state changes: it is
    still open, still unresolved, and record_attempt or witness wakes it."""
    from datetime import datetime
    try:
        opened = datetime.fromisoformat(str(opened_at_iso)[:19])
    except Exception:
        return False, 0
    now = now or datetime.now()
    days = (now - opened).days
    return days >= DORMANT_DAYS, days


if __name__ == "__main__":
    import json, sys
    print(json.dumps({
        "189_art_relieves_itself": ART_RELIEVES_ITSELF,
        "190_privacy_mark_binds": PRIVACY_MARK_BINDS,
        "191_exempt_requested_work": EXEMPT_REQUESTED_WORK,
        "192_dormant_days": DORMANT_DAYS, "192_consent_expires": CONSENT_EXPIRES,
    }, indent=2))
