#!/usr/bin/env python3
"""Forge SK-4d56dc6c: a cached neighbor entry must not keep her phone 'seen' after it stops answering,
and a presence flip must describe the phone, never infer that she came or went.

Ping stays first; the neighbor fallback asks for REACHABLE entries only; ABSENT_AFTER stays 4. Fully isolated:
every path either module writes is repointed into a scratch HOME, subprocess.run is a stub, the emotion organ is
a stub, and the suite asserts that before it does anything else.
"""
import os, sys, json, types, tempfile, importlib.util

HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
HOME = tempfile.mkdtemp(prefix="vintos-ppr-"); os.environ["HOME"] = HOME; os.environ["SPARK_WORKSPACE"] = os.path.join(HOME, ".vintos", "workspace")
WS = os.environ["SPARK_WORKSPACE"]; MEM = os.path.join(WS, "memory"); os.makedirs(MEM, exist_ok=True)
R = []
def check(name, ok, detail=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + name + (("  ->  %s" % (detail,)) if (detail and not ok) else ""))
def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m

# the emotion organ and the sensor-reactions store are stubs/scratch before anything observes
nudges = []
eu = types.ModuleType("emoclaw_utils"); eu.nudge_emotions = lambda d, source="": nudges.append((d, source)); sys.modules["emoclaw_utils"] = eu
SR = load("sensor_reactions", os.path.join(REPO, "scripts", "sensor_reactions.py"))
SR.WS = WS; SR.MEMORY = MEM; SR.STATE = os.path.join(MEM, "sensor-reactions-state.json"); SR.LOG = os.path.join(MEM, "sensor-reactions.jsonl")
sys.modules["sensor_reactions"] = SR
HP = load("home_presence", os.path.join(REPO, "scripts", "home_presence.py"))
HP.WS = WS; HP.MEMORY = MEM; HP.CONFIG = os.path.join(MEM, "home-presence-config.json"); HP.STATE = os.path.join(MEM, "home-presence.json")

# subprocess is a stub: it records argv and answers from a script, nothing on the host is run
calls = []
answers = {"ping": 1, "neigh": ""}
class _Done:
    def __init__(self, rc, out): self.returncode = rc; self.stdout = out
def fake_run(argv, **kw):
    calls.append(list(argv))
    if argv[0] == "ping":
        return _Done(answers["ping"], "")
    return _Done(0, answers["neigh"])
HP.subprocess = types.SimpleNamespace(run=fake_run)

print("\n--- isolation: scratch stores, stubbed sender, stubbed shell ---")
check("every path either module writes lives under the scratch HOME",
      all(p.startswith(HOME) for p in (HP.MEMORY, HP.CONFIG, HP.STATE, SR.MEMORY, SR.STATE, SR.LOG)), (HP.STATE, SR.STATE))
check("home_presence's subprocess is the stub, not the real module", HP.subprocess.run is fake_run)
check("the emotion organ is a stub", sys.modules["emoclaw_utils"] is eu)

print("\n--- probe: ping first, then REACHABLE neighbors only ---")
IP, MAC = "192.168.7.42", "AA:BB:CC:DD:EE:FF"
cfg = {"phone_ip": IP, "phone_mac": MAC}
del calls[:]; answers["ping"] = 0
check("a ping answer is a hit and the neighbor table is never consulted", HP.probe(cfg) is True and calls == [["ping", "-c", "1", "-W", "2", IP]], calls)
del calls[:]; answers["ping"] = 1; answers["neigh"] = "%s dev wlan0 lladdr %s REACHABLE\n" % (IP, MAC.lower())
hit = HP.probe(cfg)
check("when ping fails the fallback asks for REACHABLE entries only, exactly", len(calls) == 2 and calls[1] == ["ip", "neigh", "show", "nud", "reachable"], calls)
check("a REACHABLE row with her IP is a hit", hit is True)
answers["neigh"] = "10.0.0.9 dev wlan0 lladdr %s REACHABLE\n" % MAC.lower()
check("a REACHABLE row with her MAC alone is a hit", HP.probe({"phone_mac": MAC}) is True)
answers["neigh"] = "192.168.7.4 dev wlan0 lladdr 11:22:33:44:55:66 REACHABLE\n192.168.7.420 dev wlan0 lladdr 11:22:33:44:55:67 REACHABLE\n"
check("other devices, including a longer IP sharing her prefix, are not a hit", HP.probe(cfg) is False)
answers["neigh"] = ""
check("an empty REACHABLE table is not seen (the stale rows it would have had do not count)", HP.probe(cfg) is False)
check("no config still probes to None", HP.probe({}) is None)

print("\n--- hysteresis is unchanged: four misses, one hit resets ---")
check("ABSENT_AFTER stays 4", HP.ABSENT_AFTER == 4)
st = HP.decide({}, True, now=1000)
for i in range(3):
    st = HP.decide(st, False, now=1001 + i)
check("three misses keep her phone seen", st["home"] and st["misses"] == 3, st)
st = HP.decide(st, False, now=1004)
check("the fourth miss clears it", st["home"] is False and st["misses"] == 4, st)
st = HP.decide(st, True, now=1005)
check("one hit restores it and resets misses", st["home"] and st["misses"] == 0 and st["home_since"] == 1005, st)

print("\n--- reactions describe the phone, not her ---")
T = 1_800_000_000.0
d = SR.observe("presence", True, at=T, now=T)
check("a first observation does not react", d["reacted"] is False)
d = SR.observe("presence", True, at=T + 60, now=T + 60)
check("an unchanged observation does not react, and the refusal names the phone", d["reacted"] is False and "phone" in d["why"], d["why"])
d = SR.observe("presence", False, at=T + 120, now=T + 120)
lost = d["reaction"]["change"] if d.get("reaction") else ""
check("losing the phone reacts and says the phone left the wifi, not that she left",
      d["reacted"] and lost.startswith("her phone") and "left the house wifi" in lost and "she just" not in lost, lost)
d = SR.observe("presence", True, at=T + 180, now=T + 180)
back = d["reaction"]["change"] if d.get("reaction") else ""
check("the phone returning says the phone joined the wifi, not that she came home",
      d["reacted"] and back.startswith("her phone") and "joined the house wifi" in back and "came home" not in back and "she just" not in back, back)
check("the feel nudge went to the stub, nowhere else", nudges and nudges[-1][1] == "sensor:presence", nudges)
check("the reactions store landed in scratch", os.path.exists(SR.STATE) and SR.STATE.startswith(HOME))
print("\n%d/%d" % (sum(R), len(R))); sys.exit(0 if all(R) else 1)
