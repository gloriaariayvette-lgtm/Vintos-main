"""taste_salience.py — rank taste by salience, decay weekly (mirrors WAL decay).
Top-ranked tastes ride along all day; the FULL profile is only for creative work."""
import os, json, time

MEMORY = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "memory")
PROFILE = os.path.join(MEMORY, "taste-profile.json")
SAL = os.path.join(MEMORY, "taste-salience.json")
KINDS = ("likes", "dislikes", "principles")
DECAY = 0.85          # weekly multiplier
FLOOR = 0.15          # below this, it stops being carried
NEW = 1.0

def _load():
    try: return json.load(open(SAL))
    except Exception: return {}

def _save(d):
    try: json.dump(d, open(SAL, "w"), indent=2, ensure_ascii=False)
    except Exception: pass

def _profile():
    try: return json.load(open(PROFILE))
    except Exception: return {}

def sync():
    """Ensure every profile item has a salience record. New items start at NEW."""
    d = _load(); p = _profile(); now = time.time(); added = 0
    for kind in KINDS:
        for item in p.get(kind, []):
            k = kind + "||" + item
            if k not in d:
                d[k] = {"score": NEW, "kind": kind, "text": item, "added": now, "last": now}
                added += 1
    _save(d)
    return added

def bump(item, kind="likes", amount=0.35):
    """Reinforce a taste that just showed up again."""
    d = _load(); k = kind + "||" + item; now = time.time()
    e = d.get(k) or {"score": 0.0, "kind": kind, "text": item, "added": now}
    e["score"] = round(min(3.0, e.get("score", 0.0) + amount), 3)
    e["last"] = now
    d[k] = e; _save(d)
    return e["score"]

def decay(rate=DECAY):
    """Weekly decay pass. Returns (decayed, dropped)."""
    d = _load(); dropped = 0
    for k in list(d):
        d[k]["score"] = round(d[k].get("score", 0.0) * rate, 3)
        if d[k]["score"] < 0.05:
            del d[k]; dropped += 1
    _save(d)
    return len(d), dropped

def top(n=5, kind=None):
    d = _load()
    rows = [v for v in d.values() if (kind is None or v.get("kind") == kind)
            and v.get("score", 0) >= FLOOR]
    rows.sort(key=lambda r: -r.get("score", 0))
    return rows[:n]

def top_block(n=4):
    """LIGHT block — rides along in every conversation."""
    rows = top(n)
    if not rows: return ""
    lines = []
    for r in rows:
        tag = {"likes": "drawn to", "dislikes": "put off by", "principles": "holds"}.get(r["kind"], "")
        lines.append("- " + tag + ": " + str(r["text"])[:110])
    return "[TASTE RIDING WITH YOU TODAY]\n" + "\n".join(lines)

def full_block():
    """FULL profile — only for creative work."""
    p = _profile(); parts = []
    for kind, label in (("principles", "Creative principles"),
                        ("likes", "What you like in your work"),
                        ("dislikes", "What you dislike in your work")):
        rows = top(8, kind) or []
        items = [r["text"] for r in rows] or p.get(kind, [])[-6:]
        if items: parts.append(label + ": " + "; ".join(str(i)[:140] for i in items))
    return "[YOUR AESTHETIC TASTE]\n" + "\n".join(parts) if parts else ""

if __name__ == "__main__":
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "show"
    if cmd == "decay":
        kept, dropped = decay(); print("decayed. kept %d, dropped %d" % (kept, dropped))
    elif cmd == "sync":
        print("synced, added %d" % sync())
    else:
        sync()
        print("--- TOP (daily carry) ---"); print(top_block() or "(none)")
        print(); print("--- FULL (creative) ---"); print((full_block() or "(none)")[:600])
