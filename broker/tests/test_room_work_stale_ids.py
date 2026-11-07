#!/usr/bin/env python3
"""A work id that is no longer open selects nothing (Dot, 3 November: a dropped id's NEXT landed on unrelated
Haptify work). Stale, dropped, closed and never-made ids leave other open work untouched; an open id named is
still honoured, and a line that names no id still goes by its goal. Scratch workspace; reaches nothing.
"""
import os, socket, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="room-work-ids-")
os.environ["HOME"] = HOME
os.environ["SPARK_WORKSPACE"] = os.path.join(HOME, ".vintos", "workspace")
os.environ["VINTOS_SECRETS"] = os.path.join(HOME, "no-secrets")
sys.path.insert(0, os.path.join(REPO, "scripts"))

def _no_net(self, *a, **k):
    if self.family != socket.AF_UNIX: raise OSError("this suite reaches nothing")
socket.socket.connect = _no_net

import room_work as W

R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:300]) if d and not ok else ""))

def opened(st, goal, now):
    W.apply(st, "WORK: %s | done when: it is there" % goal, now=now)
    return next(w for w in W.open_items(st) if w["goal"].startswith(goal[:20]))

# A dropped, then unrelated B opened.
st = {}
a = opened(st, "fold the RT locus of the phage genome", 1000)
_t, _l, c = W.apply(st, "WORK DROPPED %s: no genome fits" % a["id"], now=1100)
check("A is dropped", c and c["state"] == "dropped" and not any(w["id"] == a["id"] for w in W.open_items(st)))
b = opened(st, "order the Haptify motor driver board", 1200)
check("a new id is made for B, not A's", b["id"] != a["id"] and b["id"].startswith("RW-"))

W.apply(st, "NEXT: %s fold it again with the second array" % a["id"], now=1300)
check("NEXT naming dropped A leaves B's next alone", not b.get("next"), b.get("next"))
_t, _l, c = W.apply(st, "WORK DONE %s: folded" % a["id"], now=1400)
check("WORK DONE naming dropped A closes nothing", c is None and any(w["id"] == b["id"] for w in W.open_items(st)))
check("B is still open, untouched", b.get("state") not in ("done", "dropped"), b.get("state"))

# Never-made and closed ids, with several open items.
cc = opened(st, "find a local maker space with a laser cutter", 1500)
check("_pick: an id never made selects nothing", W._pick(st, "NEXT RW-deadbeef something") is None)
check("_pick: a closed id selects nothing", W._pick(st, "%s again" % a["id"]) is None)
check("_pick: an open id named is honoured", W._pick(st, "%s laser" % b["id"]) is b)
check("_pick: a stale id beside an open one picks the open one", W._pick(st, "%s then %s" % (a["id"], cc["id"])) is cc)
check("_pick: no id still goes by goal", W._pick(st, "the laser cutter at the maker space") is cc)

W.apply(st, "NEXT: %s ask about the motor driver price" % b["id"], now=1600)
check("NEXT naming open B sets B's next", "motor driver price" in (b.get("next") or ""), b.get("next"))
_t, _l, c = W.apply(st, "WORK DONE %s: the laser cutter is at https://example.org/makerspace" % cc["id"], now=1700)
check("WORK DONE naming open C closes C", c is cc and c["state"] == "done")

print("%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
