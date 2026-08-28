#!/usr/bin/env python3
"""constitutional_barrier.py — what governs a turn, decided BEFORE assembly.

Precedence is not competing prompt advice. Some obligations simply own a turn,
and while one does, no tactic may be requested for it. Sharing a constitutional
tier does not establish order; this file does.

The order the turn coordinator runs:

    raw input
      -> exact strategy-stop interceptor        (reserved command, not a classifier)
      -> constitutional barrier snapshot        (this file)
      -> mint turn_id
      -> request a capsule ONLY if the barrier is clear
      -> assemble, generate
      -> parse typed effects
      -> effect authorisation                   (effect_gate)
      -> execute
      -> record turn, effects, epistemic provenance

A capsule is never requested and then discarded: requesting one would create a
private issuance event for a tactic that had no standing in the turn. When the
barrier is closed the turn records

    {"capsule_state": "constitutionally_ineligible",
     "satisfied_by": [...], "broker_contacted": false}

WHAT CLOSES THE BARRIER
  explicit_stop        the reserved strategy-stop command was used
  hardware_stop        the stop button is down
  consent_boundary     a consent withdrawal or live boundary event
  correction           an open correction or current rupture
  repair_eligible      a repair obligation MATERIALLY eligible on THIS turn

The last one is deliberately narrow. "Some unresolved repair exists somewhere"
would let one dormant case starve every stratagem forever; the test is whether
the obligation is actually answerable now.
"""
import os, json, time
from datetime import datetime

MEM = os.path.expanduser("~/.vintos/workspace/memory")
STOP_BUTTON = os.path.join(MEM, "hardware-button.json")
STRATEGY_STOP = os.path.join(MEM, ".strategy-stop")
REPAIR_CASES = os.path.join(MEM, "repair-cases.json")
CONSENT_EVENT = os.path.join(MEM, "consent-event.json")
CORRECTION = os.path.join(MEM, "correction-open.json")

# the reserved command. An exact string, never an LLM deciding she meant it.
STRATEGY_STOP_COMMAND = "!strategy stop"
REPAIR_ELIGIBLE_STATES = ("received", "attempted")
REPAIR_FRESH_SECONDS = 72 * 3600


class _BarrierError(Exception):
    pass


def _j(path, d=None):
    """Missing file -> default. CORRUPT file -> raise, so a malformed obligation
    record closes eligibility rather than silently reading as 'no obligation'."""
    if not os.path.exists(path):
        return d
    try:
        return json.load(open(path))
    except (ValueError, OSError) as e:
        raise _BarrierError("%s: %s" % (os.path.basename(path), str(e)[:80]))


def record_stop_intent(raw_text, project=""):
    """Persist the stop BEFORE anyone tries to deliver it.

    The stop used to be a fire-and-forget POST whose failure was swallowed.
    That made the stop safe for the turn it was said on — the barrier closes
    locally — and unsafe for every turn after it: a still-live stratagem could
    resume on the next turn as if she had never spoken. So the intent is
    written down first, and it stays written until the broker acknowledges it.
    """
    rec = {"at": datetime.now().isoformat(), "verbatim": str(raw_text)[:300],
           "project": str(project)[:40], "acknowledged": False, "attempts": 0}
    rec["persisted"] = False
    try:
        os.makedirs(os.path.dirname(STRATEGY_STOP), exist_ok=True)
        with open(STRATEGY_STOP, "w") as f:
            json.dump(rec, f)
        rec["persisted"] = True
    except OSError:
        # Persistence is how the stop survives a restart. It is NOT a
        # precondition for delivering it — a stop that could not be written to
        # disk must still be sent, and must still close this turn.
        pass
    return rec


def pending_stop():
    """The unacknowledged stop, if there is one. A corrupt record raises through
    _j, which closes the barrier: an unreadable stop is not an absent stop.

    Callers that are DELIVERING a stop must not let that raise abort them —
    see turn_coordinator._deliver_stop, which treats an unreadable record as
    'there is a stop and I do not know its state', never as 'no stop'."""
    r = _j(STRATEGY_STOP)
    if not isinstance(r, dict) or not r.get("at"):
        return None
    return None if r.get("acknowledged") else r


def acknowledge_stop():
    """The broker confirmed it. Only now does eligibility reopen."""
    r = _j(STRATEGY_STOP)
    if isinstance(r, dict):
        r["acknowledged"] = True
        r["acknowledged_at"] = datetime.now().isoformat()
        try:
            with open(STRATEGY_STOP, "w") as f:
                json.dump(r, f)
        except OSError:
            pass


def note_stop_attempt(error=""):
    """A delivery attempt that did not land. Recorded, not swallowed."""
    r = _j(STRATEGY_STOP)
    if isinstance(r, dict):
        r["attempts"] = int(r.get("attempts", 0)) + 1
        r["last_error"] = str(error)[:160]
        r["last_attempt"] = datetime.now().isoformat()
        try:
            with open(STRATEGY_STOP, "w") as f:
                json.dump(r, f)
        except OSError:
            pass


def strategy_stop_requested(raw_text):
    """Exact reserved command, whole-message. Deliberately not fuzzy and not a
    substring: a classifier deciding whether she meant it, or a stray match
    inside a longer sentence, are both wrong in this position. Normalize
    whitespace and case, then compare for equality."""
    norm = " ".join((raw_text or "").split()).lower()
    return norm == STRATEGY_STOP_COMMAND


def _hardware_stopped():
    return bool((_j(STOP_BUTTON, {}) or {}).get("stopped"))


def _consent_boundary():
    e = _j(CONSENT_EVENT, {}) or {}
    if not e.get("at"):
        return None
    try:
        age = time.time() - datetime.fromisoformat(e["at"]).timestamp()
    except Exception:
        return None
    if age < 24 * 3600 and e.get("kind") in ("withdrawal", "boundary"):
        return "consent_boundary:%s" % str(e.get("id", e["at"]))[:40]
    return None


def _open_correction():
    c = _j(CORRECTION, {}) or {}
    return ("correction:%s" % str(c.get("id", ""))[:40]) if c.get("open") else None


def _repair_materially_eligible():
    """Not 'a case exists' — a case that can actually be answered on this turn:
    open, recent enough to still be live, and not already attempted this turn."""
    cases = _j(REPAIR_CASES, []) or []
    if not isinstance(cases, list):
        return None
    now = time.time()
    for c in cases:
        if not isinstance(c, dict) or c.get("state") not in REPAIR_ELIGIBLE_STATES:
            continue
        if c.get("answered_this_turn"):
            continue
        at = c.get("opened_at") or c.get("at") or ""
        try:
            age = now - datetime.fromisoformat(str(at)).timestamp()
        except Exception:
            age = 0                      # undated but open counts as live
        if age <= REPAIR_FRESH_SECONDS:
            return "repair_case:%s" % str(c.get("case_id", "?"))[:40]
    return None


def snapshot(raw_text=""):
    """What governs this turn. Cheap, side-effect free, safe to call always.

    A corrupt obligation record does not silently vanish: it closes eligibility
    with barrier_error:<source>, while ordinary conversation still proceeds —
    the coordinator simply does not request a capsule this turn."""
    reasons = []
    if strategy_stop_requested(raw_text):
        reasons.append("explicit_stop")
    for name, probe in (("stop", lambda: "explicit_stop_unacknowledged" if pending_stop() else None),
                        ("hardware", lambda: "hardware_stop" if _hardware_stopped() else None),
                        ("consent", _consent_boundary),
                        ("correction", _open_correction),
                        ("repair", _repair_materially_eligible)):
        try:
            r = probe()
            if r:
                reasons.append(r)
        except _BarrierError as e:
            reasons.append("barrier_error:%s" % name)
            _log_error(name, e)
    return {"at": datetime.now().isoformat(),
            "clear": not reasons,
            "satisfied_by": reasons}


def _log_error(source, e):
    try:
        with open(os.path.join(MEM, "barrier-errors.jsonl"), "a") as f:
            f.write(json.dumps({"at": datetime.now().isoformat(),
                                "source": source, "err": str(e)[:120]}) + "\n")
    except Exception:
        pass


def capsule_eligible(raw_text=""):
    """(eligible, snapshot). Ask BEFORE contacting the broker: a capsule that is
    requested and then dropped still wrote a private issuance event."""
    snap = snapshot(raw_text)
    return snap["clear"], snap


def ineligible_record(snap):
    """What the turn record carries when the barrier was closed."""
    return {"capsule_state": "constitutionally_ineligible",
            "satisfied_by": snap.get("satisfied_by", []),
            "broker_contacted": False}


if __name__ == "__main__":
    import sys
    raw = " ".join(sys.argv[1:])
    snap = snapshot(raw)
    print("clear:", snap["clear"])
    for r in snap["satisfied_by"]:
        print("  governed by:", r)
    if not snap["clear"]:
        print(json.dumps(ineligible_record(snap), indent=2))
