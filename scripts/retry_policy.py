#!/usr/bin/env python3
"""retry_policy.py - one retry policy for the bounded callers (Study, the self-review builder, the
Atelier quantum doorway, the room seats).

Review item 175 (2026-09-10). Each had its own: the Study loop continued at most twice, the builder
reconciled a died build and allowed one fresh attempt, the quantum doorway returned an error with no
retry, the seat retried transport faults with a backoff. The rules are one rule now, per class of
work, and each caller asks for its class rather than carrying its own numbers.

    policy(kind) -> {"attempts", "backoff_s", "retry_on", "never_retry_on", "why"}
    should_retry(kind, attempt, error) -> (bool, seconds_to_wait, why)

Classes: transport (a socket or a 5xx), provider (a model call), bounded_loop (a read/grep loop the
model drives), build (an install), device (a physical effect - never retried automatically).
"""
POLICIES = {
    "transport":    {"attempts": 3, "backoff_s": [1, 3, 9], "retry_on": ("timeout", "connection", "5xx", "reset"),
                     "never_retry_on": ("4xx", "refused", "unauthorized"), "why": "a dropped socket is not an answer; a 4xx is"},
    "provider":     {"attempts": 2, "backoff_s": [2], "retry_on": ("timeout", "overloaded", "5xx"),
                     "never_retry_on": ("refused", "invalid", "budget"), "why": "one retry, then the result stands as unavailable"},
    "bounded_loop": {"attempts": 2, "backoff_s": [0], "retry_on": ("empty", "truncated"),
                     "never_retry_on": ("refused", "outside_roots"), "why": "a model-driven loop continues at most twice"},
    "build":        {"attempts": 1, "backoff_s": [], "retry_on": (),
                     "never_retry_on": ("*",), "why": "a build is reconciled and re-attempted deliberately, never automatically"},
    "device":       {"attempts": 1, "backoff_s": [], "retry_on": (),
                     "never_retry_on": ("*",), "why": "a physical effect is never repeated by a machine deciding it did not land"},
}


def policy(kind):
    return dict(POLICIES.get(kind) or {"attempts": 1, "backoff_s": [], "retry_on": (), "never_retry_on": ("*",),
                                       "why": "unknown class: one attempt"})


def should_retry(kind, attempt, error=""):
    """(retry, wait_seconds, why). `attempt` is 1-based: the attempt that just failed."""
    p = policy(kind)
    e = str(error or "").lower()
    if "*" in p["never_retry_on"] or any(n in e for n in p["never_retry_on"]):
        return False, 0, "%s: %s" % (kind, p["why"])
    if attempt >= p["attempts"]:
        return False, 0, "%s: %d attempt(s) is the bound" % (kind, p["attempts"])
    if p["retry_on"] and not any(r in e for r in p["retry_on"]):
        return False, 0, "%s: %r is not a retryable failure for this class" % (kind, str(error)[:60])
    wait = p["backoff_s"][attempt - 1] if attempt - 1 < len(p["backoff_s"]) else (p["backoff_s"][-1] if p["backoff_s"] else 0)
    return True, wait, "%s: attempt %d of %d, waiting %ss" % (kind, attempt + 1, p["attempts"], wait)


if __name__ == "__main__":
    for k in POLICIES:
        print("%-13s %s" % (k, policy(k)))
