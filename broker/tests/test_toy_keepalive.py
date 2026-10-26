#!/usr/bin/env python3
"""The keepalive behaves as the hand-placed copy did, now that the deploy installs it.

His steady holds are re-sent at their level for up to two hours after his last command; the hardware
stop wins; her holds, patterns and stills are left alone; nothing is ever stopped by the keepalive.
The device send is a stub: nothing reaches a toy.
"""
import os, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOTD = os.path.dirname(os.path.dirname(HERE))
TMP = tempfile.mkdtemp(prefix="keepalive-")
os.environ["HOME"] = TMP
sys.path.insert(0, os.path.join(ROOTD, "scripts"))
import toy_keepalive as K

R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:110]) if d else ""))

check("the keepalive's stores are the suite's scratch", K.STATE.startswith(TMP) and K.BUTTON.startswith(TMP))
check("the window is two hours, as before", K.STALE == 2 * 3600)

sent = []
def send(toy, lvl): sent.append((toy, lvl))
now = 100000.0
hold = lambda age, **kw: dict({"set_by": "him", "pattern": "steady", "intensity": 8, "ts": now - age}, **kw)

K.tick(now, {"tenera": hold(60)}, {}, send)
check("a fresh hold of his is re-asserted at its level", sent == [("tenera", 8)], sent)
sent.clear(); K.tick(now, {"tenera": hold(90 * 60)}, {}, send)
check("a 90-minute hold is still re-asserted", sent == [("tenera", 8)], sent)
sent.clear(); K.tick(now, {"tenera": hold(2 * 3600 + 1)}, {}, send)
check("past two hours it is left as it is: nothing sent, nothing stopped", sent == [], sent)
sent.clear(); K.tick(now, {"tenera": hold(60)}, {"stopped": True}, send)
check("the hardware stop button wins: nothing is sent", sent == [])
sent.clear(); K.tick(now, {"a": hold(60, set_by="her"), "b": hold(60, pattern="wave"), "c": hold(60, intensity=0)}, {}, send)
check("her holds, patterns and stills are left alone", sent == [], sent)

unit = open(os.path.join(ROOTD, "broker", "vintos-toy-keepalive.service")).read()
# The deploy updates the copy where it already lives, ~/toy_keepalive.py (25 October: pointing the unit at
# workspace/scripts, where no copy was, left the keepalive down until the unit was put back).
check("the unit runs the copy the deploy updates", "%h/toy_keepalive.py" in unit)
dep = open(os.path.join(ROOTD, "scripts", "deploy-atelier.sh")).read()
check("the deploy installs it", "toy_keepalive.py" in dep and "vintos-toy-keepalive" in dep)

print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
