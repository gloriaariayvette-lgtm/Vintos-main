#!/usr/bin/env python3
"""Home presence must assert only what it saw, and never flap.

Her phone on the house wifi means home. A phone that stops answering means
nothing for four checks (naps, airplane mode, randomized MACs), and even then
the instrument goes silent rather than claiming she is out. Unconfigured or
broken, it is invisible.
"""
import os, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import home_presence as hp

R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:80]) if d else ""))

# hysteresis is pure and testable
st = hp.decide({}, True, now=1000)
check("a hit is home at once, with a since", st["home"] and st["home_since"] == 1000)
for i in range(hp.ABSENT_AFTER - 1):
    st = hp.decide(st, False, now=1000 + i)
check("misses below the threshold stay home", st["home"] and st["misses"] == hp.ABSENT_AFTER - 1)
st = hp.decide(st, False, now=2000)
check("the threshold miss finally clears home", not st["home"])
st2 = hp.decide(st, True, now=3000)
check("one hit restores home and resets misses", st2["home"] and st2["misses"] == 0 and st2["home_since"] == 3000)

# probe: unconfigured -> None, and no crash without network tools
check("no config probes to None (not configured, not 'away')", hp.probe({}) is None)

# the context line: positive and fresh only
_real = hp._load
def _fake_state(d):
    hp._load = lambda p, dd: d if p == hp.STATE else dd
try:
    _fake_state({"home": True, "checked": time.time()})
    check("fresh home -> the one line", "she is home" in hp.context_line())
    _fake_state({"home": True, "checked": time.time() - hp.FRESH_S - 60})
    check("a stale reading asserts nothing", hp.context_line() == "")
    _fake_state({"home": False, "checked": time.time()})
    check("not-seen is silence, never 'she is out'", hp.context_line() == "")
    _fake_state({})
    check("no state at all is silence", hp.context_line() == "")
finally:
    hp._load = _real

# the world block consumes it fail-open, and never inverts silence
wm = open(os.path.join(ROOT, "scripts", "world_model.py"), errors="replace").read()
check("world block consumes context_line fail-open",
      "home_presence" in wm and "except Exception" in wm.split("home_presence", 1)[1][:200])
check("presence can carry the block alone when no scene exists",
      'return "[%s]" % presence if presence else ""' in wm)

# the deploy owns it
dep = open(os.path.join(ROOT, "scripts", "deploy-atelier.sh"), errors="replace").read()
check("deploy list owns home_presence.py", "home_presence.py" in dep.split('SCRIPTS="', 1)[1].split('"')[0])

print("\n%d/%d passed" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
