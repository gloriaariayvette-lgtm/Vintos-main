#!/usr/bin/env python3
"""Put graduations that a broken reviewer "held" back to eligible_day_7.

Until 2026-11-06 a reviewer error (unreachable, or a reply cut off before its JSON closed:
"no JSON object in reviewer reply") retired an eligible hypothesis for good as
graduation_review_held, the same as a real rejection. The engine now retries a broken
review on later nights. This repair finds the rows that were retired only because the
reviewer failed and proposes returning them to the active store, eligible, with one
reviewer attempt already counted, so the next nightly pass reviews them again.

Dry run by default: it reads the store, the retired log and the review flags, prints every
change it would make, and writes nothing. --apply appends the rows under the store lock.
Rows a real review held (a concern from a working reviewer) are never touched.

    python3 scripts/repairs/reinstate_reviewer_error_holds.py            # dry run
    python3 scripts/repairs/reinstate_reviewer_error_holds.py --ids CH-...  # limit to ids
    python3 scripts/repairs/reinstate_reviewer_error_holds.py --apply
"""
import argparse, copy, importlib.util, json, os, sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
ENGINE_PATH = HERE.parent / "causality-engine.py"


def load_engine():
    sys.path.insert(0, str(HERE.parent))
    spec = importlib.util.spec_from_file_location("causality_engine_repair", ENGINE_PATH)
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    return mod


def _read_jsonl(path):
    try:
        with open(path) as handle:
            return [json.loads(line) for line in handle if line.strip()]
    except FileNotFoundError:
        return []


def _reviewer_error_ids(flags):
    out = {}
    for f in flags if isinstance(flags, list) else []:
        if not isinstance(f, dict) or f.get("type") != "graduation_held":
            continue
        if (f.get("held_reason") == "reviewer_unreachable"
                or str(f.get("concern", "")).startswith("reviewer unreachable")):
            out[f.get("hypothesis_id")] = str(f.get("concern", ""))[:200]
    return out


def plan(engine, only_ids=None, now=None):
    memory = engine.MEMORY
    now = now or datetime.now().isoformat()
    try:
        flags = json.load(open(os.path.join(memory, "hallucination-flags.json")))
    except (FileNotFoundError, ValueError):
        flags = []
    errors = _reviewer_error_ids(flags)
    retired = _read_jsonl(engine.RETIRED_PATH)
    db = engine._read_hypotheses()
    active = {engine._hypothesis_id(h) for h in db.get("hypotheses", [])}
    latest = {}
    for row in retired:                      # the last retirement of each id is its current state
        latest[row.get("hypothesis_id")] = row
    proposals, skipped = [], []
    for hid, row in latest.items():
        if (row.get("retirement") or {}).get("reason") != "graduation_review_held":
            continue
        if only_ids and hid not in only_ids:
            continue
        if hid not in errors:
            skipped.append((hid, "held by a working reviewer"))
            continue
        if hid in active:
            skipped.append((hid, "already active"))
            continue
        h = copy.deepcopy(row)
        h.pop("transition_id", None)
        prior = h.pop("retirement", None)
        basis = (h.get("graduation_review") or {}).get("basis")
        h["status"] = "eligible_day_7"
        h["graduated"] = False
        h["self_knowledge"] = False
        h["graduation_review"] = {"state": "error", "basis": basis, "attempts": 1,
                                  "last_error": errors[hid], "at": now}
        h["reinstated"] = {"at": now, "from_reason": "graduation_review_held",
                           "prior_retirement_at": (prior or {}).get("at"),
                           "by": "repairs/reinstate_reviewer_error_holds"}
        ready = engine.graduation_readiness(h)
        proposals.append({"hypothesis_id": hid, "source": h.get("source"),
                          "formed_date": h.get("formed_date"), "readiness": ready["state"],
                          "readiness_reason": ready.get("reason", ""), "row": h})
    # Would the next save keep them? Simulate the save-time retirements on a copy.
    trial = copy.deepcopy(db)
    trial.setdefault("hypotheses", []).extend(copy.deepcopy(p["row"]) for p in proposals)
    gone = {engine._hypothesis_id(h) for h in engine._retire_stale_unconfirmed(trial)}
    gone |= {engine._hypothesis_id(h) for h in engine._retire_formation_overflow(trial)}
    for p in proposals:
        p["survives_next_save"] = p["hypothesis_id"] not in gone
    return db, proposals, skipped


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--apply", action="store_true", help="write the change (default: dry run)")
    ap.add_argument("--ids", nargs="*", default=None, help="limit to these hypothesis ids")
    args = ap.parse_args()
    engine = load_engine()
    _, proposals, skipped = plan(engine, set(args.ids) if args.ids else None)
    mode = "APPLY" if args.apply else "DRY RUN (nothing written)"
    print("[repair] %s - store %s" % (mode, engine.HYPOTHESIS_DB))
    for p in proposals:
        print("[repair] reinstate %s (%s, formed %s): retired graduation_review_held -> eligible_day_7, "
              "review attempts 1/%d; readiness now %s%s; survives next save: %s" % (
                  p["hypothesis_id"], p["source"], p["formed_date"], engine.REVIEW_RETRY_CAP,
                  p["readiness"], (" (" + p["readiness_reason"] + ")") if p["readiness_reason"] else "",
                  p["survives_next_save"]))
    for hid, why in skipped:
        print("[repair] leave %s: %s" % (hid, why))
    print("[repair] would change %d row(s); %d left alone" % (len(proposals), len(skipped)))
    if not args.apply or not proposals:
        return 0
    with engine.transaction(engine.HYPOTHESIS_DB):
        fresh = engine._read_hypotheses()
        have = {engine._hypothesis_id(h) for h in fresh.get("hypotheses", [])}
        added = [p["row"] for p in proposals if p["hypothesis_id"] not in have]
        fresh.setdefault("hypotheses", []).extend(added)
        engine._save_hypotheses_locked(fresh)
    print("[repair] reinstated %d row(s)" % len(added))
    return 0


if __name__ == "__main__":
    sys.exit(main())
