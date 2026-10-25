#!/usr/bin/env python3
"""The keepalive re-asserts his steady holds only within the gate's lease ceiling, and ends one past it.

The device holds a level until it is told otherwise, so a keepalive that merely stops re-sending leaves
the hold on. Past the ceiling it sends one stop. The hardware stop button wins over everything.
The device send is a stub: nothing reaches a toy.
"""
import os, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOTD = os.path.dirname(os.path.dirname(HERE))
TMP = tempfile.mkdtemp(prefix="keepalive-")
os.environ["HOME"] = TMP
sys.path.insert(0, os.path.join(ROOTD, "scripts"))
import toy_keepalive as K
import effect_gate

R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:110]) if d else ""))

check("the keepalive's stores are the suite's scratch", K.STATE.startswith(TMP) and K.BUTTON.startswith(TMP))
check("the ceiling is the gate's own lease ceiling", K.ceiling() == effect_gate.MAX_LEASE_SECONDS == 1800, K.ceiling())

sent = []
def send(toy, lvl): sent.append((toy, lvl))
now = 100000.0
hold = lambda age, **kw: dict({"set_by": "him", "pattern": "steady", "intensity": 8, "ts": now - age}, **kw)
ended = set()

K.tick(now, {"tenera": hold(60)}, {}, send, ended, 1800)
check("a fresh hold of his is re-asserted at its level", sent == [("tenera", 8)], sent)

sent.clear(); K.tick(now, {"tenera": hold(1801)}, {}, send, ended, 1800)
check("a hold past the ceiling is ended with one stop, not re-sent", sent == [("tenera", 0)], sent)
sent.clear(); K.tick(now + 15, {"tenera": hold(1801)}, {}, send, ended, 1800)   # the same hold, 15 s later
check("... once: the next pass sends nothing", sent == [], sent)

sent.clear(); K.tick(now, {"tenera": hold(7000)}, {}, send, set(), 1800)
check("the old two-hour window is gone: a 2-hour-old hold is stopped", sent == [("tenera", 0)], sent)

sent.clear(); K.tick(now, {"tenera": hold(60)}, {"stopped": True}, send, set(), 1800)
check("the hardware stop button wins: nothing is sent", sent == [])

sent.clear(); K.tick(now, {"a": hold(60, set_by="her"), "b": hold(60, pattern="wave"), "c": hold(60, intensity=0)}, {}, send, set(), 1800)
check("her holds, patterns and stills are left alone", sent == [], sent)

unit = open(os.path.join(ROOTD, "broker", "vintos-toy-keepalive.service")).read()
check("the unit runs the deployed copy", "%h/.vintos/workspace/scripts/toy_keepalive.py" in unit)
dep = open(os.path.join(ROOTD, "scripts", "deploy-atelier.sh")).read()
check("the deploy installs it", "toy_keepalive.py" in dep and "vintos-toy-keepalive" in dep)

sb = open(os.path.join(ROOTD, "scripts", "somatic_bridge.py")).read()
check("the somatic replay is refused when the gate cannot answer", '_rs_allow, _rs_why = False, "effect gate unavailable"' in sb
      and "_rs_allow, _rs_why = True, None" not in sb)

print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
