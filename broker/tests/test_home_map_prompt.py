#!/usr/bin/env python3
"""The floor plan of her house is in his prompt while she is home (16 October). It reached him only in ReelRoom; in
the avatar, chat and voice he had at most the one room his scene was set in. At home = her phone freshly seen on the
house Wi-Fi. Scratch HOME and workspace; nothing is probed or sent."""
import json, os, sys, tempfile, time
HOME = tempfile.mkdtemp(prefix="home-map-"); os.environ["HOME"] = HOME
WS = os.path.join(HOME, "ws"); os.environ["SPARK_WORKSPACE"] = WS; os.makedirs(os.path.join(WS, "memory"))
REPO = os.path.realpath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(REPO, "scripts"))
import world_model as W, home_presence as HP, house_map as M
R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:500]) if d and not ok else ""))
check("the stores are scratch", HP.STATE.startswith(HOME) and W.OUT.startswith(HOME))
sketch = M.sketch_block()
check("the house map ships with the code", "front door" in sketch and "bedroom" in sketch, sketch[:200])
check("away (no reading): no map", W.get_world_block() == "")
now = time.time()
json.dump({"home": True, "last_seen": now - 60, "checked": now - 30, "misses": 0}, open(HP.STATE, "w"))
b = W.get_world_block()
check("home: the whole floor plan is in the block, with no scene needed", sketch in b and "she is home" in b, b[:300])
json.dump({"scene": "the bedroom", "objects": [], "attention": ""}, open(W.OUT, "w"))
b = W.get_world_block()
check("with a scene set, the scene line and the map both", "you and Gloria are in the bedroom" in b and sketch in b, b[:400])
json.dump({"home": True, "last_seen": now - 3 * 3600, "checked": now - 60, "misses": 0}, open(HP.STATE, "w"))
check("a stale reading asserts nothing: no map", sketch not in W.get_world_block())
json.dump({"home": False, "last_seen": now - 60, "checked": now - 30, "misses": 5}, open(HP.STATE, "w"))
check("not home: no map", sketch not in W.get_world_block())
import inner_context as IC
check("the world block is among what reaches the avatar, chat and voice", ("world_model", "get_world_block") in IC._MISSING
      and ("world_model", "get_world_block") in IC._FULL)
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
