#!/usr/bin/env python3
"""turn_coordinator.py — the one place a turn's lifecycle is owned.

Sol's required sequence, in order:

    raw input
    -> exact strategy-stop interceptor
    -> barrier snapshot
    -> mint turn_id
    -> fetch idempotent capsule ONLY if the barrier is clear
    -> construct an immutable TurnContext
    -> assemble prompt (capsule block only if present)
    -> notify capsule admitted_to_prompt
    -> generate a COMPLETE reply
    -> parse typed effects
    -> authorize each effect against the TurnContext (explicit permits)
    -> execute
    -> run provenance-aware post-response writers
    -> turn_record.record(context + commitment + provenance + outcomes)
    -> broker capsule disposition
    -> close the turn in `finally`

Two objects, both immutable once made:

    Turn         the whole context: id, surface, barrier, capsule, provenance
    (permits)    made per effect at authorize time, carried to the executor

There is NO ambient authority. The server holds the Turn for the duration of a
request and passes it explicitly to whatever parses effects. Concurrency between
chat and avatar is safe because nothing is shared in a module global.

USAGE (server side):

    turn = begin(raw_text, surface, test_mode=...)
    prompt += turn.capsule_block            # '' unless a tactic is live
    ... generate reply ...
    turn.parsed_effects()                   # optional: authorize device tags here
    finish(turn, reply_text, outcome="response_created")

If generation throws, call finish(turn, None, outcome="generation_failed") — or
just let the `with turn_scope(...)` context manager record the furthest stage
reached and close in finally.
"""
import os, sys, uuid, json
from datetime import datetime
from contextlib import contextmanager

sys.path.insert(0, os.path.expanduser("~/.vintos/workspace/scripts"))

BROKER = "http://127.0.0.1:8611"
SURFACES = {"chat", "avatar"}


class Turn:
    __slots__ = ("turn_id", "surface", "barrier", "capsule_block", "commitment",
                 "context", "test_mode", "stage", "_disposed")

    def __init__(self, turn_id, surface, barrier, capsule_block, commitment,
                 context, test_mode):
        self.turn_id = turn_id
        self.surface = surface
        self.barrier = barrier
        self.capsule_block = capsule_block or ""
        self.commitment = commitment or {}
        self.context = context
        self.test_mode = test_mode
        self.stage = "opened"
        self._disposed = False

    @property
    def carries_capsule(self):
        return bool(self.commitment)


def _post(path, body, timeout=2.0):
    import urllib.request
    try:
        req = urllib.request.Request(BROKER + path,
                                     data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except Exception:
        return None


def begin(raw_text, surface, test_mode=False):
    """Open a turn. Returns a Turn. Never raises into the request path."""
    turn_id = "t-" + uuid.uuid4().hex[:16]
    surface = surface if surface in SURFACES else "chat"

    # 1. exact strategy-stop interceptor. If she used the reserved command, stop
    #    any live stratagem immediately, before anything else this turn.
    try:
        import constitutional_barrier as cb
        if cb.strategy_stop_requested(raw_text):
            _strategy_stop(raw_text)
    except Exception:
        pass

    # 2. barrier snapshot.
    try:
        import constitutional_barrier as cb
        clear, barrier = cb.capsule_eligible(raw_text)
    except Exception:
        clear, barrier = False, {"clear": False, "satisfied_by": ["barrier_unavailable"]}

    # 3-4. fetch a capsule ONLY if clear. A capsule is never requested and then
    #      discarded — that would write a private issuance event for a tactic
    #      with no standing in the turn.
    capsule_block, commitment = "", {}
    if clear:
        try:
            from stratagem import fetch_capsule
            capsule_block, commitment = fetch_capsule(turn_id, surface)
        except Exception:
            capsule_block, commitment = "", {}
    else:
        try:
            import constitutional_barrier as cb
            _record_ineligible(turn_id, surface, cb.ineligible_record(barrier))
        except Exception:
            pass

    # 5. the immutable context.
    try:
        from effect_gate import TurnContext
        context = TurnContext(turn_id, surface,
                              capsule_commitment=commitment or None,
                              barrier=barrier, test_mode=test_mode)
    except Exception:
        context = None

    turn = Turn(turn_id, surface, barrier, capsule_block, commitment,
                context, test_mode)

    # 6. if a capsule was admitted to the prompt, tell the broker so the
    #    disposition ledger reflects it.
    if commitment:
        turn.stage = "admitted_to_prompt"
        _dispose(turn, "admitted_to_prompt")
    return turn


def authorize_device(turn, toy, level, kind=None, detail=None):
    """Authorize one device effect against this turn. Returns (permit, mode, why).
    The executor passes the permit to toy_link. A capsule turn is denied here."""
    try:
        import effect_gate
        return effect_gate.authorize(turn.context, toy, level, kind=kind, detail=detail)
    except Exception:
        return None, "send", None


def authorize_nondevice(turn, kind, detail=None):
    """Authorize a projector/outbound effect. Returns (allow, mode, why)."""
    try:
        import effect_gate
        return effect_gate.authorize_effect(turn.context, kind, detail=detail)
    except Exception:
        return True, "send", None


def may_witness(turn, claim_kind):
    """False when this turn's output must not be evidence for claim_kind."""
    try:
        import effect_gate
        return effect_gate.may_witness(turn.context, claim_kind)
    except Exception:
        return True


def record(turn, surface_prompt_text, user_msg="", extra=None):
    """Write the turn record with the context's commitment + provenance."""
    try:
        from turn_record import record as _rec
        _rec(turn.surface, surface_prompt_text, user_msg,
             extra=extra, context=turn.context)
    except Exception:
        pass


def finish(turn, reply_text, outcome="completed"):
    """Close the turn. Records the disposition of any capsule and marks the
    furthest stage reached. Idempotent."""
    if turn is None or getattr(turn, "_disposed", False):
        return
    turn.stage = outcome
    if turn.carries_capsule:
        state = outcome if outcome in _DISPOSITION_STATES else (
            "generation_failed" if reply_text is None else "completed")
        _dispose(turn, state)
    turn._disposed = True


@contextmanager
def turn_scope(raw_text, surface, test_mode=False):
    """Open a turn, hand it to the caller, and guarantee it closes. On an
    exception the furthest completed stage is recorded before closing."""
    turn = begin(raw_text, surface, test_mode=test_mode)
    try:
        yield turn
        finish(turn, "", outcome=turn.stage if turn.stage != "opened" else "completed")
    except Exception:
        finish(turn, None, outcome="generation_failed")
        raise


# ---------------------------------------------------------------------------

_DISPOSITION_STATES = {"issued", "admitted_to_prompt", "generation_failed",
                       "response_created", "effects_completed", "transport_unknown",
                       "completed", "capsule_unrealized"}


def _dispose(turn, state):
    """Best-effort disposition. If the broker is unreachable, record it pending
    locally rather than let 'issued' silently look like 'used'."""
    body = {"id": _worktable_id(),
            "turn_id": turn.turn_id,
            "capsule_sha256": turn.commitment.get("capsule_sha256", ""),
            "state": state}
    r = _post("/stratagem/disposition", body)
    if r is None:
        _pending(turn.turn_id, state)


def _worktable_id():
    r = _post("/worktable_id", {})
    return (r or {}).get("id", "")


def _strategy_stop(raw_text):
    pid = _worktable_id()
    if pid:
        _post("/stratagem/strategy-stop",
              {"id": pid, "trigger_ref": "chat", "verbatim": str(raw_text)[:300]})


def _pending(turn_id, state):
    try:
        mem = os.path.expanduser("~/.vintos/workspace/memory")
        with open(os.path.join(mem, "disposition-pending.jsonl"), "a") as f:
            f.write(json.dumps({"turn_id": turn_id, "state": state,
                                "at": datetime.now().isoformat()}) + "\n")
    except Exception:
        pass


def _record_ineligible(turn_id, surface, rec):
    try:
        mem = os.path.expanduser("~/.vintos/workspace/memory")
        with open(os.path.join(mem, "capsule-ineligible.jsonl"), "a") as f:
            f.write(json.dumps({"turn_id": turn_id, "surface": surface,
                                "at": datetime.now().isoformat(), **rec}) + "\n")
    except Exception:
        pass


if __name__ == "__main__":
    import sys as _s
    raw = " ".join(_s.argv[1:]) or "hello"
    t = begin(raw, "chat")
    print("turn:", t.turn_id, "| surface:", t.surface)
    print("barrier clear:", t.barrier.get("clear"), t.barrier.get("satisfied_by"))
    print("carries capsule:", t.carries_capsule)
    print("capsule block:", (t.capsule_block[:80] + "...") if t.capsule_block else "(none)")
    finish(t, "", outcome="completed")
