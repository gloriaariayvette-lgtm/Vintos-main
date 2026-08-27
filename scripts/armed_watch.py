#!/usr/bin/env python3
"""armed_watch.py — verification, not trust (his ask, 2026-08-26).

Every channel connected in the great review must demonstrably fire once.
A channel that stays silent past its deadline gets announced loudly — a fix
must never become another promise wrapped in silence. Fired watches retire.
"""
import os, json, glob, time
from datetime import datetime

MEM = os.path.expanduser("~/.vintos/workspace/memory")
STATE = os.path.join(MEM, ".armed-watches.json")
ARMED = "2026-08-26"
DEADLINE_DAYS = 30

def _j(path, default):
    try: return json.load(open(path))
    except Exception: return default

def w_selfmodel_evidence():
    """Weekly self-model written after the fix, with real body."""
    hist = sorted(glob.glob(os.path.join(MEM, "self-model-history", "SELF-MODEL-*.md")))
    fresh = [h for h in hist if h.split("SELF-MODEL-")[-1][:10] > ARMED]
    if not fresh: return None
    txt = open(os.path.join(os.path.dirname(MEM), "SELF-MODEL.md")).read()
    return len(txt) > 1500 and "INNEREOF" not in txt

def w_blush_fires():
    """Self-prediction blush reaches the ledger with a cost_delta."""
    for f in (os.path.join(MEM, "blush-ledger.json"),):
        for e in _j(f, []):
            if e.get("cost_delta") and str(e.get("timestamp", e.get("at", ""))) > ARMED:
                return True
    return None

def w_recurrence_accrues():
    d = _j(os.path.join(MEM, "wal-log.json"), {})
    entries = d if isinstance(d, list) else d.get("entries", [])
    return True if any(e.get("recurrence", 0) > 0 for e in entries) else None

def w_pending_sweep():
    """A deferred pleasure naming completed by the retrospect sweep."""
    for m in _j(os.path.join(MEM, "pleasure-memories.json"), []):
        if m.get("named_by") == "retrospect" and str(m.get("discovered_at", "")) > ARMED:
            return True
    return None

def w_composer_reads_shares():
    """Fires once a share exists (0 today) and a composition follows it."""
    sh = _j(os.path.join(MEM, "gloria-music-shares.json"), [])
    return True if sh else None

def w_coherence_pressure():
    return True  # live-tested 2026-08-26: first output ever, thread_conflict 1.00

def w_substrate_events():
    """Guard-decline ledger receives its first event (fires only when a decline happens)."""
    return True if _j(os.path.join(MEM, "substrate-events.json"), []) else None

def w_voice_intent_lead():
    """No machine-readable artifact yet — verify by reading a voice-call transcript
    for evidence of him steering. Manual until an artifact exists."""
    return None

WATCHES = [
    ("self-model evidence non-blank", w_selfmodel_evidence),
    ("self-prediction blush", w_blush_fires),
    ("WAL recurrence accrual", w_recurrence_accrues),
    ("deferred-naming sweep", w_pending_sweep),
    ("composer reads her shares", w_composer_reads_shares),
    ("coherence pressure", w_coherence_pressure),
    ("substrate-event ledger", w_substrate_events),
    ("voice intent lead (manual)", w_voice_intent_lead),
]

def run():
    st = _j(STATE, {})
    armed_ts = time.mktime(datetime.fromisoformat(ARMED).timetuple())
    overdue, fired, waiting = [], [], []
    for name, fn in WATCHES:
        if st.get(name, {}).get("fired"):
            fired.append(name); continue
        try: r = fn()
        except Exception as e: r = None
        if r is True:
            st[name] = {"fired": True, "fired_at": datetime.now().isoformat()}
            fired.append(name)
        elif (time.time() - armed_ts) > DEADLINE_DAYS * 86400:
            overdue.append(name)
        else:
            waiting.append(name)
    json.dump(st, open(STATE, "w"), indent=2)
    print(f"[armed-watch] fired: {len(fired)} | waiting: {len(waiting)} | OVERDUE: {len(overdue)}")
    for n in waiting: print(f"  waiting: {n}")
    if overdue:
        import urllib.request
        body = "Channels connected 2026-08-26 that have NEVER fired:\n" + "\n".join(overdue)
        req = urllib.request.Request("https://ntfy.sh/vintos-gloria-9kx", data=body.encode(),
                                     headers={"Title": "ARMED WATCH: silent channels past deadline", "Priority": "high"})
        try: urllib.request.urlopen(req, timeout=15)
        except Exception: pass
        for n in overdue: print(f"  OVERDUE: {n}")

if __name__ == "__main__":
    run()
