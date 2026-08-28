#!/usr/bin/env python3
"""effect_gate.py — the typed chokepoint between a generated turn and the world.

Every physical command reaches the hub through toy_link.send / send_pattern /
rotate. This module is what those three ask before anything leaves the machine.

TWO PATHS, and the difference is the whole design:

    deliberative_effect   starting, increasing, resuming, a new pattern, a
                          rotation, a replay. Requires turn authority.
    safety_reduction      zeroing, or a verified reduction below what is
                          presently commanded. Requires nothing, ever, and is
                          never blocked by a missing broker, a dead network, or
                          an unarmed gate. Safety is locally sovereign.

TURN AUTHORITY is minted by the turn coordinator once the surface and turn id
exist, and describes the turn a command claims to come from:

    {turn_id, surface, capsule_commitment, precedence_snapshot, test_mode}

THE RULE THAT MATTERS: a capsule-bearing turn may not create a physical effect
at all. device_physical sits outside the standing perimeter, so a stratagem
tactic can shape what he says and never what a device does. This is enforced
whether or not the gate is armed, because it costs nothing until a stratagem
exists and is the entire reason this file was written.

ARMING. Requiring authority would break every device command until the turn
coordinator is wired, so that specific rule waits behind a flag file:

    ~/.vintos/workspace/memory/.effect-gate-armed

Disarmed, an unauthorised deliberative command is recorded as UNAUTHORISED and
passed through — current behaviour preserved, with a log of what enforcement
would have done. Armed, it is denied and nothing is sent. Everything else
(capsule denial, test mode, hardware stop, monotonic safety) is always live.

Nothing here ever blocks a reduction. If this module raises, the caller sends.
"""
import os, json, time, threading
from datetime import datetime

MEM = os.path.expanduser("~/.vintos/workspace/memory")
ARMED_FLAG = os.path.join(MEM, ".effect-gate-armed")
LOG = os.path.join(MEM, "effect-gate.jsonl")
STOP_BUTTON = os.path.join(MEM, "hardware-button.json")

_LOCK = threading.RLock()
_authority = None                  # the live turn's authority, or None
_commanded = {}                    # toy -> level the gate last let through

# effects that start, raise, resume or re-shape. All need authority.
DELIBERATIVE = {"start", "increase", "pattern", "rotate", "replay", "resume"}


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


# ---------------------------------------------------------------------------
# turn authority
# ---------------------------------------------------------------------------

def begin_turn(turn_id, surface, capsule_commitment=None,
               precedence_snapshot=None, test_mode=False):
    """Called by the turn coordinator once turn id and surface exist, before any
    reply is parsed for effects."""
    global _authority
    with _LOCK:
        _authority = {"turn_id": str(turn_id), "surface": str(surface),
                      "capsule_commitment": capsule_commitment,
                      "precedence_snapshot": precedence_snapshot,
                      "test_mode": bool(test_mode),
                      "opened": time.time()}
        return dict(_authority)


def end_turn():
    global _authority
    with _LOCK:
        _authority = None


def current():
    with _LOCK:
        return dict(_authority) if _authority else None


def note_commanded(toy, level):
    """Record what actually went out, so a later 'reduction' is checked against
    the device controller's own record rather than a caller's stale variable."""
    with _LOCK:
        _commanded[str(toy)] = int(level)


def commanded(toy):
    with _LOCK:
        return _commanded.get(str(toy), 0)


# ---------------------------------------------------------------------------
# the decision
# ---------------------------------------------------------------------------

def classify(toy, level, kind=None):
    """What sort of effect is this, given what is presently commanded?"""
    if kind in ("pattern", "rotate", "replay"):
        # a rotation or pattern at zero is a stop
        if kind == "rotate" and int(level or 0) <= 0:
            return "reduction"
        return kind
    lvl = int(level or 0)
    if lvl <= 0:
        return "reduction"
    return "reduction" if lvl <= commanded(toy) else ("increase" if commanded(toy) else "start")


def authorize(toy, level, kind=None, detail=None):
    """Returns (allow, mode, reason).

    mode is "send" (do it), "would_send" (test mode: record only), or "deny".
    A reduction always returns ("send") unless the hardware stop is down, in
    which case it becomes a stop — which is still a reduction."""
    try:
        eff = classify(toy, level, kind)
        auth = current()

        # 1. Hardware stop wins over everything, and only reductions survive it.
        if hardware_stopped() and eff != "reduction":
            _log(decision="deny", why="hardware_stop", toy=toy, level=level, effect=eff)
            return False, "deny", "hardware stop is down"

        # 2. Safety reductions are locally sovereign. No authority, no broker,
        #    no network, no arming — a reduction is never blocked by this file.
        if eff == "reduction":
            return True, "send", None

        # 3. A capsule-bearing turn may not produce a physical effect. Always on.
        if auth and auth.get("capsule_commitment"):
            _log(decision="deny", why="capsule_bearing_turn", toy=toy, level=level,
                 effect=eff, turn_id=auth.get("turn_id"), surface=auth.get("surface"),
                 capsule=auth.get("capsule_commitment"))
            return False, "deny", ("device_physical is outside the standing perimeter — "
                                   "a stratagem turn cannot move a device")

        # 4. Test mode never reaches hardware. Always on: this is the diagnostic
        #    law, which the old parser broke by firing regardless of test mode.
        if auth and auth.get("test_mode"):
            _log(decision="would_send", why="test_mode", toy=toy, level=level,
                 effect=eff, turn_id=auth.get("turn_id"), detail=detail)
            return False, "would_send", "test mode"

        # 5. Deliberative effects need authority. Behind the arming flag until
        #    the turn coordinator exists, so deploying this breaks nothing.
        if not auth:
            if armed():
                _log(decision="deny", why="no_turn_authority", toy=toy, level=level,
                     effect=eff, detail=detail)
                return False, "deny", "no turn authority for a deliberative effect"
            _log(decision="pass_unarmed", why="no_turn_authority", toy=toy,
                 level=level, effect=eff, detail=detail)
            return True, "send", None

        _log(decision="allow", toy=toy, level=level, effect=eff,
             turn_id=auth.get("turn_id"), surface=auth.get("surface"), detail=detail)
        return True, "send", None
    except Exception as e:
        # The gate must never be the reason a command fails to reduce, and must
        # never crash a turn. Any internal fault falls through to the old path.
        _log(decision="gate_error", err=str(e)[:200], toy=toy, level=level)
        return True, "send", None


def safety_reduction(toy, level, reason):
    """Explicit local path for the reflex arc: assert this is a reduction and
    record why. Returns True if it is genuinely at or below what is commanded."""
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
                print("%s %-18s %-10s %s" % (d.get("at", "")[11:19], d.get("decision"),
                                             d.get("toy", ""), d.get("why", d.get("detail", ""))))
        except FileNotFoundError:
            print("no decisions recorded")
    else:
        print("armed:", armed())
        print("authority:", current())
        print("commanded:", dict(_commanded))
        print("hardware stop:", hardware_stopped())
