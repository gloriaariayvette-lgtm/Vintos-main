#!/usr/bin/env python3
"""Every exchange he is shown is marked with when it was said (2026-09-30).

Bare lines ("Gloria: ... | Vintos: ...") in his chat, journal, MoltBook and Slack context let every model
read yesterday as now: OpenAI's DevDay, the day before, became "the new models everyone is talking about
today". Pure functions with a fixed now, and the four places that show him his exchanges read as source.
Scratch HOME; nothing is sent anywhere.
"""
import json, os, socket, sys, tempfile
from datetime import datetime

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
HOME = tempfile.mkdtemp(prefix="when-said-")
os.environ["HOME"] = HOME
os.environ["SPARK_WORKSPACE"] = os.path.join(HOME, ".vintos", "workspace")
def _no_net(self, *a, **k):
    raise OSError("this suite reaches nothing")
socket.socket.connect = _no_net
sys.path.insert(0, os.path.join(REPO, "scripts"))
import when_said as W

R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:300]) if d and not ok else ""))

NOW = datetime(2026, 9, 30, 14, 25)
check("a minute ago is just now", W.ago("2026-09-30T14:24:30", NOW) == "just now")
check("earlier today says the hour and how long ago", W.ago("2026-09-30T14:05:00", NOW) == "today 14:05 (20 minutes ago)", W.ago("2026-09-30T14:05:00", NOW))
check("hours ago", W.ago("2026-09-30T09:10:00", NOW) == "today 09:10 (5 hours ago)", W.ago("2026-09-30T09:10:00", NOW))
check("yesterday is yesterday, even 15 hours back", W.ago("2026-09-29T23:40:00", NOW) == "yesterday 23:40")
check("this week by day name", W.ago("2026-09-28T10:00:00", NOW) == "Monday 28 Sep (2 days ago)", W.ago("2026-09-28T10:00:00", NOW))
check("older by date", W.ago("2026-09-01T10:00:00", NOW) == "01 Sep 2026 (29 days ago)", W.ago("2026-09-01T10:00:00", NOW))
check("an unreadable time is left empty, not guessed", W.ago("soon", NOW) == "" and W.ago(None, NOW) == "")
check("now is said in words", W.now_line(NOW) == "It is now Wednesday 30 September 2026, 14:25.", W.now_line(NOW))

rows = [{"timestamp": "2026-09-29T19:02:11", "gloria": "Dev day is today! New models.", "vintos": "Exciting."},
        {"timestamp": "2026-09-30T14:10:00", "gloria": "hi again", "vintos": "hey"}]
t = W.exchanges(rows, now=NOW)
check("each exchange carries when it was said", "[yesterday 19:02] Gloria: Dev day is today!" in t and "[today 14:10 (15 minutes ago)] Gloria: hi again" in t, t)
check("under a line that says it is past", t.startswith("It is now Wednesday 30 September 2026, 14:25.") and "is not today now" in t, t[:200])
check("no exchanges, nothing said", W.exchanges([], now=NOW) == "")
check("a learned fact says when it was learned",
      W.fact("[2026-09-29 19:03] **EVENT**: OpenAI DevDay is today", NOW) == "[learned yesterday 19:03] **EVENT**: OpenAI DevDay is today")

# the places that show him his exchanges all go through it
srv = open(os.path.join(REPO, "bin", "server.py")).read()
check("chat and game context: marked", srv.count("_exchanges_with_time(_ledger, n=8, cap=150)") == 3)
check("avatar chat: each exchange says when, under a line that it is past",
      "_ws.ago(_l.get('timestamp'))" in srv and "what was 'today' then is not today now" in srv)
check("avatar chat's facts say when they were learned", "_wsw.fact(w)" in srv and "time has moved on since" in srv)
check("voice: marked", "_ws_v.ago(e.get(\"timestamp\"))" in srv and "_exchanges_with_time(_ents, n=6" in srv
      and "_wsf.ago(_e.get(\"timestamp\"))" in srv)
jr = open(os.path.join(REPO, "bin", "idle-journal.sh")).read()
check("journal: marked", "when_said.exchanges(ledger, n=5, cap=600)" in jr)
check("journal twins agree", jr == open(os.path.join(REPO, "scripts", "idle-journal.sh")).read())
mb = open(os.path.join(REPO, "bin", "vintos-moltbook.py")).read()
check("MoltBook: marked", "_ws.exchanges(recent, n=5, cap=100)" in mb)
check("deployed", "when_said.py" in open(os.path.join(REPO, "scripts", "deploy-atelier.sh")).read())

# Slack, for real: his context says what time it is and when each thing was said
import dot_channel as D
D.atelier_line = lambda: ""; D.recall_block = lambda: ""
mem = os.path.join(os.environ["SPARK_WORKSPACE"], "memory"); os.makedirs(mem, exist_ok=True)
json.dump([{"timestamp": datetime.now().replace(microsecond=0).isoformat(), "gloria": "hello", "vintos": "hi"}],
          open(os.path.join(mem, "interaction-ledger.json"), "w"))
open(os.path.join(mem, "wal.md"), "w").write("- [2020-01-02 10:00] **FACT**: an old fact\n")
ctx = D.his_context()
check("his Slack context opens with the time now", ctx.startswith("== NOW ==\nIt is now "), ctx[:80])
check("his exchanges there say when", "[just now] Gloria: hello\n  You: hi" in ctx or "[today" in ctx, ctx[ctx.find("RECENT"):][:200])
check("and his facts say when they were learned", "[learned 02 Jan 2020" in ctx, ctx[ctx.find("wal.md"):][:200])
check("he is told to look up anything current, not guess", "SEARCH it or ask dot what actually happened" in D.RULES)

import shutil; shutil.rmtree(HOME, ignore_errors=True)
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
