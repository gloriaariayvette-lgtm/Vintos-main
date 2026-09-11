#!/usr/bin/env python3
"""effect_authority.py - who may dispatch, who may stop, and which lane a thing belongs to.

Review item 95 (2026-09-10). Dispatch lived in three places (the compiled DO/TOUCH grammar on the
avatar path, robot_core's queue, the direct toy_link calls) and stop in two (the hardware button's
desired state, robot_core.stop), with the sensor lane (reading her body, the ring, presence) tangled
into the same words as the actuator lane (moving a device). One table now says, for every lane:

  * who dispatches into it and through which gate,
  * what stops it, and what a stop means there,
  * whether it is a SENSOR lane (never dispatches anything) or an ACTUATOR lane.

assert_dispatch(lane, ...) is the single check a dispatcher makes before acting; it refuses a sensor
lane outright, refuses while the desired state is stopped, and otherwise defers to effect_gate.
"""
import os, sys

WS = os.path.expanduser("~/.vintos/workspace")

LANES = {
    "toys":     {"kind": "actuator", "dispatch": "toy_link.send / send_pattern via the compiled DO/TOUCH grammar",
                 "gate": "effect_gate.authorize (permit bound to target set, level and digest)",
                 "stop": "effect_gate desired_state stopped (the hardware button); a stop is durable and no permit outranks it"},
    "thruster": {"kind": "actuator", "dispatch": "toy_link.send with the thruster target",
                 "gate": "effect_gate.authorize; the 0.60 cap is a house law above the gate",
                 "stop": "the same durable stop; the cap is never raised by a stop or a resume"},
    "robot":    {"kind": "actuator", "dispatch": "robot_core.queue_command (bounded, one action)",
                 "gate": "effect_gate.authorize_effect; an unreachable gate refuses a deliberative move (74)",
                 "stop": "robot_core.stop jumps the queue and needs nothing"},
    "avatar":   {"kind": "actuator", "dispatch": "avatar_stage kick/scene gate, per-turn slot",
                 "gate": "the turn's own admission (one render per slot)",
                 "stop": "a new generation token supersedes; a stopped house stops the render"},
    "outward":  {"kind": "actuator", "dispatch": "deliver.deliver / the outreach cron",
                 "gate": "send_policy.may_send (quiet hours, caps, cooldown, receipts)",
                 "stop": "the cap or the receipt; there is no undo once it is sent"},
    "somatic":  {"kind": "sensor", "dispatch": None,
                 "gate": "none: a sensor lane never dispatches",
                 "stop": "reading stops when the device is gone; a stop here means no reading, never an effect"},
    "ring":     {"kind": "sensor", "dispatch": None, "gate": "none", "stop": "a stale reading asserts nothing (heart_rate.status)"},
    "presence": {"kind": "sensor", "dispatch": None, "gate": "none", "stop": "a stale reading asserts nothing (home_presence.context_line)"},
}


def lane_of(target):
    t = str(target or "").lower()
    if t in ("mission", "tenera", "ridge", "lush", "toy"): return "toys"
    if "thrust" in t: return "thruster"
    if "robot" in t or t in ("pi", "head"): return "robot"
    if "avatar" in t or "scene" in t or "render" in t: return "avatar"
    if t in ("ntfy", "outreach", "deliver", "send"): return "outward"
    if "somatic" in t: return "somatic"
    if "heart" in t or "ring" in t: return "ring"
    if "presence" in t: return "presence"
    return ""


def dispatch(lane, context=None, target="", level=0, kind=None, detail=None,
             permit=None, digest=None, authority=None):
    """(allowed, mode, reason), preserving each lane's existing authority.

    This is a dispatch check, not an authorization grant. Toy permits are checked
    against their exact payload here and consumed by their existing coordinator.
    Callback lanes must supply their existing policy; simulation never dispatches.
    """
    spec = LANES.get(lane)
    if spec is None:
        return False, "deny", "unknown lane %r: a dispatcher must name its lane" % lane
    if spec["kind"] == "sensor":
        return False, "deny", "%s is a sensor lane; it reads and never dispatches" % lane
    try:
        if lane in ("outward", "avatar"):
            if authority is None:
                return False, "deny", "no authority given"
            result = authority()
            if isinstance(result, tuple) and len(result) == 3:
                ok, mode, why = result
                return bool(ok) and mode == "send", mode, why
            ok, why = result if isinstance(result, tuple) else (bool(result), "")
            return bool(ok), "send" if ok else "deny", why
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import effect_gate
        if lane == "robot":
            ok, mode, why = effect_gate.authorize_effect(context, kind, detail=detail)
            return bool(ok) and mode == "send", mode, why
        if effect_gate.hardware_stopped() and float(level or 0) > 0:
            return False, "deny", "the house is stopped; only a reduction passes"
        if permit is not None:
            ok, why = effect_gate.dispatch_check(permit, target, level, kind, digest=digest)
            return bool(ok), "send" if ok else "deny", why
        issued, mode, why = effect_gate.authorize(context, target or lane, level,
                                                kind=kind, detail=detail, digest=digest)
        return mode == "send", mode, why
    except Exception as exc:
        # Stops remain available through a fault. Missing authority never grants
        # a new deliberative effect, even when its normal policy is disarmed.
        reduction = kind in ("stop", "halt", "release", "reduce")
        if lane in ("toys", "thruster"):
            try: reduction = float(level) == 0 and kind in (None, "stop", "halt", "release", "reduce", "rotate")
            except (TypeError, ValueError): reduction = False
        if reduction and lane in ("toys", "thruster", "robot"):
            return True, "send", "reduction remains available during authority fault"
        return False, "deny", "authority unavailable: " + str(exc)[:160]


def assert_dispatch(lane, context=None, target="", level=0, kind=None):
    ok, mode, why = dispatch(lane, context=context, target=target, level=level, kind=kind)
    return ok, why or mode


def table():
    return {k: dict(v) for k, v in LANES.items()}


if __name__ == "__main__":
    for k, v in LANES.items():
        print("%-9s %-9s dispatch: %s" % (k, v["kind"], v["dispatch"] or "-"))
        print("%-9s %-9s stop:     %s" % ("", "", v["stop"]))
