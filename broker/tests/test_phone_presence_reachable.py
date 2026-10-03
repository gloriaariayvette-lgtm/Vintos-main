#!/usr/bin/env python3
"""Forge SK-4d56dc6c: phone presence must not trust cached neighbor entries, and reactions must describe
only the phone. Ping goes first; the fallback asks the kernel for REACHABLE neighbors only (STALE/DELAY
entries linger after a phone stops answering); four misses still clear detection; a hit resets it; and
the reaction wording names the phone joining or leaving the wifi, never where she is.
Isolated: scratch HOME and workspace, ping/ip neigh faked, the emotion organ a stub."""
import os, sys, json, time, types, tempfile, importlib.util

HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
HOME = tempfile.mkdtemp(prefix="vintos-ppr-"); os.environ["HOME"] = HOME
WS = os.path.join(HOME, ".vintos", "workspace"); MEM = os.path.join(WS, "memory"); os.makedirs(MEM, exist_ok=True)
os.environ["SPARK_WORKSPACE"] = WS
R = []
def check(name, ok, detail=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + name + (("  ->  %s" % (detail,)) if (detail and not ok) else ""))
def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m

# stubs: nothing sends, nothing feels for real, nothing touches the network
nudges = []
eu = types.ModuleType("emoclaw_utils"); eu.nudge_emotions = lambda d, source="": nudges.append((d, source)); sys.modules["emoclaw_utils"] = eu
SR = load("sensor_reactions", os.path.join(REPO, "scripts", "sensor_reactions.py"))
SR.WS = WS; SR.MEMORY = MEM; SR.STATE = os.path.join(MEM, "sensor-reactions-state.json"); SR.LOG = os.path.join(MEM, "sensor-reactions.jsonl")
sys.modules["sensor_reactions"] = SR
hp = load("home_presence", os.path.join(REPO, "scripts", "home_presence.py"))
hp.WS = WS; hp.MEMORY = MEM; hp.CONFIG = os.path.join(MEM, "home-presence-config.json"); hp.STATE = os.path.join(MEM, "home-presence.json")

calls = []; ping_ok = [False]; neigh_out = [""]
def fake_run(cmd, **kw):
    calls.append(list(cmd))
    if cmd[0] == "ping":
        return types.SimpleNamespace(returncode=0 if ping_ok[0] else 1, stdout=b"")
    return types.SimpleNamespace(returncode=0, stdout=neigh_out[0])
hp.subprocess.run = fake_run

print("\n--- isolation ---")
check("home_presence writes only under scratch", hp.STATE.startswith(HOME) and hp.CONFIG.startswith(HOME) and hp.MEMORY.startswith(HOME))
check("sensor_reactions writes only under scratch", SR.STATE.startswith(HOME) and SR.LOG.startswith(HOME) and SR.MEMORY.startswith(HOME))
check("subprocess is the fake; the emotion organ is the stub", hp.subprocess.run is fake_run and sys.modules["emoclaw_utils"] is eu)

print("\n--- probe: ping first, then REACHABLE neighbors only ---")
CFG = {"phone_ip": "192.168.1.42", "phone_mac": "aa:bb:cc:dd:ee:ff"}
ping_ok[0] = True; calls.clear()
check("ping success is a hit and skips the neighbor fallback", hp.probe(CFG) is True and len(calls) == 1 and calls[0][0] == "ping", calls)
ping_ok[0] = False; neigh_out[0] = ""; calls.clear()
hit = hp.probe(CFG)
neigh = [c for c in calls if c[0] == "ip"]
check("ping failure falls back to exactly `ip neigh show nud reachable`", neigh == [["ip", "neigh", "show", "nud", "reachable"]], calls)
check("empty neighbor output is not a hit", hit is False)
neigh_out[0] = "192.168.1.42 dev wlan0 lladdr aa:bb:cc:dd:ee:ff REACHABLE\n"
check("an IP match in reachable output is a hit", hp.probe({"phone_ip": "192.168.1.42"}) is True)
check("a MAC match in reachable output is a hit", hp.probe({"phone_mac": "AA:BB:CC:DD:EE:FF"}) is True)
neigh_out[0] = "192.168.1.7 dev wlan0 lladdr 11:22:33:44:55:66 REACHABLE\n"
check("unmatched reachable output is not a hit", hp.probe(CFG) is False)
check("ping-first and ABSENT_AFTER=4 are retained", hp.ABSENT_AFTER == 4 and "_ping(ip)" in open(os.path.join(REPO, "scripts", "home_presence.py")).read())

print("\n--- the loop: three misses keep detection, the fourth clears, a hit resets; wording names the phone ---")
json.dump(CFG, open(hp.CONFIG, "w"))
now = time.time()
json.dump({"home": True, "misses": 0, "home_since": now - 60, "checked": now}, open(hp.STATE, "w"))
ping_ok[0] = False; neigh_out[0] = ""
for _ in range(3):
    hp.main()
st = json.load(open(hp.STATE))
check("three misses retain detection", st["home"] is True and st["misses"] == 3, st)
check("first/unchanged observations do not react", SR.pending() == [])
hp.main()
st = json.load(open(hp.STATE))
check("the fourth miss clears detection", st["home"] is False and st["misses"] == 4, st)
live = SR.pending()
check("loss is one reaction about the phone, not about her leaving",
      len(live) == 1 and "phone" in live[0]["change"] and "left" in live[0]["change"]
      and "she just" not in live[0]["change"] and "came home" not in live[0]["change"], live)
ping_ok[0] = True
hp.main()
st = json.load(open(hp.STATE))
check("a hit resets detection and misses", st["home"] is True and st["misses"] == 0, st)
live = SR.pending()
back = [r for r in live if "joined" in r["change"]]
check("return is one reaction about the phone joining, not about her coming home",
      len(back) == 1 and "phone" in back[0]["change"] and "she just" not in back[0]["change"] and "came home" not in back[0]["change"], live)
check("the feel nudge went to the stub, not the organ", nudges and nudges[-1][1] == "sensor:presence", nudges)
check("nothing left scratch", all(p.startswith(HOME) for p in (hp.STATE, SR.STATE, SR.LOG)) and os.path.exists(SR.LOG))
print("\n%d/%d" % (sum(R), len(R))); sys.exit(0 if all(R) else 1)
