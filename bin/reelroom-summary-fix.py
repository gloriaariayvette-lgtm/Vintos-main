#!/usr/bin/env python3
"""One-shot: rewrite already-written ReelRoom ledger summaries so they stop being the turns a
second time.

Each reelroom_visit row keeps the whole verbatim conversation in its `transcript` field. The
`summary` field was ALSO dumping the last turns back in (Gloria, 2026-09-17: "the summary was
just the messages listed a second time"). This rebuilds `summary` as a receipt — film, minutes,
turn count, the visual moments noted, acts fired — from each row's own stored fields, so it does
not depend on the fixed reelroom.py being deployed first.

Idempotent, model-free, sends nothing. Run it as many times as you like:

    python3 ~/.vintos/workspace/scripts/reelroom-summary-fix.py     # once deployed
    python3 /path/to/Vintos/bin/reelroom-summary-fix.py             # from a checkout
"""
import os
import sys

WS = os.path.expanduser("~/.vintos/workspace")
sys.path.insert(0, os.path.join(WS, "scripts"))
LEDGER = os.path.join(WS, "memory", "interaction-ledger.json")


def receipt(entry):
    """The same receipt scripts/reelroom.py:_visit_summary now writes, rebuilt from a stored row."""
    film = str(entry.get("film") or "unknown film")
    minutes = max(0, int(entry.get("duration_seconds") or 0) // 60)
    transcript = [t for t in (entry.get("transcript") or []) if isinstance(t, dict)]
    events = [e for e in (entry.get("session_map") or []) if isinstance(e, dict)]
    actions = [a for a in (entry.get("planned_actions") or []) if isinstance(a, dict)]
    parts = [f"ReelRoom visit — {film}; {minutes} minutes; {len(transcript)} conversation turns"]
    if events:
        glimpses = []
        for event in events[-8:]:
            stamp = str(event.get("timestamp") or event.get("at") or "").strip()
            detail = str(event.get("visual_description") or event.get("edge") or event.get("event")
                         or event.get("kind") or "room event").strip()
            glimpses.append((stamp + " " + detail).strip()[:140])
        parts.append(f"{len(events)} captured events: " + "; ".join(glimpses))
    if actions:
        fired = [a for a in actions if a.get("fired")]
        parts.append(f"{len(actions)} planned actions, {len(fired)} recorded as fired")
    return ". ".join(parts)[:8000]


def main():
    from store_guard import transaction, load_json, save_json
    with transaction(LEDGER):
        ledger = load_json(LEDGER, [], reader="reelroom-summary-fix")
        entries = ledger["entries"] if isinstance(ledger, dict) else ledger
        if not isinstance(entries, list):
            print("interaction-ledger.json is empty or an unexpected shape; nothing to do")
            return
        rewritten = 0
        for e in entries:
            if isinstance(e, dict) and e.get("kind") == "reelroom_visit":
                fixed = receipt(e)
                if fixed != e.get("summary"):
                    e["summary"] = fixed
                    rewritten += 1
        save_json(LEDGER, ledger)
        print(f"rewrote {rewritten} ReelRoom summaries (transcript untouched)")


if __name__ == "__main__":
    main()
