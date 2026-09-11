#!/usr/bin/env python3
"""forge_resume.py — the last step of the forge: the want that asked gets its hand back.

    reach -> gap -> proposal -> her card -> build -> verify -> install -> RESUME

`skill_forge.resumable()` has always named the intentions whose capability has landed.
Nothing consumed it, so the last arrow was drawn and never walked: a want would sit
BLOCKED on a missing hand long after the hand was installed, and only a person noticing
would start it again. This is the consumer. It runs at the top of the wants pass, before
a single want is read, so the pass that follows sees a want that is standing rather than
one that is blocked.

WHAT IT IS ALLOWED TO DO

  Exactly one thing: take the CAPABILITY_ABSENT block off the want that opened the
  proposal, and mark the proposal resumed. It does not plan, re-order, re-prioritise,
  fulfil, or run a step. The want returns to the state it was in before it reached for
  something that was not there; the ordinary pass decides what happens next.

  It will not clear a block it does not recognise. A want blocked on a tool that is not
  answering, or on a different missing hand, keeps its block and says so. Releasing a
  want from a block that still holds would send the pass straight back into the wall.

THE ORDER OF THE TWO WRITES, AND WHY

  The want is unblocked first, under the store lock; the proposal is marked resumed
  second. A crash between them leaves the proposal installed, so resumable() names it
  again on the next pass — and the want, already free, reports `already_free` and the
  proposal is marked then. The reverse order would lose the want: the proposal would
  read resumed while the want stayed blocked forever, with nothing left to name it.
  Every outcome here is idempotent by construction, because this runs on a cadence.

    python3 forge_resume.py            resume every want whose hand has landed
    python3 forge_resume.py --dry-run  say what it would resume, change nothing
    python3 forge_resume.py <want_id>  only that want
"""
import json
import os
import sys
import time
from datetime import datetime, timezone

WS = os.environ.get("SPARK_WORKSPACE") or os.path.expanduser("~/.vintos/workspace")
MEMORY = os.path.join(WS, "memory")
WANTS = os.path.join(MEMORY, "current-wants.json")

# what resume() reports per proposal, and whether the proposal moves
RESUMED = "resumed"              # the block was cleared by this run
ALREADY_FREE = "already_free"    # no matching block left to clear (a crash between the writes)
STILL_BLOCKED = "still_blocked"  # blocked on something this hand does not answer
GONE = "gone"                    # the want stopped standing between the two reads
REFUSED = "refused"              # the forge would not move the proposal
MOVES_THE_PROPOSAL = (RESUMED, ALREADY_FREE)


def _now():
    return datetime.now(timezone.utc).isoformat()


def _forge():
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    sys.path.insert(0, os.path.join(WS, "scripts"))
    import skill_forge
    return skill_forge


def _load_wants():
    try:
        d = json.load(open(WANTS))
        return d if isinstance(d, list) else []
    except Exception:
        return []


def _update_wants(mutate):
    """Read-modify-write current-wants.json under the one store lock. Three organs write
    this file; a snapshot-then-write here would drop whatever the pass wrote meanwhile."""
    def _m(rows):
        rows = rows if isinstance(rows, list) else []
        return mutate(rows)
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        sys.path.insert(0, os.path.join(WS, "scripts"))
        from store_guard import locked_update as _lu
        _lu(WANTS, _m, default=[], reader="forge_resume.py")
        return True
    except Exception:
        return False


def release(want, capability, proposal_id):
    """Take the block off one want, in place. (changed, outcome, detail).

    Only a CAPABILITY_ABSENT block naming this exact capability is cleared. A block
    that names no step is left alone too: the forge cannot tell whether the hand that
    landed is the one it was waiting for, and guessing would un-block a want that is
    still against the wall."""
    b = want.get("blocked")
    if not isinstance(b, dict):
        if any(r.get("proposal") == proposal_id and r.get("capability") == capability for r in want.get("resumed_by", [])):
            return False, ALREADY_FREE, "this proposal already released the want"
        return False, STILL_BLOCKED, "no matching release receipt; retained"
    if b.get("block_type") != "CAPABILITY_ABSENT":
        return False, STILL_BLOCKED, "blocked on %s, which a new hand does not answer" % b.get("block_type")
    step = b.get("blocked_step")
    if step != capability:
        return False, STILL_BLOCKED, ("blocked on %r, not on %r" % (step, capability)
                                      if step else "the block does not name the hand it wants")
    want.pop("blocked", None)
    want.setdefault("resumed_by", []).append(
        {"proposal": proposal_id, "capability": capability, "at": _now()})
    # The step itself was never failed — it was never run. It is still pending, and the
    # history says why it is moving again, so the pass is not silently different.
    want.setdefault("step_history", []).append(
        {"step": capability, "result": "RESUMED",
         "findings": "the hand this step was waiting for was installed (%s)" % proposal_id,
         "error": "", "at": time.time()})
    return True, RESUMED, "the block on %s is cleared; the want is standing again" % capability


def resume(want_id=None, dry_run=False):
    """Walk every proposal whose capability is installed and whose want still stands.
    Returns one row per proposal: what it was, and what happened to it."""
    sf = _forge()
    out = []
    for row in sf.resumable(want_id):
        pid, cap, wid = row["proposal"], row["capability"], row["want_id"]
        seen = {"outcome": GONE, "detail": "the want is no longer in the store"}

        def mutate(rows, _pid=pid, _cap=cap, _wid=wid, _seen=seen):
            for w in rows:
                if not isinstance(w, dict) or w.get("id") != _wid:
                    continue
                # resumable() read the store a moment ago; under the lock it may already
                # have been fulfilled or dismissed by the pass that is running.
                if w.get("fulfilled") or w.get("dismissed"):
                    _seen.update(outcome=GONE, detail="the want was fulfilled or dismissed")
                    return None
                changed, outcome, detail = release(w, _cap, _pid)
                _seen.update(outcome=outcome, detail=detail)
                return rows if changed else None
            return None

        if dry_run:
            for w in _load_wants():
                if isinstance(w, dict) and w.get("id") == wid:
                    if w.get("fulfilled") or w.get("dismissed"):
                        seen.update(outcome=GONE, detail="the want was fulfilled or dismissed")
                    else:
                        # a copy all the way down: release() appends to lists, and a dry run
                        # must not reach even the in-memory want it was asked about
                        _, outcome, detail = release(json.loads(json.dumps(w)), cap, pid)
                        seen.update(outcome=outcome, detail=detail)
                    break
        else:
            if not _update_wants(mutate):
                out.append({**row, "outcome": REFUSED, "detail": "want save failed; proposal retained"})
                continue
            # The want is written before the proposal moves. If this process dies here the
            # proposal stays installed, resumable() names it again, and the next pass finds
            # an already_free want and finishes the job.
            if seen["outcome"] in MOVES_THE_PROPOSAL:
                moved, why = sf.mark(pid, "resumed", seen["detail"])
                if moved is None:
                    seen.update(outcome=REFUSED, detail=why)

        out.append({"proposal": pid, "capability": cap, "want_id": wid,
                    "want": row.get("want", ""), "outcome": seen["outcome"],
                    "detail": seen["detail"]})
    return out


def line(rows):
    """One line for the pass's log, or nothing at all when nothing landed."""
    if not rows:
        return ""
    done = [r for r in rows if r["outcome"] == RESUMED]
    held = [r for r in rows if r["outcome"] == STILL_BLOCKED]
    parts = []
    if done:
        parts.append("resumed %s" % ", ".join("%s (%s)" % (r["capability"], r["want_id"]) for r in done))
    if held:
        parts.append("still blocked: %s" % "; ".join("%s — %s" % (r["capability"], r["detail"]) for r in held))
    if not parts:
        return ""
    return "forge: " + "; ".join(parts)


def main():
    dry = "--dry-run" in sys.argv
    wid = next((a for a in sys.argv[1:] if not a.startswith("-")), None)
    rows = resume(wid, dry_run=dry)
    if not rows:
        print("no installed capability is waiting on a want" + (" (dry run)" if dry else ""))
        return
    for r in rows:
        print("%-11s %-22s %-14s %s" % (r["proposal"], r["capability"], r["outcome"], r["detail"]))
    if dry:
        print("\n--dry-run: nothing was written.")


if __name__ == "__main__":
    main()
