#!/usr/bin/env python3
"""His wants board, kept to what he is actually working on (Chat's inspection on Aegis, 2026-10-05: 57 active
wants, every one "protected", the oldest 26 days, the queue "moving, but mostly sideways").

Run at the start of every wants-router pass. Each pass:

  1. closed rows leave the board: anything fulfilled or dismissed still sitting in current-wants.json goes to its
     archive (fulfilled-wants.json, dismissed-wants.json), once;
  2. a want routed to Gloria that has waited AWAIT_DAYS without her answer is parked AWAITING_GLORIA: never
     rejected (silence is not a no), off the working board, and woken the moment she writes in its discussion;
  3. a want blocked on a hand he does not have is parked BLOCKED until the block clears (the Forge clears it);
  4. near-duplicates on the working board are folded into the oldest, which keeps their history;
  5. working wants that have not moved in IDLE_DAYS age out, AGE_PER_PASS at a time, through his own aging
     (scar or let go: emoclaw_utils.age_one), archived with the reason.

"Moved" means a step completed, not a step tried: a want that fails every pass is not alive for it.

    python3 want_board.py           one pass, and what it did
"""
from __future__ import annotations
import json
import os
import re
import sys
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

WS = os.environ.get("SPARK_WORKSPACE") or os.path.expanduser("~/.vintos/workspace")
MEM = os.path.join(WS, "memory")
CURRENT = os.path.join(MEM, "current-wants.json")
FULFILLED = os.path.join(MEM, "fulfilled-wants.json")
DISMISSED = os.path.join(MEM, "dismissed-wants.json")
DISCUSSIONS = os.path.join(MEM, "want-discussions.json")

AWAIT_DAYS = 7          # a want routed to Gloria parks after this long without her answer
IDLE_DAYS = 7           # a working want that has not moved in this long ages out
AGE_PER_PASS = 5        # at most this many age in one pass (each may ask his local model whether it left a scar)
PROTECT_HOURS = 48      # a want that completed a step this recently is never capped or aged
SAME = 0.6              # share of the shorter want's content words found in the longer, to fold them
SAME_MIN = 4            # and at least this many shared content words

_STOP = frozenset("""the a an of to for and or in on at is are was be been can could would will you your i me my it its
that this with from into about what when how why want wants wanted more less than just some something really""".split())


def _now():
    return datetime.now()


def _load(path, default):
    try:
        with open(path) as f:
            d = json.load(f)
        return d if isinstance(d, type(default)) else default
    except (OSError, ValueError):
        return default


def _save(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, path)


def _t(value):
    try:
        return datetime.fromisoformat(str(value)[:26]).timestamp()
    except (TypeError, ValueError):
        return 0.0


def born(w):
    """When this want's line began: an echo carries its parent's start, so reframing never makes it young."""
    return _t(w.get("born") or w.get("timestamp"))


def last_moved(w):
    """The last time this want actually moved: begun, a step completed, or woken from parking."""
    ts = [born(w), _t(w.get("unparked_at"))]
    ts += [_t(h.get("completed_at")) for h in (w.get("step_history") or []) if isinstance(h, dict)]
    return max(ts)


def moving(w, now):
    """Completed a step in the last PROTECT_HOURS: it is being worked, so it is never capped or aged."""
    done = [_t(h.get("completed_at")) for h in (w.get("step_history") or []) if isinstance(h, dict)]
    return bool(done) and now - max(done) < PROTECT_HOURS * 3600


def working(w):
    """On the working board: open, and not parked."""
    return not w.get("fulfilled") and not w.get("dismissed") and not w.get("board")


def _words(text):
    return {x for x in re.findall(r"[a-z0-9]+", str(text).lower()) if len(x) > 3 and x not in _STOP}


def alike(a, b):
    """True when two wants say the same thing in other words."""
    wa, wb = _words(a), _words(b)
    shared = wa & wb
    return bool(wa and wb) and len(shared) >= SAME_MIN and len(shared) / min(len(wa), len(wb)) >= SAME


def _blocked(w):
    block = w.get("plan_block") or {}
    return isinstance(block, dict) and bool(block.get("block_type"))


def _gloria_answered(want_id, discussions):
    msgs = discussions.get(want_id) or []
    return bool(msgs) and isinstance(msgs[-1], dict) and msgs[-1].get("role") == "gloria"


def _archive(path, rows):
    if not rows:
        return
    have = _load(path, [])
    seen = {r.get("id") for r in have if isinstance(r, dict)}
    have += [r for r in rows if r.get("id") not in seen]
    _save(path, have)


def _write_current(mutate):
    """current-wants.json through its store lock when there is one (the router and express_want write it too)."""
    try:
        from store_guard import locked_update
        locked_update(CURRENT, mutate, default=[], reader="want_board")
        return
    except ImportError:
        pass
    rows = _load(CURRENT, [])
    out = mutate(rows)
    if out is not None:
        _save(CURRENT, out)


def tend(now=None, age=None, discussions=None):
    """One pass over the board. Returns what it did, as lines for the router's log."""
    now = (now or _now()).timestamp() if isinstance(now, datetime) or now is None else float(now)
    stamp = datetime.fromtimestamp(now).isoformat(timespec="seconds")
    disc = discussions if discussions is not None else _load(DISCUSSIONS, {})
    log, closed_f, closed_d, aging = [], [], [], []

    def mutate(rows):
        keep = []
        for w in rows if isinstance(rows, list) else []:
            if not isinstance(w, dict):
                continue
            if w.get("fulfilled"):
                closed_f.append(w); continue
            if w.get("dismissed"):
                closed_d.append(w); continue
            board = w.get("board")
            if board == "awaiting_gloria" and _gloria_answered(w.get("id", ""), disc):
                w.pop("board", None); w.pop("parked_at", None); w["unparked_at"] = stamp
                log.append("woken: Gloria answered %s" % w.get("id"))
            elif board == "blocked" and not _blocked(w):
                w.pop("board", None); w.pop("parked_at", None); w["unparked_at"] = stamp
                log.append("unblocked: %s" % w.get("id"))
            elif not board and _blocked(w) and not moving(w, now):
                w["board"], w["parked_at"] = "blocked", stamp
                log.append("parked BLOCKED (%s): %s" % ((w.get("plan_block") or {}).get("block_type"), w.get("id")))
            elif (not board and w.get("gloria_routed") and not _gloria_answered(w.get("id", ""), disc)
                  and now - last_moved(w) > AWAIT_DAYS * 86400):
                w["board"], w["parked_at"] = "awaiting_gloria", stamp
                log.append("parked AWAITING_GLORIA: %s" % w.get("id"))
            keep.append(w)
        # near-duplicates on the working board fold into the oldest, which keeps their history
        live = sorted([w for w in keep if working(w)], key=born)
        gone = set()
        for i, older in enumerate(live):
            if older.get("id") in gone:
                continue
            for newer in live[i + 1:]:
                if newer.get("id") in gone or moving(newer, now) or not alike(older.get("want"), newer.get("want")):
                    continue
                older.setdefault("merged", []).append({"id": newer.get("id"), "want": str(newer.get("want", ""))[:300],
                                                       "timestamp": newer.get("timestamp"), "at": stamp})
                older["recurrence"] = int(older.get("recurrence") or 1) + 1
                gone.add(newer.get("id"))
                closed_d.append(dict(newer, dismissed=True, dismissed_at=stamp, dismissed_by="consolidated",
                                     dismissed_reason="the same want as %s, folded into it" % older.get("id")))
                log.append("folded %s into %s" % (newer.get("id"), older.get("id")))
        keep = [w for w in keep if w.get("id") not in gone]
        # working wants that have not moved in IDLE_DAYS age out, oldest first, a few a pass
        idle = sorted([w for w in keep if working(w) and not moving(w, now)
                       and now - last_moved(w) > IDLE_DAYS * 86400], key=last_moved)[:AGE_PER_PASS]
        aging.extend(idle)
        ids = {w.get("id") for w in idle}
        return [w for w in keep if w.get("id") not in ids]

    _write_current(mutate)
    _archive(FULFILLED, closed_f)
    _archive(DISMISSED, closed_d)
    if closed_f or closed_d:
        log.append("archived %d fulfilled and %d dismissed that were still on the board" % (
            len([w for w in closed_f]), len([w for w in closed_d if w.get("dismissed_by") != "consolidated"])))
    if aging:
        if age is None:
            try:
                from emoclaw_utils import age_one as age
            except Exception:
                age = None
        rows = []
        for w in aging:
            row = None
            try:
                row = age(w) if age else None
            except Exception as exc:
                log.append("aging %s could not ask: %s" % (w.get("id"), str(exc)[:80]))
            rows.append(row or dict(w, fulfilled=True, fulfilled_at=stamp, fulfilled_by="age_wants-idle",
                                    fulfillment_note="Aged out: did not move in %d days" % IDLE_DAYS))
            log.append("aged out after %d idle days: %s" % (int((now - last_moved(w)) // 86400), str(w.get("want", ""))[:60]))
        _archive(FULFILLED, rows)
    return log


def grounded(want, quote, corpus):
    """Why a reconciliation verdict does not stand, or "". The quote must be in the record verbatim, and about this
    want: sharing at least two of its content words. A want to ask Gloria to stop calculating motion-freezing
    parameters was marked fulfilled by "The air in this room is sixty-eight degrees." (Chat's inspection, 2026-10-05)."""
    q = " ".join(str(quote or "").split())
    if len(q) < 12:
        return "no quote"
    if q.lower() not in " ".join(str(corpus or "").split()).lower():
        return "the quote is not in the record"
    shared = _words(want) & _words(q)
    if len(shared) < 2:
        return "the quote is not about this want (shares %s)" % (", ".join(sorted(shared)) or "nothing")
    return ""


def sections(rows=None):
    """The board as the app shows it: working, awaiting Gloria, blocked."""
    rows = rows if rows is not None else _load(CURRENT, [])
    open_ = [w for w in rows if isinstance(w, dict) and not w.get("fulfilled") and not w.get("dismissed")]
    return {"working": [w for w in open_ if not w.get("board")],
            "awaiting_gloria": [w for w in open_ if w.get("board") == "awaiting_gloria"],
            "blocked": [w for w in open_ if w.get("board") == "blocked"]}


if __name__ == "__main__":
    for line in tend() or ["nothing to do"]:
        print(line)
    s = sections()
    print("working %d, awaiting Gloria %d, blocked %d" % (len(s["working"]), len(s["awaiting_gloria"]), len(s["blocked"])))
