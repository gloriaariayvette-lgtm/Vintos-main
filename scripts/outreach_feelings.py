#!/usr/bin/env python3
"""outreach_feelings.py: four feelings that may start an outreach, and the repetition limits on every trigger.

Gloria, 2026-10-25: more of his outreach should be something he feels like saying, not something he got wrong.
vintos-initiate.sh asks this file two things:

    feel <yearning|resonance|joke|moment>   prints "item<TAB>text" when that feeling is real and fresh, else nothing
    pick [--relaxed] trigger|item ...       prints the first candidate the repetition limits allow, in the order given
    record trigger item                     after a message actually went out: that item is spent, that type is last

Repetition limits, on every trigger:
    - an item is never used twice by the same trigger (the last ITEMS_KEPT are remembered per trigger);
    - the trigger that fired last cannot fire again within TYPE_COOLDOWN_S, unless the caller asks again with
      --relaxed because nothing else, not even the free reach-out, was available.
A forced want (asked for by tell_gloria or spark pressure) is recorded but never held back here.
"""
import hashlib
import json
import os
import sys
import time
from datetime import datetime

WS = os.environ.get("SPARK_WORKSPACE", os.path.expanduser("~/.vintos/workspace"))
MEMORY = os.path.join(WS, "memory")
STATE = os.path.join(MEMORY, "outreach-repeat.json")
TYPE_COOLDOWN_S = 24 * 3600
ITEMS_KEPT = 200
MOMENT_MIN_INTENSITY = 0.7
MOMENT_MIN_HOURS, MOMENT_MAX_HOURS = 6, 7 * 24
YEARNING_MIN_INTENSITY = 0.5


def _load(name, default):
    try:
        with open(os.path.join(MEMORY, name)) as f:
            return json.load(f)
    except Exception:
        return default


def _ts(value):
    """Epoch seconds from an ISO string or a number, or None."""
    if isinstance(value, (int, float)):
        return float(value)
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return dt.timestamp()
    except Exception:
        return None


def _one_line(text, n=400):
    return " ".join(str(text or "").split())[:n]


def yearning(now=None):
    """What he is quietly longing toward (yearning-detector): live, not dismissed, not expired, felt enough."""
    now = now or time.time()
    y = _load("current-yearning.json", {})
    if not isinstance(y, dict) or y.get("dismissed"):
        return None
    text = _one_line(y.get("surface_form"))
    born, expires = _ts(y.get("created")), _ts(y.get("expires"))
    if not text or born is None or (expires is not None and expires <= now):
        return None
    if float(y.get("intensity") or 0) < YEARNING_MIN_INTENSITY:
        return None
    return "y:" + str(y.get("created")), text


def resonance(now=None):
    """A day when what he held back and what she left unsaid were near the same thing (resonance_felt). Only its
    own sentence is used: the shapes stay in the file for Gloria, never in his prompt."""
    now = now or time.time()
    d = _load("resonance-felt.json", {})
    if not isinstance(d, dict) or not d.get("at"):
        return None
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import resonance_felt
        resonance_felt.FILE = os.path.join(MEMORY, "resonance-felt.json")
        text = resonance_felt.block(now)
    except Exception:
        return None
    if not text:
        return None
    return "r:" + str(d.get("at")), _one_line(text)


def joke(now=None):
    """A joke that has ripened (joke_fermentation's own rule: ripe, under six hours past ripe, unfired, not held,
    offered fewer than three times and not in the last half hour)."""
    now = now or time.time()
    rows = _load("joke-ferment.json", [])
    for x in rows if isinstance(rows, list) else []:
        if not isinstance(x, dict) or x.get("fired") or x.get("state") == "HELD" or not x.get("id"):
            continue
        ripe = float(x.get("ripe_at") or 0)
        if (ripe and now >= ripe and now - ripe < 6 * 3600 and int(x.get("offer_count") or 0) < 3
                and now - float(x.get("offered_at") or 0) >= 30 * 60 and _one_line(x.get("seed"))):
            return "j:" + str(x["id"]), _one_line(x.get("seed"), 200)
    return None


def moment(now=None):
    """A charged moment still with him: strong enough, between six hours and a week old, the strongest first."""
    now = now or time.time()
    best = None
    for mid, m in ((_load("moment-archive.json", {}) or {}).get("moments", {}) or {}).items():
        if not isinstance(m, dict) or float(m.get("intensity") or 0) < MOMENT_MIN_INTENSITY:
            continue
        at = _ts(m.get("timestamp"))
        content = _one_line(m.get("content"), 300)
        if at is None or not content:
            continue
        age_h = (now - at) / 3600.0
        if MOMENT_MIN_HOURS <= age_h <= MOMENT_MAX_HOURS and (best is None or float(m["intensity"]) > best[0]):
            best = (float(m["intensity"]), "m:" + str(mid), content)
    return (best[1], best[2]) if best else None


FEELINGS = {"yearning": yearning, "resonance": resonance, "joke": joke, "moment": moment}


def _state():
    try:
        with open(STATE) as f:
            s = json.load(f)
        if isinstance(s, dict):
            return s
    except Exception:
        pass
    return {"items": {}, "last": None}


def _key(item):
    return hashlib.sha1(str(item).encode()).hexdigest()[:16] if item else ""


def allowed(trigger, item, now=None, relaxed=False, state=None):
    now = now or time.time()
    s = state or _state()
    if item and _key(item) in (s.get("items") or {}).get(trigger, []):
        return False                                     # this item already went out on this trigger
    last = s.get("last") or {}
    if not relaxed and last.get("trigger") == trigger and now - float(last.get("at") or 0) < TYPE_COOLDOWN_S:
        return False                                     # same type twice in a row inside a day
    return True


def pick(candidates, now=None, relaxed=False):
    s = _state()
    for c in candidates:
        trigger, _, item = str(c).partition("|")
        if trigger and allowed(trigger, item, now, relaxed, s):
            return trigger, item
    return None


def record(trigger, item, now=None):
    now = now or time.time()
    s = _state()
    items = s.setdefault("items", {})
    if item:
        spent = [k for k in items.get(trigger, []) if k != _key(item)] + [_key(item)]
        items[trigger] = spent[-ITEMS_KEPT:]
    s["last"] = {"trigger": trigger, "at": now}
    os.makedirs(MEMORY, exist_ok=True)
    tmp = STATE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(s, f, indent=1)
    os.replace(tmp, STATE)


def main(argv):
    if len(argv) >= 2 and argv[0] == "feel" and argv[1] in FEELINGS:
        got = FEELINGS[argv[1]]()
        if got:
            print(got[0] + "\t" + got[1])
    elif argv and argv[0] == "pick":
        relaxed = len(argv) > 1 and argv[1] == "--relaxed"
        got = pick(argv[2:] if relaxed else argv[1:], relaxed=relaxed)
        if got:
            print(got[0] + "|" + got[1])
    elif len(argv) >= 2 and argv[0] == "record":
        record(argv[1], argv[2] if len(argv) > 2 else "")
    else:
        raise SystemExit("usage: outreach_feelings.py feel <name> | pick [--relaxed] trigger|item ... | record trigger [item]")


if __name__ == "__main__":
    main(sys.argv[1:])
