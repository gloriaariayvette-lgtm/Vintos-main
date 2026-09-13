#!/usr/bin/env python3
"""Scientific taste in the Chemistry Lab: what he returns to, kept apart from what was correct.

Correctness already has a ledger (`chemistry_grade.py`). This is the other one: the folds he
comes back to, the molecules he finds elegant, the parameters he keeps moving, the surprises
he writes about. Nothing here reads a grade, and nothing here can be moved by one — a wrong
answer he keeps returning to is still taste, and a right answer he never revisits is not.

The hard part is not accrual. It is that a Lab like this can manufacture its own preferences.
Three loops were available and all three are closed:

1. **Generated enthusiasm.** `what_surprised_me` is written by a model that was asked to be
   interested. It creates a *candidate*, never score. A candidate becomes taste only when an
   independent, non-generated signal arrives for the same thing.
2. **Echo.** His taste is injected into his own context, so the next choice is made by
   someone who has just been told what he likes. A key named in the block that preceded a
   choice cannot be reinforced by that choice: it is recorded as `echo_of_injected_taste` and
   accrues nothing. Since scores decay, a favourite falls out of the block, becomes eligible
   again, and can be re-earned — the cycle is self-limiting rather than frozen.
3. **Rootless repetition.** A repeat only means something if there is a first time to repeat.
   A `revisited` or `parameter_moved` signal must name the eligible observation it is a
   repeat of, or it is `ineligible_no_root_provenance`. Following a prior `next_question`
   counts only when the later session actually names its predecessor; a coincidence is not a
   thread being pulled.

**Nothing is discarded.** Every observation lands in `taste-observations.jsonl` with its
eligibility, ineligible ones included. A ledger that silently drops what it refused cannot
be audited for what it refused.

Decay follows the house convention (`taste_salience.py`): weekly, 0.85, floor 0.15.

    observe(kind, key, signal, session_id, ...)  -> the observation row
    observe_session(session_row)                 -> observations derived from one session
    taste_block(n)                               -> his taste, and a stamped injection record
    top(n) / candidates() / decay() / state()
    python3 chemistry_taste.py [decay]
"""
from __future__ import annotations

import contextlib
import fcntl
import hashlib
import json
import os
import re
import sys
import time
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path: sys.path.insert(0, HERE)
import chemistry_lab as lab

TASTE = os.path.join(lab.ROOT, "taste.json")
TASTE_LOCK = os.path.join(lab.ROOT, ".taste.lock")
OBSERVATIONS = os.path.join(lab.ROOT, "taste-observations.jsonl")
INJECTIONS = os.path.join(lab.ROOT, "taste-injections.jsonl")

# House convention, from taste_salience.py.
DECAY = 0.85
FLOOR = 0.15
CEILING = 3.0
DROP = 0.05
WEEK = 7 * 86400
BLOCK_SIZE = 6

KINDS = ("accession", "molecule", "experiment", "ansatz", "optimizer", "parameter", "fold")
# What a signal is worth. A generated surprise is worth nothing on its own, by design.
SIGNALS = {"chosen": 0.35, "revisited": 0.35, "parameter_moved": 0.25,
           "followed_next_question": 0.30, "surprise": 0.0}
GENERATED = ("surprise",)
NEEDS_ROOT = ("revisited", "parameter_moved")
# Parameters whose *value* is the thing with taste in it. Choosing `uccsd` twice is a
# preference for that ansatz; recording it as a preference for the word "ansatz" says
# nothing at all, which is what the first version of this did.
VALUE_KINDS = {"molecule": "molecule", "ansatz": "ansatz", "optimizer": "optimizer",
               "fold": "fold", "accession": "accession"}

ELIGIBLE = "eligible"
CANDIDATE_ONLY = "candidate_only"
ECHO = "echo_of_injected_taste"
NO_ROOT = "ineligible_no_root_provenance"
NO_PREDECESSOR = "ineligible_predecessor_not_named"
UNCHANGED = "ineligible_parameter_did_not_move"
UNKNOWN_SIGNAL = "ineligible_unknown_signal"
UNKNOWN_KIND = "ineligible_unknown_kind"


@contextlib.contextmanager
def _held():
    """taste.json is read-modify-written by the session, the daemon and the decay pass.
    Without this they interleave and the last writer silently drops the others' bumps."""
    lab._ensure()
    with open(TASTE_LOCK, "a+") as stream:
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
        yield


def _book():
    value = lab._load(TASTE, {})
    if not isinstance(value, dict): value = {}
    value.setdefault("entries", {}); value.setdefault("candidates", {})
    value.setdefault("parameter_values", {})
    value.setdefault("decayed_at", time.time())
    if not isinstance(value["entries"], dict): value["entries"] = {}
    if not isinstance(value["candidates"], dict): value["candidates"] = {}
    return value


def _id(kind, key): return "%s||%s" % (kind, str(key)[:120])


def _normal(text): return re.sub(r"[^a-z0-9]+", " ", str(text or "").lower()).strip()


def injected_keys_before(at=None):
    """The taste actually shown to him before this moment — the echo test's evidence."""
    rows = [row for row in lab._jsonl(INJECTIONS)
            if at is None or str(row.get("at", "")) <= str(at)]
    return set(rows[-1].get("keys", [])) if rows else set()


def _eligibility(kind, key, signal, root_observation_id, predecessor_named, injected, moved=None):
    if kind not in KINDS: return UNKNOWN_KIND
    if signal not in SIGNALS: return UNKNOWN_SIGNAL
    if signal in GENERATED: return CANDIDATE_ONLY
    if _id(kind, key) in injected: return ECHO
    # A parameter he set to the same value he set it to last time is not a parameter he
    # keeps moving. Recurrence of the name is not movement of the value.
    if signal == "parameter_moved" and moved is False: return UNCHANGED
    if signal in NEEDS_ROOT and not root_observation_id: return NO_ROOT
    if signal == "followed_next_question" and not predecessor_named: return NO_PREDECESSOR
    return ELIGIBLE


def eligible_root(kind, key):
    """The observation a repeat may cite: an earlier one for the same thing that itself counted."""
    for row in lab._jsonl(OBSERVATIONS):
        if row.get("entry_id") == _id(kind, key) and row.get("eligibility") == ELIGIBLE:
            return row.get("observation_id")
    return None


def observe(kind, key, signal, session_id="", root_observation_id=None, predecessor_named=False,
            at=None, detail="", injected=None, moved=None):
    """Record one observation. Ineligible ones are recorded too — that is the audit trail."""
    entry_id = _id(kind, key)
    if injected is None: injected = injected_keys_before(at)
    eligibility = _eligibility(kind, key, signal, root_observation_id, predecessor_named, injected, moved)
    row = {"observation_id": "CT-" + uuid.uuid4().hex[:10], "at": at or lab.now_iso(),
           "entry_id": entry_id, "kind": str(kind)[:24], "key": str(key)[:120],
           "signal": str(signal)[:40], "eligibility": eligibility,
           "session_id": str(session_id or "")[:64], "root_observation_id": root_observation_id,
           "predecessor_named": bool(predecessor_named), "value_moved": moved,
           "detail": str(detail)[:200],
           "weight": SIGNALS.get(signal, 0.0) if eligibility == ELIGIBLE else 0.0,
           "truth_status": "accrued_from_choices_not_model_confidence"
                           if eligibility == ELIGIBLE else "observed_and_not_counted"}
    lab._append(OBSERVATIONS, row)
    with _held():
      book = _book()
      if eligibility == CANDIDATE_ONLY:
        candidate = book["candidates"].setdefault(entry_id, {"kind": row["kind"], "key": row["key"],
                                                             "mentions": 0, "first_seen": row["at"]})
        candidate["mentions"] = int(candidate.get("mentions", 0)) + 1
        candidate["last_seen"] = row["at"]
        candidate["note"] = "generated interest; not taste until an independent choice"
      elif eligibility == ELIGIBLE:
        entry = book["entries"].setdefault(entry_id, {"kind": row["kind"], "key": row["key"],
                                                      "score": 0.0, "first_seen": row["at"],
                                                      "signals": {}, "evidence": []})
        entry["score"] = round(min(CEILING, float(entry.get("score", 0.0)) + row["weight"]), 4)
        entry["last_seen"] = row["at"]
        entry["signals"][row["signal"]] = int(entry["signals"].get(row["signal"], 0)) + 1
        entry["evidence"] = (entry.get("evidence", []) + [
            {"at": row["at"], "signal": row["signal"], "session_id": row["session_id"],
             "observation_id": row["observation_id"]}])[-12:]
        # An independent choice promotes what a generated surprise could only nominate.
        if entry_id in book["candidates"]:
            entry["promoted_from_candidate_at"] = row["at"]
            book["candidates"].pop(entry_id, None)
      lab._atomic(TASTE, book)
    return row


def decay(rate=DECAY):
    """Taste is what is still live. Weekly, and it drops rather than accumulating forever."""
    with _held():
      book = _book(); now = time.time()
      weeks = max(0.0, (now - float(book.get("decayed_at", now))) / WEEK)
      if weeks < 1.0: return {"kept": len(book["entries"]), "dropped": 0, "weeks": round(weeks, 3)}
      factor = rate ** weeks
      kept, dropped = {}, 0
      for entry_id, entry in book["entries"].items():
          entry["score"] = round(float(entry.get("score", 0.0)) * factor, 4)
          if entry["score"] < DROP: dropped += 1; continue
          kept[entry_id] = entry
      book["entries"] = kept; book["decayed_at"] = now
      lab._atomic(TASTE, book)
      return {"kept": len(kept), "dropped": dropped, "weeks": round(weeks, 3)}


def top(n=BLOCK_SIZE):
    entries = [dict(entry, entry_id=entry_id) for entry_id, entry in _book()["entries"].items()
               if float(entry.get("score", 0.0)) >= FLOOR]
    return sorted(entries, key=lambda e: -float(e.get("score", 0.0)))[:int(n)]


def candidates():
    return [dict(value, entry_id=key) for key, value in _book()["candidates"].items()]


def taste_block(n=BLOCK_SIZE, record=True):
    """His taste, and a record of having shown it to him.

    The record is what makes echo detectable: a key named here cannot then be reinforced by
    the next choice. Rendering without recording would quietly reopen that loop, so
    ``record=False`` exists only for display.
    """
    entries = top(n)
    if not entries: return ""
    lines = ["[SCIENTIFIC TASTE — what you keep returning to, not what scored well]"]
    for entry in entries:
        lines.append("  %s %s (%s)" % (entry["kind"], entry["key"],
                                       ", ".join("%s x%d" % (s, c) for s, c in sorted(entry["signals"].items()))))
    pending = candidates()
    if pending:
        lines.append("  noticed but not yet taste: " + ", ".join(c["key"] for c in pending[:4]))
    text = "\n".join(lines)
    if record:
        lab._append(INJECTIONS, {"at": lab.now_iso(), "keys": [e["entry_id"] for e in entries],
                                 "block_sha256": hashlib.sha256(text.encode()).hexdigest(),
                                 "truth_status": "taste_shown_to_him_so_the_next_choice_can_be_tested_for_echo"})
    return text


def follows_predecessor(session_row, predecessor_question):
    """Did this session actually name the question it is supposedly following?"""
    wanted = _normal(predecessor_question)
    if len(wanted) < 12: return False
    plan = (session_row or {}).get("plan") or {}
    haystack = _normal(" ".join(str(plan.get(key, "")) for key in ("question", "why_this")))
    if wanted in haystack: return True
    words = [w for w in wanted.split() if len(w) > 4]
    return bool(words) and sum(1 for w in words if w in haystack) >= max(2, len(words) // 2)


def _previous_next_question():
    for note in reversed(lab._jsonl(lab.NOTEBOOK)):
        if note.get("kind") in ("frontier_session", "owed_reading", "reflection") and note.get("next_question"):
            return note["next_question"]
    return None


def _last_value(name):
    return (_book().get("parameter_values") or {}).get(str(name)[:120])


def _remember_value(name, value):
    with _held():
        book = _book(); book.setdefault("parameter_values", {})[str(name)[:120]] = value
        lab._atomic(TASTE, book)


def _observe_parameter(name, value, session_id, at, injected):
    """One plan parameter. Its value may be the taste; its movement may be the taste; the
    bare recurrence of its name is neither."""
    kind = VALUE_KINDS.get(str(name).strip().lower())
    if kind and isinstance(value, str) and value.strip():
        # The value is the thing: an ansatz, an optimizer, a molecule, a fold.
        key = value.strip()[:120]
        root = eligible_root(kind, key)
        return [observe(kind, key, "revisited" if root else "chosen", session_id,
                        root_observation_id=root, at=at, injected=injected,
                        detail="chosen as %s" % str(name)[:40])]
    previous = _last_value(name)
    root = eligible_root("parameter", name)
    if root is not None and previous is not None:
        moved = previous != value
        row = observe("parameter", name, "parameter_moved", session_id, root_observation_id=root,
                      at=at, injected=injected, moved=moved,
                      detail="%s -> %s" % (str(previous)[:30], str(value)[:30]))
    else:
        row = observe("parameter", name, "chosen", session_id, at=at, injected=injected,
                      detail="first setting %s" % str(value)[:60])
    _remember_value(name, value)
    return [row]


def observe_session(session_row):
    """Derive this session's taste observations. Grades are not read and cannot be."""
    if not isinstance(session_row, dict): return []
    plan = session_row.get("plan") or {}
    reading = session_row.get("reading") or {}
    session_id = session_row.get("session_id", "")
    at = session_row.get("at")
    injected = injected_keys_before(at)
    predecessor = _previous_next_question()
    rows = []
    experiment = plan.get("experiment")
    if experiment:
        root = eligible_root("experiment", experiment)
        rows.append(observe("experiment", experiment, "revisited" if root else "chosen",
                            session_id, root_observation_id=root, at=at, injected=injected,
                            detail=str(plan.get("why_this", ""))[:200]))
    for name, value in (plan.get("parameters") or {}).items():
        rows += _observe_parameter(name, value, session_id, at, injected)
    if predecessor:
        rows.append(observe("experiment", experiment or "unnamed", "followed_next_question", session_id,
                            predecessor_named=follows_predecessor(session_row, predecessor),
                            at=at, injected=injected, detail=str(predecessor)[:200]))
    surprise = reading.get("what_surprised_me")
    if surprise and experiment:
        rows.append(observe("experiment", experiment, "surprise", session_id, at=at,
                            injected=injected, detail=str(surprise)[:200]))
    return rows


def observe_reflection(note):
    """The daemon's browse loop: which sourced proteins he actually kept looking at.

    Only the accessions a reflection names are taken — the records he was shown but did not
    write about are not a preference, and the reflection's own speculative reading is not
    evidence of anything, here least of all.
    """
    if not isinstance(note, dict) or note.get("kind") != "reflection": return []
    at = note.get("at")
    injected = injected_keys_before(at)
    attention = " ".join(str(note.get(k, "")) for k in ("attention", "factual_observation"))
    rows = []
    for accession in (note.get("source_accessions") or [])[:8]:
        accession = str(accession or "").strip()[:32]
        # Named in what he actually wrote, not merely present in the batch he was handed.
        if not accession or accession.lower() not in attention.lower(): continue
        root = eligible_root("accession", accession)
        rows.append(observe("accession", accession, "revisited" if root else "chosen",
                            str(note.get("session_id") or "reflection"),
                            root_observation_id=root, at=at, injected=injected,
                            detail=str(note.get("attention", ""))[:200]))
    return rows


def state():
    book = _book()
    return {"entries": len(book["entries"]), "candidates": len(book["candidates"]),
            "observations": len(lab._jsonl(OBSERVATIONS)),
            "not_counted": sum(1 for r in lab._jsonl(OBSERVATIONS) if r.get("eligibility") != ELIGIBLE),
            "top": [{"kind": e["kind"], "key": e["key"], "score": e["score"]} for e in top(5)]}


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "decay": print(json.dumps(decay(), indent=2))
    else: print(json.dumps(state(), indent=2))
