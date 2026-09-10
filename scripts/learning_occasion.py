#!/usr/bin/env python3
"""learning_occasion.py - the same event may be replayed as often as it likes; it teaches once.

Review item 49 (2026-09-10). Several organs already refused a second count for their own kind of
occasion (a pearl graded once, a taste occurrence counted once, a prediction graded once, a turn's
recurrence not re-counted on replay). Each knew only its own. This is the one door for the rest: an
occasion is (learner, occurrence_id); the first call is the teaching one, every later call is a
replay. A replay LOSES NOTHING - the record keeps that it happened and when - it simply does not
count a second time.

    teach(learner, occurrence_id, detail=None)  -> {"first": bool, "count": n, "first_at": ...}
    seen(learner, occurrence_id)                -> the record, or None
"""
import os, json, time

WS = os.path.expanduser("~/.vintos/workspace")
MEMORY = os.path.join(WS, "memory")
STORE = os.path.join(MEMORY, "learning-occasions.json")


def _sg():
    try:
        import sys as _s
        _s.path.insert(0, os.path.join(WS, "scripts")); _s.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import store_guard as _g
        return _g
    except Exception:
        return None


def _key(learner, occurrence_id):
    return "%s\x00%s" % (learner, occurrence_id)


def teach(learner, occurrence_id, detail=None, now=None):
    now = now if now is not None else time.time()
    k = _key(learner, str(occurrence_id))
    out = {}

    def mutate(cur):
        d = cur if isinstance(cur, dict) else {}
        rec = d.get(k)
        if rec is None:
            rec = {"learner": learner, "occurrence_id": str(occurrence_id), "first_at": now, "count": 1,
                   "replays": [], "detail": detail}
            out.update({"first": True, "count": 1, "first_at": now})
        else:
            rec["count"] = int(rec.get("count", 1)) + 1
            rec.setdefault("replays", []).append(now)
            rec["replays"] = rec["replays"][-20:]
            out.update({"first": False, "count": rec["count"], "first_at": rec.get("first_at")})
        d[k] = rec
        return {kk: vv for kk, vv in sorted(d.items(), key=lambda kv: kv[1].get("first_at", 0))[-4000:]}

    g = _sg()
    if g is not None:
        g.locked_update(STORE, mutate, default={}, reader="learning_occasion")
    else:
        try: cur = json.load(open(STORE))
        except Exception: cur = {}
        d = mutate(cur)
        os.makedirs(MEMORY, exist_ok=True)
        tmp = STORE + ".tmp"; json.dump(d, open(tmp, "w")); os.replace(tmp, STORE)
    return out


def seen(learner, occurrence_id):
    try:
        return json.load(open(STORE)).get(_key(learner, str(occurrence_id)))
    except Exception:
        return None
