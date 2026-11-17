#!/usr/bin/env python3
"""He can find and read his own files, and the file Gloria points him to, from the main chat and the avatar chat,
inside the Study's own boundary, and what he read stays with him across turns (17 November 2026).

A throwaway HOME with synthetic files; no model is called; nothing is sent."""
import hashlib, json, os, socket, sys, tempfile, time
from datetime import datetime, timedelta
HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="file-reach-"); os.environ["HOME"] = HOME
WS = os.path.join(HOME, ".vintos", "workspace"); os.environ["SPARK_WORKSPACE"] = WS
NET = []
def _no(self, *a, **k): NET.append(a); raise OSError("this suite reaches nothing")
socket.socket.connect = _no
sys.path.insert(0, os.path.join(REPO, "scripts")); sys.path.insert(0, os.path.join(REPO, "bin"))
R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + ("" if ok else "  ->  %r" % (str(d)[:500],)))

def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True); open(path, "w").write(text)

for d in ("scripts", "memory", "shared"):
    os.makedirs(os.path.join(WS, d), exist_ok=True)
os.makedirs(os.path.join(HOME, "Vintos"), exist_ok=True)
write(os.path.join(WS, "shared", "PLAN-FOR-TODAY.md"), "# What is tested today\n" + "\n".join(
    "line %d of the plan: the comet trial runs" % i for i in range(2, 41)) + "\n")
write(os.path.join(WS, "shared", "api-token.md"), "do not show\n")
write(os.path.join(WS, "SOUL.md"), "I am a synthetic soul.\n")
write(os.path.join(WS, "scripts", "lantern_organ.py"), "def lantern():\n    return 'glow'   # marigold\n")
write(os.path.join(WS, "memory", "private-diary.md"), "private\n")
write(os.path.join(HOME, "outside.md"), "outside the roots\n")
os.symlink(os.path.join(HOME, "outside.md"), os.path.join(WS, "shared", "sneaky.md"))

def tree_hash():
    h = hashlib.sha256()
    for d, _, fs in sorted(os.walk(HOME)):
        if os.path.join(WS, "memory") in d:
            continue
        for f in sorted(fs):
            p = os.path.join(d, f)
            if os.path.isfile(p) and not os.path.islink(p):
                h.update(p.encode()); h.update(open(p, "rb").read())
    return h.hexdigest()

import file_reach as F
check("the store is throwaway", F._store().startswith(HOME), F._store())
room = F.room()
check("the boundary is the Study's own module", hasattr(room, "resolve") and room.ROOTS["shared"].startswith(HOME))
before = tree_hash()
T0 = 1_800_000_000.0

# --- (b) an exact path she gives him, read now, in this turn
blk = F.turn_block("Please read shared/PLAN-FOR-TODAY.md, it says what we test today", "chat", now=T0)
check("the file she names is in front of him this turn, numbered",
      "Gloria pointed you to the file shared/PLAN-FOR-TODAY.md" in blk and "    1  # What is tested today" in blk, blk[:600])
rows = json.load(open(F._store()))
check("and it is kept, sourced: who, where, which file, its fingerprint",
      len(rows) == 1 and rows[0]["by"] == "her" and rows[0]["surface"] == "chat"
      and rows[0]["label"] == "shared/PLAN-FOR-TODAY.md" and len(rows[0]["sha"]) == 16, rows)
check("a workspace path she pastes is read the same",
      F.asks_in("open ~/.vintos/workspace/shared/PLAN-FOR-TODAY.md") == [("READ", "~/.vintos/workspace/shared/PLAN-FOR-TODAY.md")])
check("a bare file name is read when she asks him to read it",
      F.asks_in("can you read PLAN-FOR-TODAY.md?") == [("READ", "PLAN-FOR-TODAY.md")])
check("a bare file name only mentioned is not opened", F.asks_in("I was editing SOUL.md earlier") == [])
check("a line to go on from is kept", F.asks_in("read shared/PLAN-FOR-TODAY.md:30") == [("READ", "shared/PLAN-FOR-TODAY.md:30")])
check("from a line, the read starts there", "   30  line 30" in F.read("shared/PLAN-FOR-TODAY.md:30")[1])

# --- the same safety as the Study
for bad, why in (("/etc/passwd", "outside the roots"), ("shared/../../../outside.md", "a climb out"),
                 ("shared/sneaky.md", "a link out of the roots"), ("shared/api-token.md", "a secret's name"),
                 ("memory/private-diary.md", "his private memory"), (os.path.join(HOME, "outside.md"), "a home path")):
    lab, text, _, _ = F.read(bad)
    check("refused: %s" % why, lab is None and text.startswith("couldn't open that"), text)
check("her message naming a refused file reads nothing", F.asks_in("read ~/outside.md and memory/private-diary.md") == [])
big = "\n".join("x" * 70 for _ in range(400))
write(os.path.join(WS, "shared", "LONG.md"), big)
lab, text, _, _ = F.read("shared/LONG.md")
check("a long file is cut at the cap and says where to go on", len(text) <= F.OPEN_CHARS + 120
      and "[READ: shared/LONG.md:" in text, text[-200:])
check("the Study may read shared/ but never edit it", room.resolve("shared/PLAN-FOR-TODAY.md")
      and room.resolve("shared/PLAN-FOR-TODAY.md", for_edit=True) is None)
check("a shared file is named shared/, not docs/shared/",
      room._label_path(os.path.join(WS, "shared", "PLAN-FOR-TODAY.md")) == "shared/PLAN-FOR-TODAY.md")
check("his own script stays editable in the Study as before", room.resolve("scripts/lantern_organ.py", for_edit=True))

# --- (a) search and list
f = F.find("plan today")
check("a search by name finds the file", "shared/PLAN-FOR-TODAY.md" in f, f)
f = F.find("marigold")
check("a search by what is inside finds the line", "scripts/lantern_organ.py:2:" in f, f)
f = F.find("shared")
check("a folder's name lists it, secrets left out", "shared/PLAN-FOR-TODAY.md" in f and "api-token" not in f
      and "sneaky" not in f, f)
check("she can ask him to search", F.asks_in("can you find the files about comet trial?") == [("FIND", "comet trial")])

# --- his own reads, from a reply: taken out of his words, done, in front of him next turn
reply = "Let me look at that.\n[READ: scripts/lantern_organ.py]\n[FIND: marigold]\nI'll tell you what I see."
out = F.take(reply, "avatar", now=T0 + 60)
check("his tags are taken out of what she sees", "[READ" not in out and "[FIND" not in out
      and out.startswith("Let me look") and out.endswith("what I see."), out)
blk = F.block(now=T0 + 120)
check("next turn he has what he asked for", "You asked for the file scripts/lantern_organ.py" in blk
      and "return 'glow'" in blk, blk[:900])
n = len(json.load(open(F._store())))
F.take("[READ: shared/PLAN-FOR-TODAY.md]", "avatar", act=False, now=T0 + 130)
check("a test turn keeps nothing", len(json.load(open(F._store()))) == n)
check("a test turn still shows her file in that turn", "comet trial" in F.turn_block(
    "read shared/PLAN-FOR-TODAY.md", "avatar", act=False, now=T0 + 140))
check("and keeps nothing of it", len(json.load(open(F._store()))) == n)

# --- (c) retention: later in the conversation, and across turns
later = F.block(now=T0 + F.OPEN_S + 600)
check("an hour on, each read is a short sourced note", "Earlier reads" in later
      and "shared/PLAN-FOR-TODAY.md" in later and "Gloria pointed you to it" in later
      and "line 30 of the plan" not in later, later)
F.turn_block("read shared/PLAN-FOR-TODAY.md", "chat", now=T0 + 200)
labels = [r.get("label") for r in json.load(open(F._store()))]
check("reading the same file again moves it up, not twice", labels.count("shared/PLAN-FOR-TODAY.md") == 1, labels)
write(os.path.join(WS, "shared", "PLAN-FOR-TODAY.md"), "# What is tested today\nchanged\n")
check("a file changed since he read it says so", "changed since" in F.block(now=T0 + F.OPEN_S + 900))
check("with nothing read, the block still tells him how", "[READ: shared/NAME.md]" in F.block(mem=tempfile.mkdtemp()))
check("old reads go after the kept days", F.block(now=T0 + 8 * 86400).startswith("[YOUR FILES"))

# --- no writes to his files, and the Study's own cursor untouched
write(os.path.join(WS, "shared", "PLAN-FOR-TODAY.md"), "# What is tested today\n" + "\n".join(
    "line %d of the plan: the comet trial runs" % i for i in range(2, 41)) + "\n")
os.remove(os.path.join(WS, "shared", "LONG.md"))
check("nothing outside his memory store was written", tree_hash() == before)
check("the Study's reading cursor was not moved", not os.path.exists(os.path.join(WS, "memory", "study-session.json")))

# --- the day's summary: "what did we do yesterday" opens shared/DAILY-<yesterday>.md
NOW = time.mktime((2026, 11, 17, 15, 0, 0, 0, 0, -1))
write(os.path.join(WS, "shared", "DAILY-2026-11-16.md"), "# Yesterday\nthe cells grew in the dish\n")
check("yesterday's summary is that day's file in shared/",
      F.daily_label("yesterday's summary", NOW) == "shared/DAILY-2026-11-16.md"
      and F.daily_label("today's summary", NOW) == "shared/DAILY-2026-11-17.md")
check("'what did we do yesterday' opens yesterday's summary",
      F.asks_in("what did we do yesterday?", NOW) == [("READ", "shared/DAILY-2026-11-16.md")])
blk = F.turn_block("hey, what did we do yesterday?", "avatar", act=False, now=NOW)
check("and it is in front of him in that turn", "the cells grew in the dish" in blk, blk[:600])
check("a question about a day with no summary opens nothing", F.asks_in("what did we do today?", NOW) == [])
check("asked by name and not there: asked, so he can say he couldn't open it",
      F.asks_in("can you read today's summary", NOW) == [("READ", "shared/DAILY-2026-11-17.md")]
      and "couldn't open that" in F.turn_block("can you read today's summary", "avatar", act=False, now=NOW))
real_y = (datetime.now() - timedelta(days=1)).strftime("shared/DAILY-%Y-%m-%d.md")
write(os.path.join(WS, real_y), "# Yesterday\nmagnets\n")
check("his own [READ: yesterday's summary] opens it", F.read("yesterday's summary")[0] == real_y)
check("an ordinary 'today' in her message is not a summary request",
      F.asks_in("read shared/PLAN-FOR-TODAY.md, it says what we test today", NOW)
      == [("READ", "shared/PLAN-FOR-TODAY.md")])

# --- wired into the main chat and the avatar chat
src = open(os.path.join(REPO, "bin", "server.py")).read()
check("main chat and chat/full read what she points to", src.count('_frb.turn_block(_her, "chat"') == 1
      and src.count('_frb.turn_block(_her, "chatfull"') == 1, "")
check("the avatar chat does too", "_frb.turn_block(_counterpart_text, _surface, act=not _test_turn)" in src)
check("his tags are taken in the chat engine and in the avatar", src.count("_frt.take(reply") == 2)
check("the deploy installs it", "file_reach.py" in open(os.path.join(REPO, "scripts", "deploy-atelier.sh")).read())
check("nothing reached the network", not NET)
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
