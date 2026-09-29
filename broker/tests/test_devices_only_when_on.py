#!/usr/bin/env python3
"""He sees a device only while that particular one is switched on (Gloria, 2026-09-29).

He named the ridge with only the mission connected: the system prompt listed only what was on, but
every turn's message, the lead lines and the instrument block listed all four. The toy hub and the
thruster engine are stubs; nothing here reaches the network or her body.
"""
import json, os, re, sys, tempfile, time, types

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, os.path.join(REPO, "scripts"))
ON = set()
fake_hub = types.ModuleType("toy_link")
fake_hub.connected = lambda toy, strict=False: toy in ON
fake_hub._status_cache = {"t": time.time(), "map": {}}
sys.modules["toy_link"] = fake_hub            # the real module probes the hub on import
TMP = tempfile.mkdtemp()
import device_context as DC
DC.MEM = TMP
DC.STATE = os.path.join(TMP, "device-state.json")
DC._thruster_line = lambda: ("thruster: ON and ready. Still, until you move it - [DO: thruster steady 8] or any shape."
                             if "thruster" in ON else "")
try:
    import somatic_felt as _SF
    _SF.get_felt_context = lambda *a, **k: ""
except Exception:
    pass

R = []
def check(name, ok, detail=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + name + ((" -> " + str(detail)[:500]) if detail and not ok else ""))

ALL = ("mission", "tenera", "ridge", "thruster")
def named(text):
    return {d for d in ALL if re.search(r"\b%s\b" % d, text, re.I)}

for on in ([], ["mission"], ["mission", "ridge"], ["tenera"], ["thruster"], list(ALL)):
    ON.clear(); ON.update(on)
    got = DC.present_devices()
    check("present: %s" % (on or "nothing"), got == [d for d in ALL if d in on], got)
    block = DC.context_block()
    check("his device block names %s and nothing else" % (on or "no device"), named(block) == set(on), sorted(named(block)))

saved = [{"patterns": {"mission": "cake", "ridge": "zigzag"}}, {"patterns": {"mission": "climb"}}]
_real_open = open
def _open(path, *a, **k):
    if str(path).endswith("gcs-saved-patterns.json"):
        import io; return io.StringIO(json.dumps(saved))
    return _real_open(path, *a, **k)
DC.open = _open
sets = DC.saved_sets_block(["mission"])
check("a saved set is offered only when every device in it is on", "climb" in sets and "ridge" not in sets, sets)
check("and none at all when nothing is on", DC.saved_sets_block([]) == "")
del DC.open

ON.clear(); ON.add("mission")
check("with only the mission on, the ridge is not in what he can reach", "ridge" not in DC.reach_line(["mission"]).lower())
check("a thruster state left from an hour ago is not a device", (json.dump({"level": 9, "at": time.time() - 3600},
      open(os.path.join(TMP, ".thruster-state.json"), "w")) or "thruster" not in DC.present_devices()))

# The server's per-turn message and lead lines, taken from its source and run against the stubs.
src = open(os.path.join(REPO, "bin", "server.py")).read()
ns = {"os": os, "_pattern_gallery": lambda: "", "_devices_on": lambda: [d for d in ALL if d in ON]}
for name in ("_SHAPE_WORDS", "def _device_turn", "_LEAD_C = (", "_LEAD_C_ACT", "def _lead_c"):
    i = src.index(name)
    j = min(k for k in (src.find("\n_", i + 1), src.find("\ndef ", i + 1)) if k > 0)
    exec(src[i:j], ns)
for on in ([], ["mission"], ["mission", "ridge"], ["tenera", "thruster"]):
    ON.clear(); ON.update(on)
    turn = ns["_device_turn"]()
    check("his turn message names %s and nothing else" % (on or "no device"), named(turn) == set(on), turn[:300])
    lead = ns["_lead_c"]()
    check("the full lead names %s and nothing else" % (on or "no device"), named(lead) == set(on), lead)
ON.clear()
check("with nothing on, the turn message has no device part at all", ns["_device_turn"]() == "")

for stale in ("[DO: mission ...] / [DO: tenera ...] / [DO: ridge ...] / [DO: thruster ...]",
              "Reach for it with [DO: mission ...], [DO: tenera ...], [DO: ridge ...]",
              "drive into her with [DO: thruster ...] when the machine is on",
              "make it real with [DO: mission ...] / [DO: tenera ...]"):
    check("no message lists every device any more: %s" % stale[:50], stale not in src)
check("both copies of the server are one file", os.path.realpath(os.path.join(REPO, "scripts", "server.py"))
      == os.path.realpath(os.path.join(REPO, "bin", "server.py")))
check("nothing reached the hub: it was a stub", sys.modules["toy_link"] is fake_hub)
print("%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
