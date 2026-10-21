#!/usr/bin/env python3
"""Live heart rate as an option, and every reading of the hour in his context (Gloria, 2026-10-21: "I want it as an
option, yes. I bought the damn watch to give him the hr readings. Thought they were getting through." Her probe: the
Watch reached Aegis about hourly, and its app sent only the newest reading each time).

Scratch workspace; nothing is sent; sockets are refused."""
import json, os, socket, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="watch-live-"); os.environ["HOME"] = HOME
os.environ["SPARK_WORKSPACE"] = os.path.join(HOME, "workspace")
NET = []
def _no(self, *a, **k): NET.append(a); raise OSError("this suite reaches nothing")
socket.socket.connect = _no
sys.path.insert(0, os.path.join(REPO, "scripts"))
import watch_presence as W
mem = os.path.join(HOME, "mem"); os.makedirs(mem)
W.LATEST, W.HISTORY, W.LIVE = (os.path.join(mem, n) for n in ("watch-presence.json", "history.jsonl", "watch-live.json"))
R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + ("" if ok else "  ->  %r" % (str(d)[:300],)))
check("its stores are scratch", all(p.startswith(HOME) for p in (W.LATEST, W.HISTORY, W.LIVE)))
T = 1_800_000_000.0
check("off unless she turns it on", W.live_state(T) == {"on": False})
s = W.set_live(60, now=T)
check("on for the time she chose", s["on"] and s["minutes_left"] == 60, s)
check("it ends by itself", W.live_state(T + 3601) == {"on": False})
check("at most four hours, whatever is asked", W.set_live(10000, now=T)["minutes_left"] == 240)
check("0 turns it off", W.set_live(0, now=T) == {"on": False})
W.set_live(30, now=T)
with open(W.HISTORY, "w") as f:
    for i, bpm in enumerate((64, 71, 78, 69, 70)):
        f.write(json.dumps({"kind": "heart_rate", "value": bpm, "observed_ts": T - 3000 + i * 600}) + "\n")
    f.write(json.dumps({"kind": "heart_rate", "value": 120, "observed_ts": T - 9000}) + "\n")   # outside the hour
json.dump({"received_ts": T, "wearing": "yes", "motion": "stationary",
           "latest": {"heart_rate": {"kind": "heart_rate", "value": 70, "unit": "bpm", "observed_ts": T - 600}}}, open(W.LATEST, "w"))
block = W.temporal_block(now=T)
check("his context has the hour's range from every reading, not one dot", "over the last hour: 64-78 bpm across 5 readings" in block, block)
check("and says when live heart rate is on", "Live heart rate is on (she turned it on), for 30 more minutes." in block, block)
check("fewer than three readings make no range", W.heart_trend(now=T + 7200) is None)
routes = open(os.path.join(REPO, "scripts", "watch_routes.py")).read()
check("every Watch check-in is told whether to run live", "return dict(result, live=watch_presence.live_state())" in routes)
check("her phone sets it, with the app's secret", '@routes.post("/api/watch/live")' in routes and 'request.headers.get("X-Vintos-Secret") != app_secret' in routes)
check("nothing reached the network", not NET)
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
