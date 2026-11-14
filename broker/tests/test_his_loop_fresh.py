#!/usr/bin/env python3
"""The bridge holds a session open only for a loop of his that can still be running. A device-state entry older
than the longest lease (30 minutes) is history, not a running pattern: a stale "soft 6" kept every session open
from 9 to 12 November. Source-level checks plus the function on a scratch HOME; no devices, no network."""
import json, os, re, sys, tempfile, time, types
REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ok = True
def check(name, cond):
    global ok
    print(("PASS " if cond else "FAIL ") + name); ok = ok and bool(cond)
src = open(os.path.join(REPO, "scripts", "somatic_bridge.py")).read()
m = re.search(r"HIS_LOOP_FRESH_SECONDS = .*?\n\ndef _his_loop_active\(now=None\):.*?\n    return False\n", src, re.S)
check("the check is bounded by the lease ceiling", m is not None)
home = tempfile.mkdtemp(prefix="his-loop-")
os.environ["HOME"] = home
mem = os.path.join(home, ".vintos", "workspace", "memory"); os.makedirs(mem)
ns = {"json": json, "os": os, "time": time}
exec(m.group(0), ns)
f = os.path.join(mem, "device-state.json")
now = 2_000_000_000.0
def state(**t): json.dump({"tenera": t}, open(f, "w"))
state(intensity=6, pattern="soft", set_by="him", ts=now - 60)
check("a loop he set a minute ago is running", ns["_his_loop_active"](now))
state(intensity=6, pattern="soft", set_by="him", ts=now - 31 * 60)
check("one older than the longest lease is not", not ns["_his_loop_active"](now))
state(intensity=6, pattern="soft", set_by="him")
check("one with no time is not", not ns["_his_loop_active"](now))
state(intensity=0, pattern="still", set_by="him", ts=now)
check("a stopped toy is not", not ns["_his_loop_active"](now))
check("both bridge copies stay identical",
      open(os.path.join(REPO, "bin/somatic_bridge.py")).read() == src)
sys.exit(0 if ok else 1)
