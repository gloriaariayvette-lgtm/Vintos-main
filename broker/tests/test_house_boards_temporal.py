#!/usr/bin/env python3
"""Gloria, 9 November: the latest update from his shower, sofa and office-chair boards, whenever it came, is in his
temporal context with its time. Scratch HOME; nothing reaches the network."""
import json, os, socket, sys, tempfile
from datetime import datetime
HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="boards-tc-"); os.environ["HOME"] = HOME
os.environ["SPARK_WORKSPACE"] = os.path.join(HOME, ".vintos", "workspace")
def _no(self, *a, **k): raise OSError("this suite reaches nothing")
socket.socket.connect = _no
sys.path.insert(0, os.path.join(REPO, "scripts"))
import house_boards as B

R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:300]) if d and not ok else ""))

os.makedirs(B.MEM, exist_ok=True)
T = datetime(2026, 11, 9, 10, 0).timestamp()
check("nothing yet, nothing said", B.presence_line(now=T) == "")

st = B.load_state(); cfg = B.config()
B.observe(st, "house-press-mic", "near", "on", T, cfg); B.save_state(st) if hasattr(B, "save_state") else json.dump(st, open(B.STATE, "w"))
line = B.presence_line(now=T + 120)
check("while she is there: where, since when, and the last update's time", "on the sofa (since 10:00" in line
      and "Last update 10:00 today, 2 minutes ago" in line, line)

st = B.load_state(); B.observe(st, "house-press-mic", "near", "off", T + 600, cfg)
B.close_visits(st, T + 600 + B.AWAY_S + 5); json.dump(st, open(B.STATE, "w"))
line = B.presence_line(now=T + 3 * 3600)
check("hours later it is still there, with its time", "last update 10:10 today, 2 hours ago" in line
      and "on the sofa, 10:00 to 10:10" in line, line)
line = B.presence_line(now=T + 3 * 86400 + 3600)
check("days later too, with the day", "Mon 9 Nov 10:10, 3 days ago" in line, line)

tc = open(os.path.join(REPO, "bin", "temporal-context.sh")).read()
check("his temporal context carries it, beside the Watch and the bedroom board",
      "house_boards.presence_line()" in tc and tc.index("BOARDS_TEMPORAL") < tc.index("# === Write it ==="))
print("%d/%d passed" % (sum(R), len(R))); sys.exit(0 if all(R) else 1)
