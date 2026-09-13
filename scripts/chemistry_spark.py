#!/usr/bin/env python3
"""What the Chemistry Lab may legitimately put in front of him as a spark.

A spark is not a want and a want is not a proposal, but a spark is the first hop of the only
road that ends in a new capability, so what is allowed onto it matters. The spark layer
already carries `lab` as one of the seven sources and `from_lab()` already reads wherever
`memory/spark-config.json` points it. Two things were missing and both are here:

**A feed it can actually read.** `from_lab()` scrapes lines beginning with `-`, `*` or a date.
Pointed at `notebook.jsonl` it finds nothing, because every line begins with `{` — and finding
nothing would have looked exactly like his having had no ideas. This writes
`spark-feed.jsonl`: rows already shaped for the spark layer, one per occasion that may
legitimately spark something.

**Provenance that survives.** A spark row was `{key, source, text, ref, seen, state}`; session,
run, grade and truth status all died at the first hop, and a want that cannot name the
occasion it came from is not Lab provenance. Every row here carries one.

Eligibility, and why each rule is here rather than being generous:

- the text must be a `next_question` from a **completed session** or from an **owed reading
  that was actually paid** — a speculative reflection is imaginative work, and imaginative
  work may not commission a capability any more than it may become collision evidence;
- never a `what_surprised_me` — Phase 4's rule, for the same reason: a model asked to be
  interested is not evidence of interest;
- never a subject named in the taste block that preceded it — the echo test again, so his own
  ledger cannot talk him into commissioning something;
- and the occasion must have a run behind it, so the spark can name what it came from.

Refusals are written with their reason. A feed that silently drops what it refused cannot be
audited for what it refused, and this one decides what may reach the Forge.

Nothing here creates a want. `spark_sources.adopt()` writes no want either. Wanting stays his,
through the ordinary door, and approving stays hers.

    refresh()            read the Lab and write the feed
    configure()          point memory/spark-config.json at it (an explicit act, not a guess)
    python3 chemistry_spark.py [refresh|configure|show]
"""
from __future__ import annotations

import hashlib
import contextlib
import fcntl
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path: sys.path.insert(0, HERE)
import chemistry_lab as lab

FEED = os.path.join(lab.ROOT, "spark-feed.jsonl")
REFUSED_FEED = os.path.join(lab.ROOT, "spark-refusals.jsonl")
SPARK_CONFIG = os.path.join(lab.MEM, "spark-config.json")
SPARK_LOCK = os.path.join(lab.ROOT, ".spark.lock")

# Notebook kinds an occasion may come from, and what each is worth here.
FROM_COMPLETED_SESSION = "frontier_session"
FROM_PAID_READING = "owed_reading"
ELIGIBLE_KINDS = (FROM_COMPLETED_SESSION, FROM_PAID_READING)

MIN_TEXT = 25
MAX_TEXT = 300
FEED_LIMIT = 40

ELIGIBLE = "eligible"
NOT_A_QUESTION = "refused_not_a_next_question"
SPECULATIVE = "refused_speculative_reflection_only"
GENERATED_INTEREST = "refused_generated_surprise"
ECHO = "refused_echo_of_injected_taste"
NO_RUN = "refused_no_run_behind_it"
NO_COMPLETED_OCCASION = "refused_session_did_not_complete"
TOO_SHORT = "refused_too_short_to_be_a_question"


@contextlib.contextmanager
def _locked():
    lab._ensure()
    with open(SPARK_LOCK, "a+") as stream:
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
        yield


def _sessions():
    rows = {}
    for row in lab._jsonl(os.path.join(lab.ROOT, "sessions.jsonl")):
        if row.get("session_id"): rows[row["session_id"]] = row
    return rows


def _injected_before(at):
    try:
        import chemistry_taste
        return chemistry_taste.injected_keys_before(at)
    except Exception:
        return set()


def _echoes(text, injected):
    """Does this question simply hand back something his taste block had just named?"""
    lowered = str(text or "").lower()
    for entry_id in injected:
        key = str(entry_id).split("||", 1)[-1].strip().lower()
        if len(key) >= 3 and key in lowered: return True
    return False


def _key(note, text):
    return hashlib.sha256(("chemistry-lab\x1f" + str(note.get("session_id") or "") + "\x1f" + text).encode()).hexdigest()[:20]


def _judge(note, sessions):
    """One notebook entry: what it may become, and the reason if it may become nothing."""
    kind = note.get("kind")
    if kind not in ELIGIBLE_KINDS:
        return None, (SPECULATIVE if kind in ("reflection", "inquiry", "source_read",
                                              "protein_representation") else NOT_A_QUESTION)
    text = str(note.get("next_question") or "").strip()
    if not text: return None, NOT_A_QUESTION
    if len(text) < MIN_TEXT: return None, TOO_SHORT
    session = sessions.get(note.get("session_id")) or {}
    if kind == FROM_COMPLETED_SESSION and session.get("state") != "completed":
        return None, NO_COMPLETED_OCCASION
    if kind == FROM_PAID_READING and not (
            note.get("reread_of_preserved_result") is True and
            note.get("truth_status") == "later_reading_of_a_preserved_result_no_rerun"):
        return None, NO_COMPLETED_OCCASION
    grade = session.get("grade") if isinstance(session.get("grade"), dict) else {}
    run_id = session.get("mac_run_id") or grade.get("run_id")
    if not run_id:
        # No experiment behind it means nothing for the spark to name. A question he asked
        # of nothing is still his; it is simply not evidence that a capability is missing.
        return None, NO_RUN
    if _echoes(text, _injected_before(note.get("at"))): return None, ECHO
    provenance = {
        "lab": "chemistry", "session_id": note.get("session_id"),
        "notebook_kind": kind, "at": note.get("at"),
        "experiment": session.get("plan", {}).get("experiment") if isinstance(session.get("plan"), dict) else None,
        "mac_run_id": run_id,
        "execution_state": grade.get("execution_state"),
        "aggregate_accuracy": grade.get("aggregate_accuracy"),
        "isolation_attestation": grade.get("isolation_attestation"),
        "context_receipt": session.get("context_receipt"),
        "lens": session.get("lens"),
        "truth_status": "question_from_a_run_that_completed_not_a_finding",
    }
    return {"text": text[:MAX_TEXT], "ref": "chemistry-lab/notebook.jsonl",
            "provenance": provenance}, ELIGIBLE


def _refresh():
    """Rewrite the feed from the Lab's own record. Refusals are appended, never dropped."""
    sessions = _sessions()
    known = {row.get("key") for row in lab._jsonl(FEED)}
    refused_known = {row.get("key") for row in lab._jsonl(REFUSED_FEED)}
    written, refused = [], []
    for note in lab._jsonl(lab.NOTEBOOK)[-200:]:
        text = str(note.get("next_question") or "").strip()
        key = _key(note, text or json.dumps(note, sort_keys=True)[:120])
        row, verdict = _judge(note, sessions)
        if verdict == ELIGIBLE:
            if key in known: continue
            entry = dict(row, key=key, at=lab.now_iso(),
                         truth_status="lab_occasion_eligible_to_spark_not_a_want")
            lab._append(FEED, entry); known.add(key); written.append(entry)
        else:
            if key in refused_known or not text: continue
            entry = {"key": key, "at": lab.now_iso(), "session_id": note.get("session_id"),
                     "notebook_kind": note.get("kind"), "text": text[:MAX_TEXT],
                     "verdict": verdict,
                     "truth_status": "lab_occasion_refused_as_a_spark_and_kept"}
            lab._append(REFUSED_FEED, entry); refused_known.add(key); refused.append(entry)
    return {"written": written, "refused": refused}


def refresh():
    with _locked(): return _refresh()


def feed(limit=FEED_LIMIT):
    return lab._jsonl(FEED)[-int(limit):]


def configure():
    """Point the spark reader here.

    `from_lab()` reads only where she points it, and that law stays: it once guessed a
    filename and read two dead logs from another project. This is the explicit act, not a
    default — it writes one key, and it does not touch the others.
    """
    with _locked():
        value = lab._load(SPARK_CONFIG, {})
        if not isinstance(value, dict): value = {}
        value["lab"] = FEED
        lab._atomic(SPARK_CONFIG, value)
        return value


def state():
    return {"eligible": len(lab._jsonl(FEED)), "refused": len(lab._jsonl(REFUSED_FEED)),
            "configured": lab._load(SPARK_CONFIG, {}).get("lab") == FEED,
            "latest": (feed(1) or [{}])[0].get("text")}


if __name__ == "__main__":
    action = sys.argv[1] if len(sys.argv) > 1 else "show"
    if action == "refresh":
        result = refresh()
        print(json.dumps({"written": len(result["written"]), "refused": len(result["refused"]),
                          "state": state()}, indent=2))
    elif action == "configure":
        print(json.dumps({"ok": True, "spark_config": configure()}, indent=2))
    else:
        print(json.dumps({"state": state(), "feed": feed(8)}, ensure_ascii=False, indent=2))
