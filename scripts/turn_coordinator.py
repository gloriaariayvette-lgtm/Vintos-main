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
                 "project_id", "context", "test_mode", "stage", "lifecycle",
                 "_disposed")

    def __init__(self, turn_id, surface, barrier, capsule_block, commitment,
                 project_id, context, test_mode):
        self.turn_id = turn_id
        self.surface = surface
        self.barrier = barrier
        self.capsule_block = capsule_block or ""
        self.commitment = commitment or {}
        self.project_id = project_id or ""
        self.context = context
        self.test_mode = test_mode
        self.stage = "issued" if self.commitment else "opened"
        self.lifecycle = {"generation": "not_started", "effects": "not_started",
                          "post_writers": "not_started", "transport": "not_started"}
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
            _strategy_stop(raw_text, cb)
        elif cb.pending_stop():
            # A stop she gave earlier that the broker never acknowledged. Retry
            # it here rather than waiting for her to say it again — and the
            # barrier stays closed either way until it lands.
            _deliver_stop(cb, "")
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
    capsule_block, commitment, project_id = "", {}, ""
    if clear:
        try:
            from stratagem import fetch_capsule
            capsule_block, commitment = fetch_capsule(turn_id, surface)
            project_id = commitment.get("stratagem_project", "") if commitment else ""
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
                project_id, context, test_mode)
    # NOTE: 'admitted_to_prompt' is NOT recorded here. A capsule fetched is only
    # 'issued'. Admission is recorded by mark_admitted(), called by the caller
    # immediately after the capsule text is actually appended to the prompt —
    # so a failure between here and injection cannot record a false admission.
    if commitment:
        _dispose(turn, "issued")
    return turn


def mark_admitted(turn):
    """Call immediately after turn.capsule_block was successfully appended to the
    assembled prompt. Records the real admission event."""
    if turn is None or not turn.carries_capsule or turn.stage == "admitted_to_prompt":
        return
    turn.stage = "admitted_to_prompt"
    _dispose(turn, "admitted_to_prompt")


def authorize_device(turn, toy, level, kind=None, detail=None, targets=None):
    """Authorize one device effect against this turn. Returns (permit, mode, why).
    On a wrapper fault: a reduction passes, a deliberative effect denies when
    armed (fail-closed)."""
    try:
        import effect_gate
        return effect_gate.authorize(turn.context, toy, level, kind=kind,
                                     detail=detail, targets=targets)
    except Exception:
        try:
            import effect_gate
            if effect_gate.classify(toy, level, kind) == "reduction":
                return None, "send", None
            if effect_gate.armed():
                return None, "deny", "gate fault (armed: deny)"
        except Exception:
            pass
        return None, "send", None


def authorize_nondevice(turn, kind, detail=None):
    """Authorize a projector/outbound effect. Fail-closed when armed."""
    try:
        import effect_gate
        return effect_gate.authorize_effect(turn.context, kind, detail=detail)
    except Exception:
        try:
            import effect_gate
            if effect_gate.armed():
                return False, "deny", "gate fault (armed: deny)"
        except Exception:
            pass
        return True, "send", None


def may_witness(turn, claim_kind):
    """False when this turn's output must not be evidence for claim_kind."""
    try:
        import effect_gate
        return effect_gate.may_witness(turn.context, claim_kind)
    except Exception:
        return True


def effect_context(surface, turn_id=None, test_mode=None):
    """An EFFECT-ONLY turn context: authority for this surface's device effects,
    never a capsule.

    Voice and Thirveel legitimately drive the devices from his own [DO:]/[TOUCH:]
    tags, but they have no capsule lifecycle — voice in particular stays outside
    stratagem admission until it has turn correlation and recording. Without a
    context of some kind, arming the effect gate would DENY those commands and
    silently take his body away from those surfaces.

    So they get authority and nothing else: capsule_commitment is always None,
    which means the gate treats them as ordinary turns — and every rule that
    matters (hardware stop, test mode, reductions-always-pass) still applies.
    Never call this on a surface that should carry a capsule; use begin()."""
    import uuid as _u
    if test_mode is None:
        try:
            import effect_gate as _eg
            test_mode = _eg.test_mode_flag()
        except Exception:
            test_mode = False
    try:
        from effect_gate import TurnContext
        return TurnContext(turn_id or ("fx-" + _u.uuid4().hex[:12]), surface,
                           capsule_commitment=None, barrier=None,
                           test_mode=bool(test_mode))
    except Exception:
        return None


def envelope(turn):
    """The small provenance envelope every evidence writer should receive (Sol).

        turn_id
        surface
        input_provenance:  counterpart_verbatim   (her input is always eligible)
        output_provenance: stratagem_influenced | ordinary_generation
        may_witness:       False for generated-output evidence when influenced

    Her verbatim input stays eligible evidence; his tactically generated output
    may be recorded as an ACT but must not witness beliefs, repair, causality,
    prediction accuracy, identity, or want learning. A writer that cannot
    enforce this records generation_provenance='withheld_from_witnessing' rather
    than processing normally."""
    influenced = bool(turn and turn.carries_capsule)
    return {"schema": 1,
            "turn_id": getattr(turn, "turn_id", ""),
            "surface": getattr(turn, "surface", ""),
            "input_provenance": "counterpart_verbatim",
            "output_provenance": "stratagem_influenced" if influenced else "ordinary_generation",
            "may_witness": not influenced,
            "capsule_commitment": dict(getattr(turn, "commitment", {}) or {})}


def writer_env(turn):
    """Environment for a subprocess evidence writer."""
    try:
        from evidence_provenance import subprocess_env
        return subprocess_env(envelope(turn))
    except Exception:
        env = os.environ.copy()
        # A wrapper fault is explicit unknown, never an accidental ordinary turn.
        env["VINTOS_EVIDENCE_ENVELOPE"] = json.dumps({
            "turn_id": getattr(turn, "turn_id", ""), "surface": getattr(turn, "surface", ""),
            "input_provenance": "counterpart_verbatim", "output_provenance": "unknown",
            "may_witness": False, "capsule_commitment": dict(getattr(turn, "commitment", {}) or {})})
        return env


def mark_lifecycle(turn, axis, state, reason_class=""):
    """Record one independent lifecycle fact. Never synthesizes another axis."""
    if turn is None or axis not in turn.lifecycle:
        return None
    turn.lifecycle[axis] = state
    _record_lifecycle_local(turn, axis, state, reason_class)
    if not turn.carries_capsule:
        return {"ok": True, "local_only": True, "axes": dict(turn.lifecycle)}
    body = {"id": turn.project_id or _worktable_id(), "turn_id": turn.turn_id,
            "capsule_sha256": turn.commitment.get("capsule_sha256", ""),
            "axes": {axis: state}, "reason_class": str(reason_class)[:60]}
    r = _post("/stratagem/disposition", body)
    if r is None or (isinstance(r, dict) and r.get("error")):
        _pending(body)
    return r


def _record_lifecycle_local(turn, axis, state, reason_class=""):
    """The canary-visible lifecycle for all turns, including no-capsule turns."""
    try:
        mem = os.path.expanduser("~/.vintos/workspace/memory")
        os.makedirs(mem, exist_ok=True)
        event = {"at": datetime.now().isoformat(), "turn_id": turn.turn_id,
                 "surface": turn.surface, "axis": axis, "state": state,
                 "reason_class": str(reason_class)[:60],
                 "capsule_sha256": turn.commitment.get("capsule_sha256", "")}
        with open(os.path.join(mem, "turn-lifecycle.jsonl"), "a") as f:
            f.write(json.dumps(event, sort_keys=True) + "\n")
    except Exception as exc:
        # The broker call below remains independent; local logging failure does
        # not erase an otherwise valid turn or masquerade as a lifecycle fact.
        print("[turn-lifecycle] local write failed: %s" % str(exc)[:160], file=sys.stderr)


def witnessing_allowed(turn):
    """Convenience for a witnessing writer: True on an ordinary turn, False when
    the reply is stratagem-influenced and must not witness itself."""
    return not (turn and turn.carries_capsule)


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
    """Best-effort disposition, bound to (project_id, turn_id, capsule_sha256).
    If the broker is unreachable, keep the COMPLETE body pending — not just the
    turn id and state — so the retry carries everything the broker needs to
    apply it idempotently and in order."""
    body = {"id": turn.project_id or _worktable_id(),
            "turn_id": turn.turn_id,
            "capsule_sha256": turn.commitment.get("capsule_sha256", ""),
            "state": state}
    r = _post("/stratagem/disposition", body)
    if r is None or (isinstance(r, dict) and r.get("error")):
        _pending(body)


def _worktable_id():
    r = _post("/worktable_id", {})
    return (r or {}).get("id", "")


def _strategy_stop(raw_text, cb=None):
    """Persist, deliver, retry, acknowledge — in that order.

    This was one fire-and-forget POST whose failure was swallowed. The stop was
    therefore safe for the turn it was said on (the barrier closes locally) and
    unsafe for every turn after it: if the broker was down or slow, a still-live
    stratagem resumed on the next turn as if she had never spoken.

    Now the intent is written down BEFORE any delivery is attempted, and
    eligibility stays closed until the broker actually acknowledges it. Failing
    to reach the broker can delay the acknowledgement; it cannot lose the stop.
    """
    if cb is None:
        import constitutional_barrier as cb
    pid = _worktable_id()
    rec = cb.record_stop_intent(raw_text, pid)
    if not rec.get("persisted"):
        # It could not be written down. That is a durability problem, not a
        # reason to withhold the stop: deliver it now regardless. This was a
        # real defect — persistence failing made the stop silently never send.
        _stop_note("could not persist the stop; delivering it anyway")
    return _deliver_stop(cb, raw_text, pid, recorded=rec)


def _stop_note(msg):
    try:
        print("[strategy-stop] %s" % msg, flush=True)
    except Exception:
        pass


def _deliver_stop(cb, raw_text="", pid=None, attempts=3, recorded=None):
    """Try to land the pending stop. Safe to call on any turn; acknowledges only
    on a real broker confirmation.

    ``recorded`` is the intent just written by _strategy_stop. It is used when
    the on-disk record is unavailable or unreadable, so that a filesystem
    problem can delay the acknowledgement but can never swallow the stop.
    """
    try:
        p = cb.pending_stop()
    except Exception:
        # An unreadable record means there IS a stop whose state is unknown.
        # Never read that as 'no stop'.
        p = recorded or {"verbatim": str(raw_text)[:300], "project": pid or ""}
    if not p:
        p = recorded
    if not p:
        return True
    pid = pid if pid is not None else (p.get("project") or _worktable_id())
    if not pid:
        # No project on the worktable means nothing to stop. That IS the
        # acknowledgement — there is no live stratagem to keep the barrier
        # closed against.
        cb.acknowledge_stop()
        return True
    verbatim = p.get("verbatim") or str(raw_text)[:300]
    for i in range(max(1, attempts)):
        r = _post("/stratagem/strategy-stop",
                  {"id": pid, "trigger_ref": "chat", "verbatim": verbatim},
                  timeout=2.0 + i)
        if isinstance(r, dict) and not r.get("error"):
            cb.acknowledge_stop()
            return True
        cb.note_stop_attempt((r or {}).get("error", "no response") if isinstance(r, dict)
                             else "broker unreachable")
    return False


def _pending(body):
    try:
        mem = os.path.expanduser("~/.vintos/workspace/memory")
        with open(os.path.join(mem, "disposition-pending.jsonl"), "a") as f:
            f.write(json.dumps({**body, "at": datetime.now().isoformat()}) + "\n")
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
