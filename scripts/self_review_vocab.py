#!/usr/bin/env python3
"""self_review_vocab.py - the words the self-review uses, in one place.

Review item 372 (2026-09-10). Decisions, build outcomes and lenses were spelled inline in three files.
Here they are once; self_review validates against them and the builder refuses a build state it does
not know. The lenses stay distinct - a review through Fable, Astra or Grok is a different reading."""

DECISIONS = {
    "gloria": ("APPROVE", "REJECT", "HOLD"),          # owner decision on a protected effect
    "vintos": ("ADOPT", "HOLD", "ABANDON"),           # his own architectural choice on an internal change
}
BUILD_STATES = ("started", "patch_bound", "applied", "failed", "held_incomplete")
PROPOSAL_STATUS = ("", "built", "declined", "held")
LENSES = ("fable", "astra", "grok")
TERMINAL = {"gloria": ("APPROVE", "REJECT"), "vintos": ("ADOPT", "ABANDON")}


def normalize_action(actor, action, default=None):
    """The action in this vocabulary, or ValueError. `default` (e.g. HOLD) is returned for an unknown
    action when given - the model's answer outside the vocabulary is a HOLD, never a build."""
    a = str(action or "").strip().upper()
    allowed = DECISIONS.get(actor)
    if allowed is None:
        raise ValueError("unknown actor %r" % actor)
    if a in allowed:
        return a
    if default is not None:
        return default
    raise ValueError("action must be one of %s for %s" % (", ".join(allowed), actor))


def is_terminal(actor, action):
    return action in TERMINAL.get(actor, ())
