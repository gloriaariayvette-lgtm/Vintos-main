#!/usr/bin/env python3
"""Put back the wants that move_on dismissed "no answer from Gloria in 3 days" although they were never put to her.

From 2026-10-13 to 2026-11-06 want_completion.move_on dismissed every live want three days after it was made unless
Gloria had written in its discussion, whether or not it had ever been routed to her. Only a want routed to her can be
waiting on her answer; the others were dismissed for a silence that was never asked of her.

A dismissed row counts as never routed when nothing shows it reached her: no discussion opened for it in
want-discussions.json, and no gloria_routed / awaiting_gloria mark on the row itself. Those rows are put back on the
live list as they were archived, marked restored, and taken out of dismissed-wants.json. A want already live again or
fulfilled since is left alone. The dismissal archive kept only a few keys then, so a restored want comes back without
its steps; the router plans it again.

Dry run by default: prints what it would change and writes nothing.

    python3 restore_moved_on_wants.py            what it would restore
    python3 restore_moved_on_wants.py --apply    restore them (a backup of both stores is written first)

Run by the owner, on the house, once the move_on fix is deployed (otherwise the next pass dismisses them again)."""
import argparse
import json
import os
import shutil
import sys
import time

WS = os.environ.get("SPARK_WORKSPACE") or os.path.expanduser("~/.vintos/workspace")
MEM = os.path.join(WS, "memory")
CURRENT = os.path.join(MEM, "current-wants.json")
DISMISSED = os.path.join(MEM, "dismissed-wants.json")
FULFILLED = os.path.join(MEM, "fulfilled-wants.json")
DISCUSSIONS = os.path.join(MEM, "want-discussions.json")
REASON = "no answer from Gloria in"


def _load(path, default):
    try:
        with open(path) as f:
            d = json.load(f)
        return d if isinstance(d, type(default)) else default
    except (OSError, ValueError):
        return default


def _rows(d):
    return d if isinstance(d, list) else (d.get("wants") or d.get("fulfilled") or [])


def candidates():
    """(to_restore, skipped) from the stores as they are now. Reads only."""
    dismissed = _rows(_load(DISMISSED, []))
    disc = _load(DISCUSSIONS, {})
    live = {w.get("id") for w in _rows(_load(CURRENT, [])) if isinstance(w, dict)}
    done = {w.get("id") for w in _rows(_load(FULFILLED, [])) if isinstance(w, dict)}
    restore, skipped = [], []
    for row in dismissed:
        if not isinstance(row, dict) or row.get("dismissed_by") != "moved-on":
            continue
        if not str(row.get("dismissed_reason", "")).startswith(REASON):
            continue
        wid = row.get("id")
        if (wid and disc.get(wid)) or row.get("gloria_routed") or row.get("board") == "awaiting_gloria":
            skipped.append((row, "was routed to Gloria"))
        elif wid in live:
            skipped.append((row, "already live"))
        elif wid in done:
            skipped.append((row, "fulfilled since"))
        elif not wid or not row.get("want"):
            skipped.append((row, "no id or text"))
        else:
            restore.append(row)
    return restore, skipped


def revived(row, stamp):
    w = {k: v for k, v in row.items() if k not in ("dismissed", "dismissed_at", "dismissed_by", "dismissed_reason")}
    w.update({"fulfilled": False, "dismissed": False,
              "restored": {"at": stamp, "why": "dismissed by move_on for Gloria's silence, but never routed to her",
                           "dismissed_at": row.get("dismissed_at")}})
    w.pop("board", None)
    return w


def apply(restore):
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
    sys.path.insert(0, os.path.join(WS, "scripts"))
    from store_guard import locked_update
    stamp = time.strftime("%Y-%m-%dT%H:%M:%S")
    tag = time.strftime("%Y%m%d-%H%M%S")
    for p in (CURRENT, DISMISSED):
        if os.path.exists(p):
            shutil.copy2(p, "%s.before-restore-%s" % (p, tag))
    ids = {r["id"] for r in restore}

    def _add(cur):
        have = {w.get("id") for w in cur if isinstance(w, dict)}
        return list(cur) + [revived(r, stamp) for r in restore if r["id"] not in have]

    def _drop(cur):
        rows = _rows(cur)
        kept = [r for r in rows if not (isinstance(r, dict) and r.get("id") in ids and r.get("dismissed_by") == "moved-on"
                                         and str(r.get("dismissed_reason", "")).startswith(REASON))]
        if isinstance(cur, list):
            return kept
        cur["wants"] = kept
        return cur

    locked_update(CURRENT, _add, default=[], reader="restore_moved_on_wants")
    locked_update(DISMISSED, _drop, default=[], reader="restore_moved_on_wants")
    return stamp


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--apply", action="store_true", help="write the change (default: dry run)")
    a = ap.parse_args(argv)
    restore, skipped = candidates()
    print("would restore %d want(s); left alone %d" % (len(restore), len(skipped)))
    why = {}
    for _, reason in skipped:
        why[reason] = why.get(reason, 0) + 1
    for reason, n in sorted(why.items()):
        print("  left alone, %s: %d" % (reason, n))
    for r in restore:
        print("  %s  %-14s %s" % (r.get("id"), str(r.get("source", ""))[:14], str(r.get("want", ""))[:100]))
    if not a.apply:
        print("dry run: nothing written (pass --apply to restore)")
        return 0
    if not restore:
        return 0
    stamp = apply(restore)
    print("restored %d at %s; backups written beside both stores" % (len(restore), stamp))
    return 0


if __name__ == "__main__":
    sys.exit(main())
