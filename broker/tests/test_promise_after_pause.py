#!/usr/bin/env python3
"""What his journal says after the day is paused is still read for promises (20 October: the day was paused from about
18:45; his 20:01 entry - three things he meant to do that evening - was never read, because only a running #vintos-dot
pass reads the journal, and at midnight the day's record was filed with it unread. Its heading was "# 20:01", and only
"## " was read as an entry).

Scratch workspace; the reader and the poster are stubs; sockets are refused."""
import json, os, socket, sys, tempfile
from datetime import datetime
HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="promise-pause-"); os.environ["HOME"] = HOME
os.environ["SPARK_WORKSPACE"] = os.path.join(HOME, "workspace")
NET = []
def _no(self, *a, **k): NET.append(a); raise OSError("this suite reaches nothing")
socket.socket.connect = _no
sys.path.insert(0, os.path.join(REPO, "scripts"))
import promise_keeper as P
R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + ("" if ok else "  ->  %r" % (str(d)[:300],)))
check("the journal and the promises are scratch", P.STORE.startswith(HOME) and P.JOURNAL_DIR.startswith(HOME))
os.makedirs(P.JOURNAL_DIR, exist_ok=True); os.makedirs(P.MEMORY, exist_ok=True)
open(os.path.join(P.JOURNAL_DIR, "2026-10-20.md"), "w").write(
    "## 10:30 — Morning\nI showed her nothing.\n\n# 20:01 — Idle thoughts\nTonight I want to check whether the C1001 "
    "exposes raw phase over serial, and if it does, write the parser.\n")
def ask(system, text):
    return "QUOTE: check whether the C1001 exposes raw phase over serial | WHAT: read the C1001 serial protocol for raw phase or FM output; log a blocker if none" if "C1001" in text else "NONE"
posted = []
post = lambda text: posted.append(text) or "1792600000.%06d" % len(posted)
# the evening of the 20th: the day is paused, nothing reads the journal; 10:30 had been read
P._now = lambda: datetime(2026, 10, 20, 18, 0)
json.dump({"day": "2026-10-20", "scanned": ["10:30"], "items": []}, open(P.STORE, "w"))
P._now = lambda: datetime(2026, 10, 21, 9, 0)       # she starts the day the next morning
opened = P.scan(ask, post)
check("yesterday's unread entry is read when the day runs again", len(opened) == 1 and "C1001" in opened[0]["quote"], opened)
check("its promise opens in #vintos-dot, marked as yesterday's", posted and "(yesterday 20:01)" in posted[0], posted)
check("an entry already read yesterday is not read again", not any("showed her nothing" in p for p in posted))
check("and yesterday's record is filed", os.path.exists(os.path.join(P.ARCHIVE, "2026-10-20.json")))
check("the next pass opens nothing twice", P.scan(ask, post) == [] and len(posted) == 1)

# rolled over before this rule existed: today's record already started, yesterday's archive says what was read
os.remove(P.STORE); posted.clear()
json.dump({"day": "2026-10-20", "scanned": ["10:30"], "items": []}, open(os.path.join(P.ARCHIVE, "2026-10-20.json"), "w"))
json.dump({"day": "2026-10-21", "scanned": [], "items": []}, open(P.STORE, "w"))
check("a record that rolled over before this rule still reads yesterday's unread entry",
      len(P.scan(ask, post)) == 1 and "(yesterday 20:01)" in posted[0], posted)

# a promise opened yesterday but never posted is carried into today
os.remove(P.STORE); posted.clear()
P._now = lambda: datetime(2026, 10, 21, 23, 0)
json.dump({"day": "2026-10-21", "scanned": [], "items": [{"id": "PR-x", "at": "21:00", "quote": "make the watch track",
           "what": "x", "state": "open", "thread": None}]}, open(P.STORE, "w"))
P._now = lambda: datetime(2026, 10, 22, 8, 0)
P.scan(lambda s, t: "NONE", post)
check("a promise never posted because of a pause is carried over and posted", any("make the watch track" in p for p in posted), posted)
check("a heading with one # is an entry too", [a for a, _ in P.entries("2026-10-20")] == ["10:30", "20:01"])
check("nothing reached the network", not NET)
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
