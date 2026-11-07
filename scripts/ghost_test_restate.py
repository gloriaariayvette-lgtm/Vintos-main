#!/usr/bin/env python3
"""ghost_test_restate.py — restate the `test` of EXISTING Ghost Branch hypotheses about his real behaviour.

New ghost rows are written with ghost-branches.real_behaviour_test() (2026-11-07). Rows written before that
watch for a lean "producing movement" when a thread type recurs, which only a ghost run can show. This
rewrites their `test` the same way new rows are written, keeping the old one in `test_before_restate`.

Nothing else on a row changes: not the hypothesis, its id, formation, marks, tenure or status. Rows on any
older wording (no basis, or an earlier real-behaviour version) are brought to the current TEST_BASIS; the first
replaced test stays in `test_before_restate`. Marks are never deleted, but once a row is restated the nightly
judge counts only marks dated from `test_restated_at` on (they were judged under another test). Graduated or
retired rows, and rows whose lean label no longer matches their hypothesis, are skipped.

Gloria decides whether to run it. By default it is a DRY RUN: it prints counts and row ids only, never any
hypothesis or test text, and writes nothing.

    python3 scripts/ghost_test_restate.py            # dry run
    python3 scripts/ghost_test_restate.py --apply    # writes, after a timestamped backup beside the file
"""
import importlib.util, json, os, shutil, sys
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)


def _ghost_module():
    spec = importlib.util.spec_from_file_location("ghost_branches_restate", os.path.join(HERE, "ghost-branches.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _lean_labels(gb):
    axes = gb.DEFAULT_AXES
    try:
        if os.path.exists(gb.AXES_FILE):
            axes = json.load(open(gb.AXES_FILE)) or axes
    except Exception:
        pass
    labels = {a.get("id"): a.get("label") for a in gb.DEFAULT_AXES if isinstance(a, dict)}
    labels.update({a.get("id"): a.get("label") for a in axes if isinstance(a, dict) and a.get("label")})
    return labels


def plan(db, gb):
    """(to_restate, skipped) — lists of (row, reason). Pure: changes nothing."""
    labels = _lean_labels(gb)
    todo, skipped = [], []
    for h in (db.get("hypotheses", []) if isinstance(db, dict) else []):
        if not isinstance(h, dict) or h.get("source") != "ghost_branch":
            continue
        label = labels.get(h.get("successful_lean"))
        if h.get("test_basis") == gb.TEST_BASIS:
            skipped.append((h, "already_current"))
        elif h.get("graduated") or h.get("status") == "graduated":
            skipped.append((h, "graduated"))
        elif h.get("retired") or h.get("status") == "retired":
            skipped.append((h, "retired"))
        elif not label:
            skipped.append((h, "lean_unknown"))
        elif not str(h.get("hypothesis") or "").startswith(label):
            # the lean was relabelled since this row formed: the test would name a different lean than the claim
            skipped.append((h, "label_mismatch"))
        else:
            todo.append((h, label))
    return todo, skipped


def _rid(h):
    return str(h.get("id") or h.get("hypothesis_id") or "?")


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    unknown = [a for a in argv if a != "--apply"]
    if unknown:
        print("unknown argument(s): %s - nothing done. Usage: ghost_test_restate.py [--apply]" % " ".join(unknown))
        return 2
    apply = "--apply" in argv
    gb = _ghost_module()
    path = gb.CAUSALITY_FILE
    from store_guard import transaction
    with transaction(path):
        try:
            db = json.load(open(path))
        except FileNotFoundError:
            print("no causality store at the expected path - nothing to do"); return 0
        except Exception as e:
            print("causality store unreadable (%s) - nothing done" % type(e).__name__); return 1
        todo, skipped = plan(db, gb)
        ghost_rows = len(todo) + len(skipped)
        print("ghost_branch rows: %d | to restate: %d | skipped: %d" % (ghost_rows, len(todo), len(skipped)))
        reasons = {}
        for h, why in skipped:
            reasons.setdefault(why, []).append(_rid(h))
        for why, ids in sorted(reasons.items()):
            print("  skipped (%s): %d  %s" % (why, len(ids), " ".join(ids)))
        print("  to restate: " + (" ".join(_rid(h) for h, _ in todo) or "none"))
        if not apply:
            print("DRY RUN - nothing written. Run with --apply to restate.")
            return 0
        if not todo:
            print("nothing to restate - nothing written"); return 0
        backup = path + ".bak-ghost-restate-" + datetime.now().strftime("%Y%m%d-%H%M%S")
        shutil.copy2(path, backup)
        at = datetime.now().isoformat(timespec="seconds")
        for h, label in todo:
            if "test_before_restate" not in h:
                h["test_before_restate"] = h.get("test", "")
            h["test"] = gb.real_behaviour_test(label, h.get("failed_primary_pattern"), h.get("thread_type"),
                                               h.get("successful_lean"))
            h["test_basis"] = gb.TEST_BASIS
            h["test_restated_at"] = at
        from store_guard import save_json
        save_json(path, db)
        print("restated %d row(s); backup at %s" % (len(todo), os.path.basename(backup)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
