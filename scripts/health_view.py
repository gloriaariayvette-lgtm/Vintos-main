#!/usr/bin/env python3
"""health_view.py - the state of every store, in words that mean different things.

Review item 389 (2026-09-10). "Nothing there" used to mean four different things. Here each store is
one of: quiet (present, parses, nothing recent - normal silence), live (present, parses, written within
its expected window), unavailable (the file does not exist), malformed (exists but does not parse; the
quarantine will have it), unsupported (parses but is not the shape its readers expect), and the
services are asked the same way (broker up / unavailable). Read-only.

    python3 health_view.py            print the view
    python3 health_view.py --json
"""
import os, sys, json, time

WS = os.path.expanduser("~/.vintos/workspace")
MEMORY = os.path.join(WS, "memory")
# store -> (expected top-level shape, expected freshness window in hours; None = no expectation)
STORES = {
    "interaction-ledger.json": ("list|entries", 72), "current-wants.json": ("list", None), "unfinished-threads.json": ("list", 72),
    "emotional-state.json": ("dict", 1), "causal-self-model.json": ("entries", None), "belief-sediment.json": ("beliefs", None),
    "commitment-imprints.json": ("imprints", None), "taste-vector.json": ("dict", None), "durable-memory.json": ("list", None),
    "wal-log.json": ("list|entries", 72), "semantic-index.json": ("entries", 168), "dream-log.json": ("nights", 72),
    "atelier-undertakings.json": ("dict", None), "compute-ledger.jsonl": ("jsonl", 24), "post-turn-record.jsonl": ("jsonl", 72),
}


def _shape_ok(obj, want):
    for w in want.split("|"):
        if w == "list" and isinstance(obj, list): return True
        if w == "dict" and isinstance(obj, dict): return True
        if w not in ("list", "dict") and isinstance(obj, dict) and w in obj: return True
    return False


def store_state(name, want, window_h, now=None):
    p = os.path.join(MEMORY, name); now = now or time.time()
    if not os.path.exists(p):
        return {"store": name, "state": "unavailable", "why": "no file"}
    age_h = (now - os.path.getmtime(p)) / 3600.0
    try:
        raw = open(p, errors="replace").read()
        if want == "jsonl":
            for ln in raw.splitlines()[-5:]:
                if ln.strip(): json.loads(ln)
            obj = None
        else:
            obj = json.loads(raw) if raw.strip() else None
    except Exception as e:
        return {"store": name, "state": "malformed", "why": str(e)[:80], "age_h": round(age_h, 1)}
    if want != "jsonl" and (obj is None or not _shape_ok(obj, want)):
        return {"store": name, "state": "unsupported", "why": "expected %s, found %s" % (want, type(obj).__name__), "age_h": round(age_h, 1)}
    if window_h is not None and age_h > window_h:
        return {"store": name, "state": "quiet", "why": "last written %.1f h ago (window %d h)" % (age_h, window_h), "age_h": round(age_h, 1)}
    return {"store": name, "state": "live", "age_h": round(age_h, 1)}


def view(now=None):
    rows = [store_state(n, w, h, now) for n, (w, h) in STORES.items()]
    services = {}
    try:
        sys.path.insert(0, os.path.join(WS, "scripts")); sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import atelier_ledger as _al
        services["broker"] = _al.broker_state()
    except Exception as e:
        services["broker"] = {"broker": "unknown", "why": str(e)[:60]}
    try:
        import store_guard as _sg
        services["quarantined"] = _sg.quarantined(limit=5)
    except Exception:
        pass
    counts = {}
    for r in rows: counts[r["state"]] = counts.get(r["state"], 0) + 1
    # review 376: the receipts beside the stores - the last deliveries, effects and paid reservations
    receipts = {}
    try:
        d = json.load(open(os.path.join(MEMORY, "delivery-receipts.json")))
        rs = d.get("receipts", d) if isinstance(d, dict) else d
        receipts["delivery"] = (list(rs.values()) if isinstance(rs, dict) else rs)[-5:]
    except Exception:
        receipts["delivery"] = "none"
    for name, key in (("effects", "effect-receipts.jsonl"), ("compute", "compute-ledger.jsonl")):
        try:
            lines = [ln for ln in open(os.path.join(MEMORY, key)) if ln.strip()][-5:]
            receipts[name] = [json.loads(ln) for ln in lines]
        except Exception:
            receipts[name] = "none"
    return {"at": time.strftime("%Y-%m-%dT%H:%M:%S"), "stores": rows, "counts": counts, "services": services, "receipts": receipts}


if __name__ == "__main__":
    v = view()
    if "--json" in sys.argv:
        print(json.dumps(v, indent=1))
    else:
        print("stores:", v["counts"])
        for r in v["stores"]:
            print("  %-28s %-12s %s" % (r["store"], r["state"], r.get("why", "")))
        print("broker:", v["services"].get("broker"))
