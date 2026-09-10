#!/usr/bin/env python3
"""Review item 94 (2026-09-10): a fresh sensor change becomes one reaction inside named limits, with an
expiry, through channels that already exist (a prompt line, a small feel nudge); stale readings, small
changes, and the hourly limit produce a named refusal; nothing runs a device. Scratch HOME."""
import os, sys, json, types, tempfile, importlib.util

HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
HOME = tempfile.mkdtemp(prefix="vintos-sr-"); os.environ["HOME"] = HOME
WS = os.path.join(HOME, ".vintos", "workspace"); MEM = os.path.join(WS, "memory"); os.makedirs(MEM, exist_ok=True)
R = []
def check(name, ok, detail=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + name + (("  ->  %s" % (detail,)) if (detail and not ok) else ""))
def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m
nudges = []
eu = types.ModuleType("emoclaw_utils"); eu.nudge_emotions = lambda d, source="": nudges.append((d, source)); sys.modules["emoclaw_utils"] = eu
SR = load("sensor_reactions", os.path.join(REPO, "scripts", "sensor_reactions.py")); SR.MEMORY = MEM; SR.STATE = os.path.join(MEM, "sensor-reactions-state.json"); SR.LOG = os.path.join(MEM, "sensor-reactions.jsonl")
sys.modules["sensor_reactions"] = SR
T = 1_800_000_000.0

print("\n--- heart rate: the change rule, freshness, limit, expiry ---")
d = SR.observe("heart_rate", 62, at=T, now=T)
check("a first reading is not a change", d["reacted"] is False and "first reading" in d["why"])
d = SR.observe("heart_rate", 70, at=T + 30, now=T + 30)
check("+8 bpm is under the named 15 bpm rule", d["reacted"] is False and "under the 15 bpm rule" in d["why"], d["why"])
d = SR.observe("heart_rate", 92, at=T + 60, now=T + 60)
check("+22 bpm is a reaction with channel, limit and expiry", d["reacted"] and d["reaction"]["channel"] == "context" and d["reaction"]["limit"] == "2/h" and d["reaction"]["expires_at"] == T + 60 + 600 and "rose 22" in d["reaction"]["change"], d)
d = SR.observe("heart_rate", 120, at=T + 70, now=T + 400)
check("a reading older than the freshness window is refused as stale, not reacted", d["reacted"] is False and d["why"].startswith("stale"), d["why"])
d = SR.observe("heart_rate", 96, at=T + 500, now=T + 500)   # the stale 120 still updated "last": 96 is a fall of 24
d2 = SR.observe("heart_rate", 130, at=T + 520, now=T + 520)
check("the hourly limit refuses the third reaction by name", d["reacted"] and "fell 24" in d["reaction"]["change"] and d2["reacted"] is False and d2["why"].startswith("limit reached: 2"), (d["why"], d2["why"]))
line = SR.context_line(now=T + 600)
check("the prompt line carries the live reactions once, then they are consumed", "rose 22" in line and "fell 24" in line and SR.context_line(now=T + 601) == "", line)
SR.observe("heart_rate", 60, at=T + 4000, now=T + 4000); d = SR.observe("heart_rate", 100, at=T + 4010, now=T + 4010)
check("an hour later the limit has room again", d["reacted"], d)
check("an unexpired reaction is pending; after expiry it is gone", len(SR.pending(now=T + 4011)) == 1 and SR.pending(now=T + 4011 + 601) == [])

print("\n--- presence: a flip, with a small feel nudge, no device, no reach recorded ---")
d = SR.observe("presence", True, at=T + 5000, now=T + 5000)
check("first presence value is not a change", d["reacted"] is False)
d = SR.observe("presence", False, at=T + 5100, now=T + 5100)
check("home -> away is a reaction", d["reacted"] and "left" in d["reaction"]["change"])
d = SR.observe("presence", True, at=T + 5200, now=T + 5200)
check("away -> home is a reaction with the named feel nudge through emoclaw", d["reacted"] and d["reaction"]["felt"] == {"Warmth": 0.02, "Connection": 0.02} and nudges[-1][1] == "sensor:presence", (d, nudges))
check("no encounter is recorded as made (nothing reached out)", not os.path.exists(os.path.join(MEM, "encounters.json")))
src = open(os.path.join(REPO, "scripts", "sensor_reactions.py")).read()
check("the module never imports a device link", "toy_link" not in src and "thruster" not in src and "device_patterns" not in src)
d = SR.observe("weather", 1, now=T)
check("a sensor without a named contract never reacts", d["reacted"] is False and "without a contract" in d["why"])

print("\n--- the writers call it; the prompts carry it ---")
hr = open(os.path.join(REPO, "scripts", "heart_rate.py")).read(); hp = open(os.path.join(REPO, "scripts", "home_presence.py")).read(); sv = open(os.path.join(REPO, "bin", "server.py"), errors="replace").read()
check("heart_rate.record observes with the reading's own time", '_sr.observe("heart_rate", bpm, at=rec["observed_ts"])' in hr)
check("home_presence.main observes only when a previous state exists", '_sr.observe("presence", bool(st.get("home")), at=st.get("checked"))' in hp and 'if "home" in prev:' in hp)
check("chat and avatar contexts both carry the line", sv.count("sensor_reactions") >= 2 and "_sr_i.context_line()" in sv and "_sr_v.context_line()" in sv)
rows = [json.loads(l) for l in open(SR.LOG)]
check("every decision is logged with its reason", len(rows) >= 11 and all("why" in r for r in rows))
print("\n%d/%d" % (sum(R), len(R))); sys.exit(0 if all(R) else 1)
