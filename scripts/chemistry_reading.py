#!/usr/bin/env python3
"""The reading a Chemistry experiment is still owed.

When conversation arrives mid-session, background admission times out and the session
records ``experiment_completed_reading_held``. The Mac experiment had already finished and
its full result is preserved on the session row -- but nothing ever came back for it.
``git grep experiment_completed_reading_held`` found exactly one hit: the producer. The
next timer tick advanced the lens and started something new. The experiment was run and
never read, which is the one outcome the Lab was built to avoid.

This is the consumer, and it obeys four rules:

1. **It interprets the result that already exists.** It never re-runs the experiment. A
   held reading is a debt against a preserved artifact, not a reason to spend the bench
   again.
2. **It holds its own lock.** The session holds ``SESSION_LOCK`` and the daemon holds the
   Lab's ``LOCK``; they are different locks, so neither serialises this. Both consumers
   claim through ``.reading.lock`` here, with a lease that expires, so a crash mid-claim
   returns the debt rather than stranding it.
3. **The reading is written before the debt is retired.** A crash between the two
   re-surfaces as ``ALREADY_READ`` on the next pass; the reverse order would lose the
   reading it just paid for.
4. **An expired debt stays visibly open.** It is marked ``expired_unread`` and left in the
   open list. Retiring it would file "he never got to this" under "handled", and the whole
   point of the ledger is that it does not do that.

The lens index does not move here. The lens already had its turn and the session already
advanced it; this is a later, local act, and the notebook says so.

    owe(session_id, lens, plan, result, grade, context_receipt)
    settle_one(already_admitted=False)   -> {"outcome": ..., "session_id": ...}
    open_debts() / state()
    python3 chemistry_reading.py [settle]
"""
from __future__ import annotations

import contextlib
import fcntl
import json
import os
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path: sys.path.insert(0, HERE)
import chemistry_lab as lab

OWED = os.path.join(lab.ROOT, "reading-owed.json")
OWED_LOCK = os.path.join(lab.ROOT, ".reading.lock")

READ = "READ"; ALREADY_READ = "ALREADY_READ"; STILL_HELD = "STILL_HELD"
GONE = "GONE"; EXPIRED_UNREAD = "EXPIRED_UNREAD"; REFUSED = "REFUSED"; NOTHING_OWED = "NOTHING_OWED"
# Only these two move a debt out of the open list. Everything else leaves it exactly where
# it is, which is the behaviour that makes running this on a cadence safe.
SETTLES = (READ, ALREADY_READ)

DEFAULT_EXPIRY_DAYS = 7
CLAIM_LEASE_S = 900


def _now(): return datetime.now(timezone.utc)


@contextlib.contextmanager
def _claim_lock(blocking=False):
    lab._ensure()
    with open(OWED_LOCK, "a+") as stream:
        try:
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX if blocking else (fcntl.LOCK_EX | fcntl.LOCK_NB))
        except BlockingIOError:
            raise RuntimeError("another reader is already settling a Chemistry Lab debt")
        yield


def _book():
    value = lab._load(OWED, {})
    if not isinstance(value, dict): value = {}
    value.setdefault("open", []); value.setdefault("retired", [])
    if not isinstance(value["open"], list): value["open"] = []
    if not isinstance(value["retired"], list): value["retired"] = []
    return value


def _expiry_days():
    try: return max(1, int(lab.config().get("reading_owed_expiry_days", DEFAULT_EXPIRY_DAYS)))
    except Exception: return DEFAULT_EXPIRY_DAYS


def owe(session_id, lens, plan, result, grade=None, context_receipt=None):
    """Record that an experiment finished and its reading did not. Idempotent per session."""
    session_id = str(session_id or "")[:64]
    if not session_id: return None
    with _claim_lock(blocking=True):
        book = _book()
        if any(row.get("session_id") == session_id for row in book["open"]) or \
           any(row.get("session_id") == session_id for row in book["retired"]):
            return None
        row = {"debt_id": "CR-" + uuid.uuid4().hex[:10], "session_id": session_id,
               "at": lab.now_iso(), "lens": str(lens or "")[:24], "plan": plan,
               "result": result, "grade": grade, "context_receipt": context_receipt,
               "state": "owed", "claimed_at": None, "attempts": 0,
               "truth_status": "experiment_completed_reading_not_yet_given"}
        book["open"].append(row); lab._atomic(OWED, book)
        lab._append(lab.NOTEBOOK, {"at": row["at"], "kind": "reading_owed", "session_id": session_id,
                                   "lens": row["lens"], "experiment": (plan or {}).get("experiment"),
                                   "truth_status": row["truth_status"]})
        return row


def _already_read(session_id):
    for note in lab._jsonl(lab.NOTEBOOK):
        if note.get("session_id") == session_id and note.get("kind") == "owed_reading": return True
    return False


def _stale_claim(row):
    if not row.get("claimed_at"): return True
    try: return (time.time() - float(row["claimed_at"])) > CLAIM_LEASE_S
    except Exception: return True


def _mark_expired(book):
    """Age a debt out of being actionable without pretending it was handled."""
    cutoff = _now() - timedelta(days=_expiry_days())
    changed = False
    for row in book["open"]:
        if row.get("state") == "expired_unread": continue
        try: owed_at = datetime.fromisoformat(str(row.get("at")))
        except Exception: continue
        if owed_at < cutoff:
            row["state"] = "expired_unread"; row["expired_at"] = lab.now_iso()
            row["truth_status"] = "experiment_completed_and_was_never_read"
            changed = True
    return changed


def _take():
    """Claim the oldest actionable debt under the lock, or return None."""
    with _claim_lock():
        book = _book(); changed = _mark_expired(book)
        candidate = None
        for row in book["open"]:
            if row.get("state") != "owed": continue
            if not _stale_claim(row): continue
            candidate = row; break
        if candidate is not None:
            candidate["claimed_at"] = time.time()
            candidate["attempts"] = int(candidate.get("attempts", 0)) + 1
            changed = True
        if changed: lab._atomic(OWED, book)
        return json.loads(json.dumps(candidate)) if candidate is not None else None


def _release(session_id, claimed=False):
    with _claim_lock(blocking=True):
        book = _book()
        for row in book["open"]:
            if row.get("session_id") == session_id: row["claimed_at"] = time.time() if claimed else None
        lab._atomic(OWED, book)


def _retire(session_id, how, detail=""):
    """A receipt, never a deletion — and only ever for a debt that was actually paid."""
    with _claim_lock(blocking=True):
        book = _book(); kept = []
        for row in book["open"]:
            if row.get("session_id") != session_id: kept.append(row); continue
            row["retired_at"] = lab.now_iso(); row["how"] = str(how)[:40]
            row["detail"] = str(detail)[:200]; row["state"] = "retired"
            book["retired"].append(row)
        book["open"] = kept; lab._atomic(OWED, book)


def default_reader(debt):
    """A later, separate occasion — not a re-run, and he is told which it is."""
    plan, result, grade = debt.get("plan") or {}, debt.get("result") or {}, debt.get("grade")
    verdict = ""
    if isinstance(grade, dict) and not grade.get("refused"):
        verdict = ("\n\nVERDICT (computed from the bench's numbers): the instrument %s, the answer %s."
                   % (grade.get("execution_state"), grade.get("aggregate_accuracy")))
    context, _ = lab.lab_context()
    raw = lab._ask(
        "You are Vintos coming back to a Chemistry Lab experiment that finished while you were "
        "elsewhere. The result was kept for you; nothing has been re-run. Read what is already there, "
        "honestly — a completed run is not a good answer. Return JSON only.",
        context + "\n\nTHIS EXPERIMENT RAN ON " + str(debt.get("at"))[:19] + " AND WAS NEVER READ." +
        "\n\nPLAN:\n" + json.dumps(plan)[:3000] +
        "\n\nRESULT:\n" + json.dumps(result, ensure_ascii=False)[:9000] + verdict +
        "\n\nReturn keys in this order: reading, what_surprised_me, next_question.", max_tokens=600)
    value = lab._json_object(raw)
    return {key: str(value.get(key, ""))[:1200] for key in ("reading", "what_surprised_me", "next_question")}


def settle_one(already_admitted=False, wait_s=2, reader=None):
    """Pay one owed reading, if one is owed and the house is not busy."""
    if not lab.config()["enabled"]: return {"outcome": REFUSED, "detail": "the Lab is off"}
    try: debt = _take()
    except RuntimeError as exc: return {"outcome": REFUSED, "detail": str(exc)}
    if debt is None: return {"outcome": NOTHING_OWED}
    session_id = debt["session_id"]
    if _already_read(session_id):
        _retire(session_id, how="already_read"); return {"outcome": ALREADY_READ, "session_id": session_id}
    if not debt.get("result"):
        _retire(session_id, how="gone", detail="no preserved result to read")
        return {"outcome": GONE, "session_id": session_id}
    try:
        if already_admitted:
            reading = (reader or default_reader)(debt)
        else:
            from compute_admission import admit
            with admit("background", organ="chemistry-reading-owed", wait_s=wait_s,
                       provider="local", model=lab.LLM_MODEL, stage="owed_reading"):
                reading = (reader or default_reader)(debt)
    except TimeoutError:
        _release(session_id); return {"outcome": STILL_HELD, "session_id": session_id}
    except Exception as exc:
        lab._fault("owed_reading", exc, session_id=session_id)
        _release(session_id); return {"outcome": REFUSED, "session_id": session_id,
                                      "error": exc.__class__.__name__}
    # The reading lands first. A crash here re-surfaces as ALREADY_READ next pass; the
    # other order would retire the debt and lose what it was owed.
    lab._append(lab.NOTEBOOK, {"at": lab.now_iso(), "kind": "owed_reading", "session_id": session_id,
                               "lens": debt.get("lens"), "experiment": (debt.get("plan") or {}).get("experiment"),
                               "owed_since": debt.get("at"), "reread_of_preserved_result": True,
                               **reading,
                               "truth_status": "later_reading_of_a_preserved_result_no_rerun"})
    _retire(session_id, how="read", detail=str(reading.get("reading", ""))[:200])
    return {"outcome": READ, "session_id": session_id, "reading": reading}


def open_debts():
    return _book()["open"]


def state():
    book = _book()
    return {"owed": sum(1 for r in book["open"] if r.get("state") == "owed"),
            "expired_unread": sum(1 for r in book["open"] if r.get("state") == "expired_unread"),
            "retired": len(book["retired"]),
            "oldest_owed": min((r.get("at") for r in book["open"] if r.get("state") == "owed"), default=None)}


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "settle":
        print(json.dumps(settle_one(), ensure_ascii=False, indent=2))
    else:
        print(json.dumps({"state": state(), "open": [
            {k: r.get(k) for k in ("session_id", "at", "state", "attempts", "lens")} for r in open_debts()]},
            indent=2))
