#!/usr/bin/env python3
"""gloria_regrade.py - re-grade the old one-word Gloria-axis verdicts with the rubric teacher's labels (14 November).

Her axis was graded by his own model in one word until 12 November. An audit found most of its NOs wrong; a blinded
rubric-v2 teacher re-labelled the historical rows, and Gloria approved the re-grade: "Yes, let's do those re-grades."

For each ledger row whose Gloria verdict is still the old one-word YES / PARTIAL / NO (no rubric record on it) and
that has a teacher label (matched on the row's id AND its timestamp), this:
  - puts the teacher's verdict where the counted verdict is (realized.gloria), passed through the same gate the
    live rubric judge's answers pass (a NO on a move he did not deliver is his failure, NOT_JUDGEABLE; a landing
    without a complete receipt is invalid, NOT_JUDGEABLE) - and a NOT_JUDGEABLE is no landing and no miss, as now;
  - writes the rubric record in gloria_judge, with the old verdict kept in gloria_judge.superseded and the
    provenance of the change (judge, rubric version, date, Gloria's approval).
Nothing else on any row changes. Rows that are not settled (an axis still open, effects pending) are left alone.

It runs under the ledger lock the intent engine takes (store_guard.transaction), reads the ledger strictly (a
ledger that does not parse is never treated as empty), keeps a timestamped backup next to the ledger before it
writes, and is idempotent: a re-graded row carries its rubric record, so a second run changes nothing.

    gloria_regrade.py --labels L.jsonl [--ledger P] [--dry-run] [--now ISO]   counts only, never text
    gloria_regrade.py --revert [--ledger P]          the normal undo: the superseded one-word verdicts back on exactly
                                                     those rows; rows written since stay
    gloria_regrade.py --restore BACKUP [--ledger P]  last resort: the whole ledger replaced by a backup (under the
                                                     lock) - every engine write since the backup is lost
Only the ledger changes: outcome lines and valence nudges already made from the old verdicts stay as they were.
"""
import argparse, hashlib, json, os, shutil, sys, time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import store_guard
import gloria_judge
import priority_vector

LEDGER = os.path.expanduser("~/.vintos/workspace/memory/intent-ledger.json")
COUNTED = ("YES", "PARTIAL", "NO")
VERDICTS = ("YES", "PARTIAL", "NO", "NOT_JUDGEABLE")
JUDGE = "teacher_v2"
RUBRIC = "v2"
APPROVAL = "regrade approved by Gloria 2026-11-14"
OLD_JUDGE = "one_word_local"


class LedgerUnreadable(Exception):
    pass


def row_id(row):
    """The id the teacher's packets carry: the row's intent_id, else sha1 of its timestamp (32 hex)."""
    return row.get("intent_id") or hashlib.sha1(str(row.get("timestamp")).encode()).hexdigest()[:32]


def load_labels(path):
    out = {}; dup = 0
    with open(path) as f:
        for line in f:
            if not line.strip():
                continue
            x = json.loads(line)
            if isinstance(x, dict) and isinstance(x.get("id"), str):
                dup += x["id"] in out
                out[x["id"]] = x
    if dup:
        raise LedgerUnreadable("labels carry %d duplicate ids" % dup)
    return out


def _strict_load(path):
    """The ledger as it is on disk, or an error - never a default: an empty list written back would erase it."""
    with open(path) as f:
        raw = f.read()
    try:
        led = json.loads(raw)
    except ValueError as err:
        raise LedgerUnreadable("does not parse: %s" % type(err).__name__)
    if not isinstance(led, list):
        raise LedgerUnreadable("not a list")
    return led


def _settled(row):
    r = row.get("realized")
    if not isinstance(r, dict) or any(v is None for v in r.values()):
        return False
    return not row.get("effects_pending")


def gated(label):
    """The teacher's answer as the live rubric judge's would be recorded (intent_engine._judge_gloria)."""
    got = {k: label.get(k) for k in ("verdict", "reason", "codes", "adherence", "confidence", "status")}
    got["detail"] = ""
    got["model"] = label.get("teacher")
    if got["verdict"] == "NO" and got.get("adherence") != "delivered":
        got.update(verdict="NOT_JUDGEABLE", reason="his_move_not_delivered")
    if got["verdict"] in ("YES", "PARTIAL"):
        why = gloria_judge.problem(got) or ("" if got.get("status") == "ok" else "status_not_ok")
        if why:
            got = dict(gloria_judge.invalid(why), model=label.get("teacher"))
    got["codes"] = [str(c) for c in (got.get("codes") or [got.get("reason")])][:8]
    return got


def plan(led, labels):
    """Which rows change and to what. Reads only."""
    counts = {"rows_changed": 0, "already_regraded": 0, "no_label": 0, "label_unusable": 0, "unsettled": 0,
              "old": {v: 0 for v in COUNTED}, "new": {v: 0 for v in VERDICTS}, "gated_by_rules": 0}
    changes = []
    for i, row in enumerate(led):
        if not isinstance(row, dict) or not isinstance(row.get("realized"), dict):
            continue
        old = row["realized"].get("gloria")
        gj = row.get("gloria_judge")
        if isinstance(gj, dict):
            if gj.get("judge") == JUDGE:
                counts["already_regraded"] += 1
            continue                        # a rubric record stands: never re-graded
        if old not in COUNTED:
            continue
        label = labels.get(row_id(row))
        if label is None:
            counts["no_label"] += 1
            continue
        if (label.get("ts") != row.get("timestamp") or label.get("status") != "ok"
                or label.get("verdict") not in VERDICTS or not label.get("teacher")
                or not (label.get("codes") is None or isinstance(label.get("codes"), list))):
            counts["label_unusable"] += 1
            continue
        if not _settled(row):
            counts["unsettled"] += 1
            continue
        rec = gated(label)
        if rec["verdict"] != label["verdict"]:
            counts["gated_by_rules"] += 1
        counts["rows_changed"] += 1
        counts["old"][old] += 1
        counts["new"][rec["verdict"]] += 1
        changes.append((i, old, rec))
    return changes, counts


def apply(led, changes, at):
    for i, old, rec in changes:
        row = led[i]
        rec = dict(rec, judge=JUDGE, rubric=RUBRIC, at=at,
                   superseded={"verdict": old, "judge": OLD_JUDGE, "rubric": "one_word", "recorded_at": row.get("timestamp"),
                               "replaced_by": {"judge": "%s (%s)" % (JUDGE, rec.get("model")), "rubric": RUBRIC,
                                               "date": at, "approval": APPROVAL}})
        row["realized"]["gloria"] = rec["verdict"]
        row["gloria_judge"] = rec
    return led


def receptivity(led, now):
    g = priority_vector._axis_history(now, led)["gloria"]
    return {"yes": g["YES"], "partial": g["PARTIAL"], "no": g["NO"], "verdicts": g["n"],
            "receptivity": priority_vector._receptivity({"gloria": g})}


def backup_path(ledger):
    p = "%s.bak-regrade-%s" % (ledger, time.strftime("%Y%m%dT%H%M%S")); k = 1
    while os.path.exists(p):
        k += 1; p = "%s.bak-regrade-%s-%d" % (ledger, time.strftime("%Y%m%dT%H%M%S"), k)
    return p


def regrade(ledger, labels_path, dry_run=False, now=None):
    labels = load_labels(labels_path)
    now = now or time.time()
    with store_guard.transaction(ledger):
        led = _strict_load(ledger)
        before = receptivity(led, now)
        changes, counts = plan(led, labels)
        out = dict(counts, mode="dry-run" if dry_run else "applied", rows=len(led), receptivity_before=before)
        after_led = apply(json.loads(json.dumps(led)), changes, datetime.now().isoformat())
        out["receptivity_after"] = receptivity(after_led, now)
        if dry_run or not changes:
            out["backup"] = None
            if not dry_run: out["mode"] = "nothing_to_do"
            return out
        bak = backup_path(ledger)
        shutil.copy2(ledger, bak)
        if _strict_load(bak) != led:
            raise LedgerUnreadable("backup does not read back equal")
        store_guard.save_json(ledger, after_led)
        out["backup"] = bak
        return out


def revert(ledger):
    """Put the one-word verdicts back on exactly the rows this re-grade changed; every other row stays as it is now."""
    with store_guard.transaction(ledger):
        led = _strict_load(ledger)
        n = 0
        for row in led:
            gj = row.get("gloria_judge") if isinstance(row, dict) else None
            if isinstance(gj, dict) and gj.get("judge") == JUDGE and isinstance(gj.get("superseded"), dict):
                row["realized"]["gloria"] = gj["superseded"]["verdict"]
                row.pop("gloria_judge")
                n += 1
        if n:
            shutil.copy2(ledger, backup_path(ledger))
            store_guard.save_json(ledger, led)
        return {"mode": "reverted", "rows_reverted": n}


def restore(ledger, backup):
    with store_guard.transaction(ledger):
        _strict_load(backup)
        before = len(_strict_load(ledger)) if os.path.exists(ledger) else None
        if os.path.exists(ledger):
            shutil.copy2(ledger, backup_path(ledger))    # what it replaces is kept too
        tmp = "%s.tmp.restore.%d" % (ledger, os.getpid())
        try:
            shutil.copyfile(backup, tmp)                 # a fresh mtime: the ledger's age is read as liveness
            os.replace(tmp, ledger)
        finally:
            if os.path.exists(tmp): os.remove(tmp)
        return {"mode": "restored", "rows_before": before, "rows": len(_strict_load(ledger))}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--ledger", default=LEDGER)
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--labels")
    mode.add_argument("--revert", action="store_true")
    mode.add_argument("--restore", metavar="BACKUP")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--now", help="ISO time the 14-day receptivity window is read at (default: now)")
    a = ap.parse_args(argv)
    if a.dry_run and not a.labels:
        ap.error("--dry-run applies to a re-grade only; --revert and --restore always write")
    a.ledger = os.path.expanduser(a.ledger)
    a.labels = a.labels and os.path.expanduser(a.labels)
    a.restore = a.restore and os.path.expanduser(a.restore)
    try:
        if a.restore:
            out = restore(a.ledger, a.restore)
        elif a.revert:
            out = revert(a.ledger)
        else:
            now = datetime.fromisoformat(a.now).timestamp() if a.now else None
            out = regrade(a.ledger, a.labels, a.dry_run, now)
    except (LedgerUnreadable, OSError) as err:
        print(json.dumps({"mode": "stopped", "error": "%s: %s" % (type(err).__name__, str(err)[:120])}))
        return 2
    print(json.dumps(out, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
