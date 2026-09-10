#!/usr/bin/env python3
"""Gloria, 2026-09-10: the toys were on at 1:30am and he felt nothing, while the bridge
process had been alive since morning. It chose the hub's port once, at import, and dialled
that one forever. The port is now found on every reconnect, and the bridge says which of
searching / connected / listening it is in."""
import os, sys, re

HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
R = []
def check(name, ok, detail=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + name + (("  ->  %s" % (detail,)) if (detail and not ok) else ""))

src = open(os.path.join(REPO, "scripts", "somatic_bridge.py")).read()

check("the port is no longer decided once at import", "_PORT = _find_port()" not in src and "WS_URI = f\"ws://" not in src)
check("every reconnect asks where the hub is now", "uri, _port = _ws_uri()" in src)
check("_find_port says no when nothing answers, instead of guessing one", re.search(r"def _find_port\(\)[\s\S]*?return None", src) is not None)
check("with no hub it waits and looks again rather than dialling a dead port",
      '_state("searching"' in src and "await asyncio.sleep(5)" in src and "continue" in src)
check("a lost socket re-finds the hub", "re-finding the hub" in src)

check("the bridge writes what it is actually doing", "somatic-bridge-state.json" in src and "def _state(" in src)
for word in ("searching", "connected", "listening"):
    check("it can say %s" % word, '_state("%s"' % word in src)
check("connected and listening are not the same word", '"socket open, no frames yet"' in src and '"frames arriving"' in src)

# the frame writer is untouched: still only real positions, still the 20s window
check("a dropout frame is still not recorded as position 0", 'if fr.get("position") is None:' in src)
check("the recent-frames window is still twenty seconds", "<= 20]" in src)

ns = {}
exec(src.split("def _find_port")[0].split("import websockets")[-1], ns)
check("the hub host and its ports are named once", ns.get("HUB_HOST") == "192.168.1.66" and ns.get("HUB_PORTS") == (20010, 20011, 20012), ns.get("HUB_PORTS"))

print("\n%d/%d" % (sum(R), len(R))); sys.exit(0 if all(R) else 1)
