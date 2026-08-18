#!/usr/bin/env python3
"""dream_heat_seed.py — 6b 'dreams seek heat': set the hottest unconsumed thread as the preoccupation
before the dream cycle, so the dream pulls toward what is most volatile. Skips if one is already set."""
import os, sys, json
SCRIPTS = os.path.expanduser("~/.vintos/workspace/scripts")
sys.path.insert(0, SCRIPTS)
THREADS = os.path.expanduser("~/.vintos/workspace/memory/unfinished-threads.json")
def main():
    try:
        from emoclaw_utils import set_preoccupation, get_preoccupation
    except Exception as e:
        print("[heat-seed] emoclaw_utils unavailable:", e); return
    _existing = get_preoccupation()
    if _existing:
        # Only leave it if it will still be alive when the dream runs (~30 min from now).
        # Otherwise it expires in the gap and the dream wakes to nothing.
        try:
            from datetime import datetime as _hd, timedelta as _ht
            _exp = _hd.fromisoformat(str(_existing.get("expires_at", ""))[:19])
            if _exp - _hd.now() > _ht(minutes=30):
                print("[heat-seed] preoccupation already set - leaving it."); return
            print("[heat-seed] existing preoccupation expires within 30m - replacing it.")
        except Exception:
            print("[heat-seed] preoccupation already set - leaving it."); return
    try:
        d = json.load(open(THREADS)); threads = d if isinstance(d, list) else d.get("threads", [])
    except Exception as e:
        print("[heat-seed] no threads:", e); return
    unconsumed = [t for t in threads if isinstance(t, dict) and not t.get("consumed")]
    if not unconsumed:
        print("[heat-seed] nothing unconsumed."); return
    best = max(unconsumed, key=lambda t: ((t.get("temperature") or 0), (t.get("priority") or 0)))
    ok = set_preoccupation(str(best.get("thread",""))[:200], "heat-seed",
                           int(best.get("priority") or 3), best.get("triage_voice",""))
    print(f"[heat-seed] {'set' if ok else 'not set'}: T={best.get('temperature')} pull={best.get('priority')} "
          f"[{best.get('source')}] {str(best.get('thread',''))[:60]}")
if __name__ == "__main__":
    main()
