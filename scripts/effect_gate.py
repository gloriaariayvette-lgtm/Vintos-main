#!/usr/bin/env python3
"""effect_gate.py — the typed chokepoint between a generated turn and the world.

Every physical command reaches the hub through toy_link.send / send_pattern /
rotate. This module is what those ask before anything leaves the machine.

NO AMBIENT AUTHORITY. There is no process-global "current turn". Two surfaces
(chat, avatar) run concurrently, and a single global slot let one surface's
authority be live while the other parsed effects. Instead:

    context  = TurnContext(...)                     immutable, made by the coordinator
    permit   = authorize(context, toy, level, kind) an EffectPermit, or a denial
    toy_link.execute(effect, permit)                explicit, survives concurrency

A permit is immutable and bounded. A long-running pattern's later motor ticks
run under the permit it was started with; closing the turn does not invalidate
an execution envelope already authorized.

TWO PATHS, and the difference is the whole design:

    deliberative   start, increase, resume, pattern, rotation, replay.
                   Needs a permit from a clean TurnContext.
    reduction      zeroing, or a verified drop below what is presently
                   commanded. Needs NOTHING, ever, and is the ONLY thing that
                   fails open — not a missing permit, not an armed gate, not a
                   dead broker, not an internal fault. Safety is locally
                   sovereign.

ALWAYS LIVE, armed or not:
  - a capsule-bearing turn cannot produce ANY physical effect (device_physical
    is outside the standing perimeter)
  - test mode records WOULD_SEND and reaches no hardware
  - the hardware stop blocks every increase

BEHIND THE ARMING FLAG (~/.vintos/workspace/memory/.effect-gate-armed):
  denying a deliberative effect that carries no valid permit. Disarmed, an
  unpermitted deliberative command is recorded UNARMED_PASS and sent, so
  deploying this changes nothing until the coordinator exists AND the flag is
  set. When ARMED, a missing permit OR an internal fault DENIES a deliberative
  effect — only a verified reduction may fall through.
"""
import os, json, time, threading, uuid
from datetime import datetime, timedelta

MEM = os.path.expanduser("~/.vintos/workspace/memory")
ARMED_FLAG = os.path.join(MEM, ".effect-gate-armed")
LOG = os.path.join(MEM, "effect-gate.jsonl")
STOP_BUTTON = os.path.join(MEM, "hardware-button.json")
TEST_MODE_FLAG = os.path.join(MEM, ".test-mode")   # bin/test-mode.sh touches this

DELIBERATIVE_KINDS = {"start", "increase", "pattern", "rotate", "replay", "resume"}

_commanded = {}                       # toy -> last level the gate let through
_commanded_lock = threading.Lock()
_target_locks = {}                    # toy -> Lock, for per-device serialization
_target_lock_guard = threading.Lock()
_execution_owners = {}                # toy -> effect_id for the current deliberative lease
_execution_owner_lock = threading.Lock()


# ---------------------------------------------------------------------------
# immutable turn context and effect permit
# ---------------------------------------------------------------------------

class TurnContext:
    """What a turn is, fixed at construction. Passed explicitly; never stored
    in a module global. capsule_commitment is truthy exactly when this turn
    carries a stratagem tactic."""
    __slots__ = ("turn_id", "surface", "capsule_commitment", "barrier",
                 "test_mode", "opened")

    def __init__(self, turn_id, surface, capsule_commitment=None,
                 barrier=None, test_mode=False):
        self.turn_id = str(turn_id)
        self.surface = str(surface)
        self.capsule_commitment = capsule_commitment or None
        self.barrier = barrier
        self.test_mode = bool(test_mode)
        self.opened = time.time()

    def provenance(self):
        if not self.capsule_commitment:
            return {}
        return {"generation_provenance": "stratagem_influenced",
                "capsule_commitment": self.capsule_commitment,
                "turn_id": self.turn_id}


MAX_LEASE_SECONDS = 30 * 60   # hard safety ceiling for an until-replaced lease

# what execution kind each permit kind authorizes. A pattern permit covers both
# the pattern start and the scalar ticks its background loop emits; a plain start
# permit covers only a scalar send; rotate covers only rotate.
_KIND_COMPATIBLE = {
    "start":   frozenset({"start"}),
    "pattern": frozenset({"pattern", "start"}),
    "rotate":  frozenset({"rotate"}),
    "replay":  frozenset({"replay", "pattern", "start"}),
    "resume":  frozenset({"resume", "pattern", "start"}),
    "increase": frozenset({"increase", "start"}),
}


class EffectPermit:
    """An immutable, bounded, single-use authorization for one deliberative
    effect. It binds the exact effect it authorizes — kind, the exact target
    set, the maximum intensity, and a parameter digest — so a permit granted at
    level 12 cannot be reused to run a named pattern peaking at 18, and a permit
    for one toy cannot fire another. consume() guards the START; the running
    execution then holds a separate bounded lease (see ExecutionLease)."""
    __slots__ = ("effect_id", "turn_id", "surface", "kind", "targets",
                 "maximum", "digest", "duration", "expires", "lease_mode",
                 "capsule_commitment", "_consumed", "_lock")

    def __init__(self, turn_id, surface, kind, targets, maximum, duration,
                 digest=None):
        self.effect_id = uuid.uuid4().hex
        self.turn_id = turn_id
        self.surface = surface
        self.kind = kind
        # exact target set: "both"/broadcast is expanded by the caller
        self.targets = frozenset(targets if isinstance(targets, (set, frozenset, list, tuple))
                                 else [targets])
        self.maximum = int(maximum)
        self.digest = digest
        self.duration = int(duration or 0)
        self.lease_mode = "bounded" if self.duration else "until_replaced"
        secs = self.duration or MAX_LEASE_SECONDS
        self.expires = (datetime.now() + timedelta(seconds=secs)).isoformat()
        self.capsule_commitment = None      # a permit never carries a capsule
        self._consumed = False
        self._lock = threading.Lock()

    def valid_now(self):
        return datetime.now().isoformat() <= self.expires

    def covers(self, toy, level, kind, digest=None):
        """True iff this permit authorizes THIS command: still valid, the toy in
        the target set, the level within the authorized maximum, the kind
        compatible, and — when the caller supplies one — the transport digest
        matching what was authorized.

        Kind compatibility (a permit authorizes only what it was granted for):
            start   -> scalar send only
            pattern -> a pattern start AND its scalar execution ticks
            rotate  -> rotate only
        """
        if not self.valid_now():
            return False
        if toy not in self.targets and "both" not in self.targets:
            return False
        if int(level or 0) > self.maximum:
            return False
        if not _KIND_COMPATIBLE.get(self.kind, frozenset()).__contains__(kind or "start"):
            return False
        # A digest-bound permit is unusable unless the executor carries the
        # exact digest. Omitting it must not turn a binding into a wildcard.
        if self.digest is not None and digest != self.digest:
            return False
        return True

    def consume(self):
        """Authorizes one execution start; later ticks are the same action."""
        with self._lock:
            if self._consumed:
                return False
            self._consumed = True
            return True

    def lease(self):
        """A separate bounded execution lease for a background pattern thread, so
        expiry can be checked by the executor and the turn's close cannot revoke
        an already-started, still-legal execution."""
        return ExecutionLease(self.effect_id, self.targets, self.maximum,
                              self.expires, self.lease_mode)

    def as_dict(self):
        return {"effect_id": self.effect_id, "turn_id": self.turn_id,
                "surface": self.surface, "kind": self.kind,
                "targets": sorted(self.targets), "maximum": self.maximum,
                "digest": self.digest, "duration": self.duration,
                "lease_mode": self.lease_mode, "expires": self.expires,
                "capsule_commitment": None}


class ExecutionLease:
    """What a running pattern thread holds. Bounded and checkable; the executor
    stops and reduces to zero when it expires or the hardware stop is down."""
    __slots__ = ("effect_id", "targets", "maximum", "expires", "mode")

    def __init__(self, effect_id, targets, maximum, expires, mode):
        self.effect_id = effect_id
        self.targets = frozenset(targets)
        self.maximum = int(maximum)
        self.expires = expires
        self.mode = mode

    def live(self):
        if hardware_stopped():
            return False
        return datetime.now().isoformat() <= self.expires


def claim_execution(targets, effect_id):
    """Make effect_id the current execution owner for each exact target."""
    if not effect_id:
        return
    with _execution_owner_lock:
        for target in targets:
            _execution_owners[str(target)] = str(effect_id)


def execution_owned_by(target, effect_id):
    """Whether effect_id still owns target after any replacement commands."""
    with _execution_owner_lock:
        return bool(effect_id) and _execution_owners.get(str(target)) == str(effect_id)


def release_execution(target, effect_id=None):
    """Release target ownership, optionally only if effect_id still owns it."""
    with _execution_owner_lock:
        target = str(target)
        if effect_id is None or _execution_owners.get(target) == str(effect_id):
            _execution_owners.pop(target, None)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def armed():
    return os.path.exists(ARMED_FLAG)


def _log(**row):
    try:
        os.makedirs(MEM, exist_ok=True)
        row["at"] = datetime.now().isoformat()
        with open(LOG, "a") as f:
            f.write(json.dumps(row) + "\n")
    except Exception:
        pass


def hardware_stopped():
    try:
        return bool(json.load(open(STOP_BUTTON)).get("stopped"))
    except Exception:
        return False


def test_mode_flag():
    """The diagnostic bracket's flag file. A gateway-level defense independent of
    any TurnContext, because diagnostics call toy_link directly — this is the
    law that a diagnostic must never fire the hardware, which the old parser
    broke by sending 'regardless of test-mode'."""
    return os.path.exists(TEST_MODE_FLAG)


def note_commanded(toy, level):
    with _commanded_lock:
        _commanded[str(toy)] = int(level)


def commanded(toy):
    with _commanded_lock:
        return _commanded.get(str(toy), 0)


def target_lock(toy):
    """Serialize commands to one physical target. Two legitimate ordinary turns
    can command the same device at once; the later authorized command holds the
    lease. Callers take this around a send."""
    with _target_lock_guard:
        return _target_locks.setdefault(str(toy), threading.Lock())


def classify(toy, level, kind=None):
    if kind in ("pattern", "rotate", "replay", "resume"):
        if kind == "rotate" and int(level or 0) <= 0:
            return "reduction"
        return "deliberative"
    lvl = int(level or 0)
    if lvl <= 0:
        return "reduction"
    return "reduction" if lvl <= commanded(toy) else "deliberative"


# ---------------------------------------------------------------------------
# the decision — always takes an explicit context (or None for a bare reduction)
# ---------------------------------------------------------------------------

def authorize(context, toy, level, kind=None, detail=None, targets=None, digest=None):
    """Returns (permit_or_None, mode, reason).

    targets: the exact, already-expanded target set this effect will touch
    (a broadcast alias like "both" must be expanded by the caller before
    authorizing). Defaults to {toy}. The granted permit binds this set, the
    level as its maximum, and the digest, so it cannot be reused for a larger
    effect.

    mode: "send" (a reduction, or a granted deliberative permit),
          "would_send" (test mode: record only),
          "deny".
    For a reduction the returned permit is None and mode is "send" — reductions
    need no permit and are never blocked. Only a deliberative effect returns an
    EffectPermit on success.

    context may be None for a bare safety reduction. A deliberative effect with
    context=None is unpermitted."""
    try:
        eff = classify(toy, level, kind)

        # 1. reductions: locally sovereign. Nothing blocks them. The hardware
        #    stop only makes them more urgent, never less permitted.
        if eff == "reduction":
            return None, "send", None

        # from here it is deliberative.

        # 2. hardware stop blocks every increase.
        if hardware_stopped():
            _log(decision="deny", why="hardware_stop", toy=toy, level=level, kind=kind)
            return None, "deny", "hardware stop is down"

        # 2b. the diagnostic bracket's flag file. Gateway-level, context-free:
        #     a diagnostic that forgot to pass a test-mode context still cannot
        #     fire the hardware. Reductions already returned above.
        if test_mode_flag():
            _log(decision="would_send", why="test_mode_flag", toy=toy, level=level,
                 kind=kind, detail=detail)
            return None, "would_send", "test mode (flag file)"

        # 3. a capsule-bearing turn may not move a device. Always on.
        if context is not None and context.capsule_commitment:
            _log(decision="deny", why="capsule_bearing_turn", toy=toy, level=level,
                 kind=kind, turn_id=context.turn_id, surface=context.surface,
                 capsule=context.capsule_commitment)
            return None, "deny", ("device_physical is outside the standing perimeter "
                                  "— a stratagem turn cannot move a device")

        # 4. test mode never reaches hardware. Always on.
        if context is not None and context.test_mode:
            _log(decision="would_send", why="test_mode", toy=toy, level=level,
                 kind=kind, turn_id=context.turn_id, detail=detail)
            return None, "would_send", "test mode"

        # 5. deliberative needs a clean context. Missing context:
        #    ARMED -> deny (a fault is not permission).  DISARMED -> pass+log.
        if context is None:
            if armed():
                _log(decision="deny", why="no_context", toy=toy, level=level, kind=kind)
                return None, "deny", "no turn context for a deliberative effect"
            _log(decision="unarmed_pass", why="no_context", toy=toy, level=level,
                 kind=kind, detail=detail)
            return None, "send", None

        permit = EffectPermit(context.turn_id, context.surface,
                              kind or "start", targets or {toy}, level,
                              _dur(detail), digest=digest)
        _log(decision="permit", effect_id=permit.effect_id, toy=toy, level=level,
             kind=kind, turn_id=context.turn_id, surface=context.surface, detail=detail)
        return permit, "send", None
    except Exception as e:
        # ONLY a reduction may fail open. A deliberative fault, armed, denies.
        try:
            if classify(toy, level, kind) == "reduction":
                _log(decision="gate_error_reduction_passed", err=str(e)[:160],
                     toy=toy, level=level)
                return None, "send", None
        except Exception:
            pass
        if armed():
            _log(decision="deny", why="gate_error", err=str(e)[:160], toy=toy, level=level)
            return None, "deny", "gate fault on a deliberative effect (armed: deny)"
        _log(decision="gate_error_unarmed_passed", err=str(e)[:160], toy=toy, level=level)
        return None, "send", None


def _dur(detail):
    try:
        for tok in str(detail or "").replace(":", " ").split():
            if tok.endswith("s") and tok[:-1].isdigit():
                return int(tok[:-1])
    except Exception:
        pass
    return 0


def authorize_effect(context, kind, detail=None):
    """Non-device typed effects that still reach the world or the record — a
    projector render, an outbound message, a queued video. Same rules; when
    ARMED, a missing context denies (these are never reductions)."""
    try:
        if context is not None and context.capsule_commitment:
            _log(decision="deny", why="capsule_bearing_turn", effect=kind,
                 turn_id=context.turn_id, detail=detail)
            return False, "deny", ("%s is outside the standing perimeter for a "
                                   "stratagem turn" % kind)
        if context is not None and context.test_mode:
            _log(decision="would_send", why="test_mode", effect=kind, detail=detail)
            return False, "would_send", "test mode"
        if context is None:
            if armed():
                _log(decision="deny", why="no_context", effect=kind, detail=detail)
                return False, "deny", "no turn context for %s" % kind
            _log(decision="unarmed_pass", why="no_context", effect=kind, detail=detail)
            return True, "send", None
        _log(decision="allow", effect=kind, detail=detail, turn_id=context.turn_id)
        return True, "send", None
    except Exception as e:
        _log(decision="gate_error", err=str(e)[:160], effect=kind)
        if armed():
            return False, "deny", "gate fault (armed: deny)"
        return True, "send", None


# ---------------------------------------------------------------------------
# provenance — computed from the context, never from a global
# ---------------------------------------------------------------------------

def provenance(context):
    """{} on an ordinary turn; a stamp on a stratagem-influenced one. Sol: the
    factual record is marked, not suppressed, and a tactically generated reply
    may never be independent evidence for the belief model, identity, repair
    success, causal graduation, want learning, or prediction leverage."""
    return context.provenance() if isinstance(context, TurnContext) else {}


def may_witness(context, claim_kind):
    """False when this turn's output must not be evidence for claim_kind."""
    return not provenance(context)


def safety_reduction(toy, level, reason):
    """Explicit local path for the reflex arc. Returns True iff genuinely at or
    below what is presently commanded — a disguised increase is refused here."""
    lvl = int(level or 0)
    ok = lvl <= commanded(toy)
    _log(decision="safety_reduction" if ok else "safety_reduction_refused",
         toy=toy, level=lvl, commanded=commanded(toy), reason=str(reason)[:120])
    return ok


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "tail":
        try:
            for line in list(open(LOG))[-20:]:
                d = json.loads(line)
                print("%s %-26s %-9s %s" % (d.get("at", "")[11:19], d.get("decision"),
                                            d.get("toy", d.get("effect", "")),
                                            d.get("why", d.get("detail", ""))))
        except FileNotFoundError:
            print("no decisions recorded")
    else:
        print("armed:", armed())
        print("hardware stop:", hardware_stopped())
        print("commanded:", dict(_commanded))
