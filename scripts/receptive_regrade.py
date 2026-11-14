#!/usr/bin/env python3
"""receptive_regrade.py - give the moves already in the ledger her receptivity record (14 November).

Her receptivity was read from the Gloria-axis landing rate; since 14 November it is read from row["receptive"]
(receptivity.py): did she respond to what his reply asked or offered, in any form, inside 48 hours. Rows settled
before then carry no such record, so the figure would start from nothing. A blinded rubric teacher labelled those rows
against the new definition; Gloria approved fixing the measure: "Fix it."

For each ledger row with no receptive record that has a teacher label (matched on the row's id AND its timestamp),
this writes row["receptive"] - the label, the teacher, the date, Gloria's approval - and nothing else. Her axis
(realized, gloria_judge) is never touched. A label outside the vocabulary is refused, never guessed.

It runs under the ledger lock the intent engine takes (store_guard.transaction), reads the ledger strictly, keeps a
timestamped backup next to the ledger before it writes, and is idempotent: a row that has a receptive record is
never written again.

    receptive_regrade.py --labels L.jsonl [--ledger P] [--dry-run] [--now ISO]   counts only, never text
    receptive_regrade.py --revert [--ledger P]   the normal undo: exactly the records this wrote are taken off
Labels: one JSON object per line, {"id", "ts", "label", "via"?, "teacher"}.
"""
import argparse, json, os, shutil, sys, time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import store_guard
import receptivity as RC
import priority_vector
from gloria_regrade import LedgerUnreadable, _strict_load, backup_path, load_labels, row_id

LEDGER = os.path.expanduser("~/.vintos/workspace/memory/intent-ledger.json")
JUDGE = "teacher_receptive_v1"
APPROVAL = "receptivity re-measure approved by Gloria 2026-11-14 (Fix it.)"
VIA = ("next_reply", "later_turn")


def plan(led, labels):
    """Which rows get which record. Reads only."""
    counts = {"rows_changed": 0, "already_recorded": 0, "no_label": 0, "label_unusable": 0,
              "new": {k: 0 for k in RC.LABELS}}
    changes = []
    for i, row in enumerate(led):
        if not isinstance(row, dict):
            continue
        label = labels.get(row_id(row))
        if RC.label_of(row) is not None:
            counts["already_recorded"] += label is not None
            continue                    # a labelled record stands; one with no label (a failed live judgment) is open
        if label is None:
            counts["no_label"] += 1
            continue
        if (label.get("ts") != row.get("timestamp") or label.get("label") not in RC.LABELS
                or not label.get("teacher") or (label.get("via") is not None and label.get("via") not in VIA)):
            counts["label_unusable"] += 1
            continue
        counts["rows_changed"] += 1
        counts["new"][label["label"]] += 1
        changes.append((i, label))
    return changes, counts


def apply(led, changes, at):
    for i, label in changes:
        led[i]["receptive"] = RC.record(label["label"], JUDGE, at=at, via=label.get("via"),
                                        model=str(label["teacher"]), approval=APPROVAL)
    return led


def measure(led, now):
    """Old and new figures side by side: the landing rate it was read from, and her receptivity now."""
    g = priority_vector._axis_history(now, led)["gloria"]
    h = RC.history(led, now)
    return {"old_landing_rate": priority_vector._landing_rate({"gloria": g}), "old_verdicts": g["n"],
            "receptivity": RC.score(h), "records": h["n"], "answered": h["answered"], "partly": h["partly"],
            "ignored": h["ignored"], "refused": h["refused"], "answered_in_later_turn": h["later_turn"]}


def regrade(ledger, labels_path, dry_run=False, now=None):
    labels = load_labels(labels_path)
    now = now or time.time()
    with store_guard.transaction(ledger):
        led = _strict_load(ledger)
        changes, counts = plan(led, labels)
        out = dict(counts, mode="dry-run" if dry_run else "applied", rows=len(led), before=measure(led, now))
        after = apply(json.loads(json.dumps(led)), changes, datetime.now().isoformat())
        out["after"] = measure(after, now)
        if dry_run or not changes:
            out["backup"] = None
            if not dry_run: out["mode"] = "nothing_to_do"
            return out
        bak = backup_path(ledger).replace(".bak-regrade-", ".bak-receptive-")
        shutil.copy2(ledger, bak)
        if _strict_load(bak) != led:
            raise LedgerUnreadable("backup does not read back equal")
        store_guard.save_json(ledger, after)
        out["backup"] = bak
        return out


def revert(ledger):
    """Take off exactly the records this wrote; every other row, and every live record, stays as it is now."""
    with store_guard.transaction(ledger):
        led = _strict_load(ledger)
        n = 0
        for row in led:
            rec = row.get("receptive") if isinstance(row, dict) else None
            if isinstance(rec, dict) and rec.get("judge") == JUDGE:
                row.pop("receptive")
                n += 1
        if n:
            bak = backup_path(ledger).replace(".bak-regrade-", ".bak-receptive-")
            before = _strict_load(ledger)
            shutil.copy2(ledger, bak)
            if _strict_load(bak) != before:
                raise LedgerUnreadable("backup does not read back equal")
            store_guard.save_json(ledger, led)
        return {"mode": "reverted", "rows_reverted": n}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--ledger", default=LEDGER)
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--labels")
    mode.add_argument("--revert", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--now", help="ISO time the 14-day window is read at (default: now)")
    a = ap.parse_args(argv)
    if a.dry_run and not a.labels:
        ap.error("--dry-run applies to a re-measure only; --revert always writes")
    a.ledger = os.path.expanduser(a.ledger)
    try:
        if a.revert:
            out = revert(a.ledger)
        else:
            now = datetime.fromisoformat(a.now).timestamp() if a.now else None
            out = regrade(a.ledger, os.path.expanduser(a.labels), a.dry_run, now)
    except (LedgerUnreadable, OSError, ValueError) as err:
        print(json.dumps({"mode": "stopped", "error": "%s: %s" % (type(err).__name__, str(err)[:120])}))
        return 2
    print(json.dumps(out, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
