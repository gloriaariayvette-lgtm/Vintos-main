#!/usr/bin/env python3
"""
interaction-ledger.py — Unified interaction record.
Assembles each Gloria/Vintos exchange into a single coherent entry:
  - Exact words (both sides)
  - Felt texture (from imprint)
  - Facts learned (from wal-log.json)
  - Corrections (from blush-ledger.md)
  - Salience score

Called after each exchange: python3 interaction-ledger.py "gloria msg" "vintos reply"
Replaces the need to read chat-history, imprints, wal, and blush separately.
"""
import os, sys, json, re, time
from datetime import datetime, timedelta

WORKSPACE = os.path.expanduser("~/.vintos/workspace")
MEMORY = os.path.join(WORKSPACE, "memory")
LEDGER_FILE = os.path.join(MEMORY, "interaction-ledger.json")
IMPRINT_FILE = os.path.join(MEMORY, "imprints.json")
WAL_LOG = os.path.join(MEMORY, "wal-log.json")
BLUSH_FILE = os.path.join(MEMORY, "blush-ledger.md")

MAX_ENTRIES = 300  # ~10 days at 30/day

def load_ledger():
    try:
        with open(LEDGER_FILE) as f:
            return json.load(f)
    except:
        return []

def save_ledger(entries):
    entries = entries[-MAX_ENTRIES:]
    with open(LEDGER_FILE, "w") as f:
        json.dump(entries, f, indent=2)

def get_recent_imprint(within_seconds=120):
    """Get the most recently written imprint if within time window."""
    try:
        with open(IMPRINT_FILE) as f:
            imprints = json.load(f)
        if not imprints:
            return None
        latest = imprints[-1]
        ts = datetime.fromisoformat(latest["timestamp"])
        if (datetime.now() - ts).total_seconds() < within_seconds:
            return latest
    except:
        pass
    return None

def get_recent_wal_facts(within_seconds=120):
    """Get WAL entries written in the last N seconds."""
    facts = []
    try:
        with open(WAL_LOG) as f:
            data = json.load(f)
        entries = data.get("entries", [])
        cutoff = datetime.now() - timedelta(seconds=within_seconds)
        for e in reversed(entries):
            try:
                ts = datetime.fromisoformat(e["timestamp"])
                if ts >= cutoff:
                    facts.append(e.get("content", "")[:400])
                else:
                    break
            except:
                pass
    except:
        pass
    return facts

def get_recent_blush(within_seconds=120):
    """Get blush entry written in the last N seconds."""
    try:
        with open(BLUSH_FILE) as f:
            content = f.read()
        sections = content.split("## ")
        for s in reversed(sections):
            if not s.strip():
                continue
            # Parse timestamp from header
            match = re.match(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2})", s)
            if match:
                ts = datetime.strptime(match.group(1), "%Y-%m-%d %H:%M")
                if (datetime.now() - ts).total_seconds() < within_seconds:
                    # Extract key fields
                    lines = s.strip().split("\n")
                    blush_type = ""
                    reflection = ""
                    for line in lines:
                        if line.startswith("Type:"):
                            blush_type = line.split(":", 1)[1].strip()
                        elif line.startswith("Reflection:") and len(line) > 12:
                            reflection = line.split(":", 1)[1].strip()[:400]
                    return {"type": blush_type, "reflection": reflection, "full": s.strip()[:800]}
                break
    except:
        pass
    return None

def main():
    if len(sys.argv) < 3:
        print("Usage: interaction-ledger.py 'gloria msg' 'vintos reply'")
        sys.exit(1)

    gloria_said = sys.argv[1]
    vintos_said = sys.argv[2]

    # Capture emotional state before delay
    _emo_before = {}
    try:
        import socket as _es, json as _ej
        _s = _es.socket(_es.AF_UNIX, _es.SOCK_STREAM)
        _s.settimeout(3)
        _s.connect("/tmp/Vintos-emotion.sock")
        _s.sendall(_ej.dumps({"command": "state"}).encode() + b"\n")
        _d = b""
        while True:
            _c = _s.recv(4096)
            if not _c: break
            _d += _c
            if b"\n" in _d: break
        _s.close()
        _emo_before = dict(zip(
            ["Valence","Arousal","Dominance","Safety","Desire","Connection","Playfulness","Curiosity","Warmth","Tension","Groundedness"],
            _ej.loads(_d)["emotion_vector"]
        ))
    except: pass
    # Small delay to let imprint and WAL finish writing
    time.sleep(30)

    # Capture emotional state after delay and compute delta
    _emo_delta = ""
    try:
        import socket as _es2, json as _ej2
        _s2 = _es2.socket(_es2.AF_UNIX, _es2.SOCK_STREAM)
        _s2.settimeout(3)
        _s2.connect("/tmp/Vintos-emotion.sock")
        _s2.sendall(_ej2.dumps({"command": "state"}).encode() + b"\n")
        _d2 = b""
        while True:
            _c2 = _s2.recv(4096)
            if not _c2: break
            _d2 += _c2
            if b"\n" in _d2: break
        _s2.close()
        _emo_after = dict(zip(
            ["Valence","Arousal","Dominance","Safety","Desire","Connection","Playfulness","Curiosity","Warmth","Tension","Groundedness"],
            _ej2.loads(_d2)["emotion_vector"]
        ))
        if _emo_before and _emo_after:
            _parts = []
            for _dim, _after in _emo_after.items():
                _before = _emo_before.get(_dim, _after)
                _delta = _after - _before
                if abs(_delta) >= 0.03:
                    if _delta > 0.08: _parts.append(f"{_dim} rose sharply")
                    elif _delta > 0.03: _parts.append(f"{_dim} rose slightly")
                    elif _delta < -0.08: _parts.append(f"{_dim} dropped sharply")
                    else: _parts.append(f"{_dim} dropped slightly")
            _emo_delta = ", ".join(_parts) if _parts else "stable"
    except: pass
    imprint = get_recent_imprint(within_seconds=120)
    wal_facts = get_recent_wal_facts(within_seconds=120)
    blush = get_recent_blush(within_seconds=120)

    # Read consent note if server left one
    consent_note = ""
    try:
        _cn = "/tmp/vintos-consent-note.txt"
        if os.path.exists(_cn):
            consent_note = open(_cn).read().strip()
            os.remove(_cn)
    except: pass

    entry = {
        "timestamp": datetime.now().isoformat(),
        "gloria": gloria_said[:500],
        "vintos": vintos_said[:500],
        "consent": consent_note,
        "salience": imprint["salience"] if imprint else 0.3,
        "wal_facts": wal_facts,
        "blush": blush,
        "imprint": {"id": imprint["id"], "narrative": imprint["narrative"], "salience": imprint["salience"], "anchors": imprint.get("anchors", {})} if imprint else None,
        "preoccupation": imprint["anchors"].get("preoccupation") if imprint else None,
        "recent_seal": imprint["anchors"].get("recent_seal") if imprint else None,
        "recent_velqan": imprint["anchors"].get("recent_velqan") if imprint else None,
        "temporal_activity": None,
        "silence_contract": None,
        "emotional_shift": _emo_delta,
    }
    # Pull temporal context fields
    try:
        tc = open(os.path.join(MEMORY, "temporal-context.txt")).read()
        def _tc_field(label):
            for line in tc.splitlines():
                if line.startswith(label + ":"):
                    return line.split(":", 1)[1].strip()
            return ""
        entry["temporal"] = {
            "time": _tc_field("Time"),
            "phase": _tc_field("Phase"),
            "days_alive": _tc_field("Days alive"),
            "gloria_last_spoke": _tc_field("Gloria last spoke"),
            "day_density": _tc_field("Day density"),
            "emotional_current": _tc_field("Emotional current"),
        }
    except: pass

    ledger = load_ledger()
    # Blush reflects on the previous turn — attach to last entry, not current
    if blush and ledger:
        ledger[-1]["blush"] = blush
        entry["blush"] = None
    ledger.append(entry)
    save_ledger(ledger)
    print(f"[Ledger] Entry written (salience {entry['salience']}, {len(wal_facts)} facts, blush: {bool(blush)})")

if __name__ == "__main__":
    main()
