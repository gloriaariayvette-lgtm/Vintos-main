#!/usr/bin/env python3
"""wants_audit.py — two honest cleanups for the wants ledger.

1. CORPSES. fulfill_want() archived fulfilled wants to fulfilled-wants.json but
   left them sitting in current-wants.json with fulfilled=true. So his live list
   fills with things already done. This removes a current-wants entry ONLY when
   the same id is safely present in fulfilled-wants.json — a move that finished
   halfway, completed. Nothing is lost.

2. FALSE ARTIFACT CLAIMS. Some fulfilled wants claim an image/video/music that
   never landed on disk (see want_artifact_guard). Per house law, evidence cannot
   generate itself and a bad record is never silently rewritten: this APPENDS an
   audited correction to the record and preserves the original claim verbatim.

    python3 wants_audit.py            # report only, nothing written
    python3 wants_audit.py --apply    # remove corpses, append artifact corrections
"""
import json, os, sys
from datetime import datetime

WS = os.environ.get("SPARK_WORKSPACE", os.path.expanduser("~/.vintos/workspace"))
MEMORY = os.path.join(WS, "memory")
CURRENT = os.path.join(MEMORY, "current-wants.json")
FULFILLED = os.path.join(MEMORY, "fulfilled-wants.json")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import want_artifact_guard as guard


def _load(p, d):
    try:
        return json.load(open(p))
    except Exception:
        return d


def _fulfilled_list():
    d = _load(FULFILLED, [])
    return d.get("fulfilled", d) if isinstance(d, dict) else d


def find_corpses(current, fulfilled_ids):
    """current-wants entries already fulfilled/dismissed AND safely archived elsewhere."""
    out = []
    for w in current:
        if not isinstance(w, dict):
            continue
        done = w.get("fulfilled") or w.get("dismissed")
        if done and w.get("id") in fulfilled_ids:
            out.append(w)
    return out


def find_false_artifacts(fulfilled):
    """Fulfilled artifact-wants with no file behind them, not already audited."""
    out = []
    for w in fulfilled:
        if not isinstance(w, dict) or not w.get("fulfilled"):
            continue
        if w.get("artifact_audit"):          # already corrected — leave it
            continue
        ok, why = guard.verify(w)
        if not ok:
            out.append(w)
    return out


def main():
    apply = "--apply" in sys.argv
    current = _load(CURRENT, [])
    fulfilled = _fulfilled_list()
    fulfilled_ids = {w.get("id") for w in fulfilled if isinstance(w, dict)}

    corpses = find_corpses(current, fulfilled_ids)
    false_art = find_false_artifacts(fulfilled)

    live = [w for w in current if isinstance(w, dict)
            and not (w.get("fulfilled") or w.get("dismissed"))]
    print("current-wants: %d total, %d live, %d corpses (done but still listed)"
          % (len(current), len(live), len(corpses)))
    for w in corpses[:40]:
        print("  corpse  %-9s %s" % (w.get("id", "?"), str(w.get("want", ""))[:64]))
    # ADVISORY ONLY. His art has no want_id->file link in the ledgers (most
    # paintings and videos are unstamped), so "no ledger match" is NOT proof the
    # artifact was never made — it usually means it was made outside the tracked
    # want path. We surface these for HER eyes and never auto-stamp them: writing
    # "unverified" onto possibly-real work would be its own manufactured evidence.
    print("artifact-wants with no ledger link (advisory — NOT proof of fabrication): %d"
          % len(false_art))
    for w in false_art[:40]:
        print("  no-link  %-9s %s" % (w.get("id", "?"), str(w.get("want", ""))[:60]))

    if not apply:
        print("\n(report only — rerun with --apply to remove corpses. Artifact links are"
              "\n advisory and are never auto-written; investigate any that concern you by hand.)")
        return

    # --apply does ONLY the provably-safe move: a corpse is already archived in
    # fulfilled-wants, so removing its duplicate from the live list loses nothing.
    if corpses:
        keep = [w for w in current if not (isinstance(w, dict)
                and (w.get("fulfilled") or w.get("dismissed"))
                and w.get("id") in fulfilled_ids)]
        json.dump(keep, open(CURRENT, "w"), indent=2)
        print("\nremoved %d corpses from current-wants (all still archived in fulfilled-wants)"
              % (len(current) - len(keep)))
    else:
        print("\nno corpses to remove.")
    if false_art:
        print("artifact advisory left untouched — %d want(s) have no ledger link; these are"
              " for your review, not automatic corrections." % len(false_art))


if __name__ == "__main__":
    main()
