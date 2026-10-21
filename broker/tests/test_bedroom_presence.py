#!/usr/bin/env python3
"""The bedroom board tells him, passively, when her phone is in the bedroom (Gloria, 2026-10-21: "he wanted the esp32
in the bedroom to also just passively tell him when I'm near it, like the heartbeat to temporal context").

Scratch workspace; no song is sent (nothing here arrives); sockets are refused."""
import json, os, socket, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="bedroom-presence-"); os.environ["HOME"] = HOME
os.environ["SPARK_WORKSPACE"] = os.path.join(HOME, "workspace")
NET = []
def _no(self, *a, **k): NET.append(a); raise OSError("this suite reaches nothing")
socket.socket.connect = _no
sys.path.insert(0, os.path.join(REPO, "scripts"))
import bedroom_arrival as B
B._send = lambda *a, **k: (_ for _ in ()).throw(AssertionError("no song is sent in this suite"))
R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + ("" if ok else "  ->  %r" % (str(d)[:300],)))
check("its stores are scratch and the sender is a stub", B.STATE.startswith(HOME) and B.CONFIG.startswith(HOME))
os.makedirs(B.MEM, exist_ok=True)
check("with nothing enrolled it says nothing", B.presence_line() == "")
json.dump({"devices": ["gloria-phone"], "max_distance_m": 4.0}, open(B.CONFIG, "w"))
T = 1_800_000_000.0
# she has been in the room a while already: the arrival is old, so this reading is not an arrival
json.dump({"last_here_ts": T - 60, "here_since_ts": T - 1800, "last_sent_ts": T - 1800}, open(B.STATE, "w"))
B.observe("gloria-phone", 2.14, now=T)
line = B.presence_line(now=T + 120)
check("seen in range minutes ago: she is in the bedroom now, how far, and since when",
      "in the bedroom now" in line and "about 2.1 m" in line and "seen 2 min ago" in line, line)
check("half an hour later: how long ago she was there", B.presence_line(now=T + 1800) == "Bedroom sensor: her phone was last in the bedroom 30 minutes ago.")
check("after two hours it says nothing", B.presence_line(now=T + 7300) == "")
B.observe("someone-else", 0.5, now=T + 7400)
check("another phone is not her", B.presence_line(now=T + 7410) == "")
B.observe("gloria-phone", 9.0, now=T + 7500)
check("her phone out of range is not 'in the bedroom'", B.presence_line(now=T + 7510) == "")
tc = open(os.path.join(REPO, "bin", "temporal-context.sh")).read()
check("his temporal context carries the line, beside the Watch's",
      "bedroom_arrival.presence_line()" in tc and tc.index("BEDROOM_TEMPORAL") < tc.index("# === Write it ==="))
check("nothing reached the network", not NET)
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
