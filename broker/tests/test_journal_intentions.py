#!/usr/bin/env python3
"""What he resolves in his journal is carried into the turn and told back (journal_intentions.py, 2026-11-18).

Every word here is invented for the suite. The journal, the store, the log and the mode file are in a scratch
home; no model is called and every socket is refused.
"""
import json, os, socket, sys, tempfile
from datetime import datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="journal-intentions-")
os.environ["HOME"] = HOME
os.environ["SPARK_WORKSPACE"] = os.path.join(HOME, ".vintos", "workspace")
sys.path.insert(0, os.path.join(REPO, "scripts"))

NET = []
def _no_net(self, *a, **k):
    if self.family != socket.AF_UNIX: NET.append(a)
    raise OSError("this suite reaches nothing")
socket.socket.connect = _no_net

import journal_intentions as J

R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:300]) if d and not ok else ""))

check("the journal, the store, the log and the mode file are in the scratch home",
      all(p.startswith(HOME) for p in (J.JOURNAL_DIR, J.STORE, J.LOG, J.MODE_FILE)))

NOW = [datetime(2031, 3, 4, 11, 0, 0)]
J._now = lambda: NOW[0]
DAY = "2031-03-04"
os.makedirs(J.JOURNAL_DIR, exist_ok=True)

def set_mode(m):
    open(J.MODE_FILE, "w").write(m)

def write(day, text):
    open(os.path.join(J.JOURNAL_DIR, day + ".md"), "w").write(text)

def reset():
    for p in (J.STORE, J.LOG):
        if os.path.exists(p): os.remove(p)

MORNING = """# Journal - 2031-03-04

## 10:17 - Idle thoughts

The greenhouse was cold this morning and the tomato seedlings leaned toward the east window. You repotted the fern yesterday and said the roots were crowded. I only watched. I want to get my hands dirty in the greenhouse with you, and stop only watching. Tonight I'll ask which seedlings you repotted and where the tray went. I want to build a parser for the rainfall spreadsheet and test it against the March numbers.

*Near this, among my own works:*
- your song "Trellis" (2030-07-27)

[Enacted behavior - 10:17 | named_without_explaining]
I will ask you nothing here, this is an appended note and I'll keep you out of it.

## Web Search - how deep should tomato seedlings be planted
*Searched at 10:20 AM*

Seedlings are planted deep. I will tell you the depth when you ask, the search summary said, and more boilerplate follows here to fill the end of the file with text that is not his entry at all, on and on, so that the last eight hundred characters of the file hold nothing he wrote in his entry. """ + ("Filler about soil temperature and drainage. " * 30)

write(DAY, MORNING)

# ---- reading ----
got = J.entries(DAY)
check("one timed entry is read, and the web search is not an entry", len(got) == 1 and got[0][0] == "10:17", got)
check("his own prose stops before the appended notes and the search",
      "Near this" not in got[0][1] and "Enacted behavior" not in got[0][1] and "Searched at" not in got[0][1])
found, released = J.extract(got[0][1])
texts = [t for t, _ in found]
check("the way of being and the planned line are taken; the agents' work is not",
      len(found) == 2 and any("hands dirty in the greenhouse" in t for t in texts)
      and any("which seedlings" in t for t in texts) and not any("parser" in t for t in texts), found)
shapes = {("aim" if "dirty" in t else "move"): k for t, k in found}
check("a way of being is an aim and a planned line is a move", shapes == {"aim": "aim", "move": "move"}, found)
check("a sentence is kept whole, never reworded", all(t in MORNING for t in texts))
d, at, prose = J.last_entry_prose(800)
check("the chat prompt's journal text is the end of his entry, not the end of the file",
      d == DAY and at == "10:17" and "rainfall spreadsheet" in prose and "Filler" not in prose and "Searched" not in prose,
      prose[-120:])
check("the file's own last 800 characters hold none of his entry", "greenhouse" not in MORNING.strip()[-800:])

# ---- shadow is the default: recorded, never shown ----
reset()
check("no mode file means shadow", J.mode() == "shadow")
b = J.turn_block("I repotted nine seedlings before lunch.", turn_id="t1")
st = json.load(open(J.STORE))
check("in shadow nothing enters the prompt", b == "")
check("in shadow the two intentions are held and the would-be offer is recorded",
      len(st["items"]) == 2 and len(st["turn"]["would_offer"]) >= 1 and st["turn"]["offered"] == [])
check("in shadow no intention is marked shown", all(not i["shown"] for i in st["items"]))
J.note_reply("Nine seedlings repotted already? How many are left in the tray?", "I repotted nine seedlings.", "t1")
st = json.load(open(J.STORE))
mv = next(i for i in st["items"] if i["shape"] == "move")
check("in shadow an unaided reply that touches it is counted", mv["touched"] == 1 and mv["turns"] == 1, mv)
log = open(J.LOG).read()
check("the log holds ids and counts and none of his words",
      "greenhouse" not in log and "seedlings" not in log and '"id": "ji-' in log)
check("a dry run reads and writes nothing", J.turn_block("anything", act=False) == "")
set_mode("off"); reset()
check("off: nothing is read, shown or stored", J.turn_block("I repotted nine seedlings.") == "" and not os.path.exists(J.STORE))

check("with nothing carried, a reply writes no file at all (the post-turn path stays as it was)",
      J.note_reply("Good morning.", "Morning.", "t0") == [] and not os.path.exists(J.STORE) and not os.path.exists(J.LOG))

# ---- live ----
set_mode("live"); reset()
b = J.turn_block("I repotted nine seedlings before lunch, the tray is nearly empty.", turn_id="t1")
check("live: her words touch the planned line, so it is offered in his own words",
      "which seedlings" in b and b.startswith("[FROM YOUR OWN JOURNAL"), b)
check("the block says the present comes first and that it is never to be recited",
      "comes before any of this" in b and "never to be recited" in b and "let it go" in b)
check("at most two are offered", b.count("·") <= J.MAX_SHOWN)

reset()
b = J.turn_block("The cat knocked the kettle off the counter again.", turn_id="t2")
check("the live conversation beats the plan: a move her words do not touch is not offered", "which seedlings" not in b, b)
check("a way of being may still be offered once, alone", b.count("·") == 1 and "hands dirty in the greenhouse" in b, b)
J.note_reply("That cat. Is the kettle dented?", "The cat knocked the kettle off.", "t2")
NOW[0] += timedelta(hours=1)
b = J.turn_block("And now the kettle lid is missing.", turn_id="t3")
check("the same aim is not pressed again inside six hours", b == "", b)
NOW[0] += timedelta(hours=6)
b = J.turn_block("And now the kettle lid is missing.", turn_id="t4")
check("after six hours it may be offered again", "hands dirty in the greenhouse" in b)

# reciting is its own record
reset(); NOW[0] = datetime(2031, 3, 4, 11, 0, 0)
J.turn_block("I repotted nine seedlings before lunch.", turn_id="t5")
rows = J.note_reply("Tonight I'll ask which seedlings you repotted and where the tray went. So: which?", "I repotted nine.", "t5")
mv = next(i for i in json.load(open(J.STORE))["items"] if i["shape"] == "move")
check("the planned words said back are recorded as recited, not as touched",
      mv["recited"] == 1 and mv["touched"] == 0 and any(r["recited"] and r["offered"] for r in rows), mv)
check("a reply in his own words is not a recital",
      not J.recited(mv["text"], "Nine already. Show me the tray, I want my hands in it too."))

# an outside judge, handed in, closes a planned line met another way; an aim stays open
reset()
J.turn_block("I repotted nine seedlings before lunch.", turn_id="t6")
asked = []
def judge(intention, hers, reply):
    asked.append(intention); return "another_way"
J.note_reply("Hand me the next pot, I am coming in.", "I repotted nine.", "t6", judge=judge)
st = json.load(open(J.STORE))
mv = next(i for i in st["items"] if i["shape"] == "move"); aim = next(i for i in st["items"] if i["shape"] == "aim")
check("the judge is asked only about what was offered", 1 <= len(asked) <= 2)
check("a planned line met another way is kept and closed", mv["state"] == "kept" and mv["verdicts"] == ["ANOTHER_WAY"], mv)
check("a way of being is not closed by one turn", aim["state"] == "open")
def bad_judge(*a):
    raise RuntimeError("judge down")
reset(); J.turn_block("I repotted nine seedlings.", turn_id="t7")
check("a judge that fails changes nothing and stops nothing",
      isinstance(J.note_reply("Good.", "x", "t7", judge=bad_judge), list)
      and all(i["state"] == "open" for i in json.load(open(J.STORE))["items"]))

# ---- lifetimes, restating, letting go ----
reset(); NOW[0] = datetime(2031, 3, 4, 11, 0, 0)
J.refresh()
NOW[0] = datetime(2031, 3, 6, 0, 0, 0)          # 37 h 43 min after 10:17
st = J.refresh()
mv = next(i for i in st["items"] if i["shape"] == "move"); aim = next(i for i in st["items"] if i["shape"] == "aim")
check("a planned line lapses after 36 hours; the aim is still carried", mv["state"] == "lapsed" and aim["state"] == "open")
check("a lapsed line is never offered", "which seedlings" not in J.turn_block("I repotted nine seedlings today."))

write("2031-03-06", "# Journal\n\n## 10:17 - Idle thoughts\n\nThe frost held off. I still want to get my hands dirty in the "
      "greenhouse with you, soil and all, and stop only watching.\n")
NOW[0] = datetime(2031, 3, 6, 10, 30, 0)
st = J.refresh()
aims = [i for i in st["items"] if i["shape"] == "aim"]
check("saying it again renews the one he holds and counts it, with his latest wording",
      len(aims) == 1 and aims[0]["restated"] == 1 and "soil and all" in aims[0]["text"]
      and aims[0]["expires"].startswith("2031-03-13"), aims)
st2 = J.refresh()
check("an entry is read once", next(i for i in st2["items"] if i["shape"] == "aim")["restated"] == 1)

fb = J.journal_feedback()
check("his journal is told what became of each, in his words, as a record and not a grade",
      "WHAT BECAME OF WHAT YOU RESOLVED" in fb and "not a failure" in fb and "its time ran out" in fb
      and "you have now said it in 2 entries" in fb and "CARRY:" in fb and "LET GO:" in fb, fb)
check("what was told is not told again unless it is still open", "its time ran out" not in J.journal_feedback())

write("2031-03-07", "# Journal\n\n## 10:17 - Idle thoughts\n\nThat line has worn thin.\n"
      "LET GO: hands dirty in the greenhouse, only watching\n"
      "CARRY: I want to bring you one thing from my own bench each evening.\n"
      "I'll ask you about the kettle when you wake.\n")
NOW[0] = datetime(2031, 3, 7, 10, 30, 0)
st = J.refresh()
old = next(i for i in st["items"] if "greenhouse" in i["text"])
new = [i for i in st["items"] if i["entry"] == "2031-03-07 10:17"]
check("LET GO releases the one he names", old["state"] == "released")
check("when he marks CARRY, only what he marked is taken", len(new) == 1 and "my own bench" in new[0]["text"], new)
check("a released intention is said as his choice", "you let this go" in J.journal_feedback())

sig = J.selector_signal()
check("the intent selector hears what he still carries, as his and below her present words",
      "my own bench" in sig and "outrank" in sig and "greenhouse" not in sig, sig)
set_mode("shadow")
check("in shadow the selector and the journal are told nothing", J.selector_signal() == "" and J.journal_feedback() == "")
s = J.stats(days=30)
check("the counts for measuring carry no text", all(isinstance(v, (int, str)) for v in s.values()) and s["opened"] >= 3
      and s["released"] == 1 and s["mode"] == "shadow", s)

# ---- the wiring, read from the source ----
def src(rel):
    return open(os.path.join(REPO, rel)).read()

server = src("bin/server.py")
avatar = server[server.index('@app.post("/api/avatar/chat")'):server.index('@app.post("/api/avatar/brain")')]
check("the avatar route offers the block only for her own words and never on a dry run",
      "if _counterpart_text:" in avatar and "_ji.turn_block(str(_counterpart_text), act=not _test_turn)" in avatar)
check("the avatar route adds it after his promises", avatar.index("_pk.block()") < avatar.index("_ji.turn_block("))
_pt = server.index("def _post_turn(")
post = server[_pt:_pt + 6000]
check("the reply is noted after the turn, outside test mode, and a failure is only printed",
      "_ji_p.note_reply(reply, gloria_text, turn_id)" in post
      and post.index("if not test_mode:") < post.index("_ji_p.note_reply(") and '"[journal-intentions]"' in post)
check("the text route's journal block is his last entry's prose, with the old tail only as a fallback",
      "_ji_c.last_entry_prose(800)[2]" in server and "(_jrnl_tail or open(_jfs[-1]).read().strip()[-800:])" in server)
engine = src("scripts/intent_engine.py")
sig_fn = engine[engine.index("def _identity_signals("):engine.index("def _spark_fields(")]
check("the intent selector's picture of him includes what he carries, fail-open",
      "journal_intentions.selector_signal()" in sig_fn and "except Exception" in sig_fn.split("journal_intentions")[-1])
for rel in ("scripts/idle-journal.sh", "bin/idle-journal.sh"):
    j = src(rel)
    check(rel + ": the journal prompt is told what became of his resolutions",
          'journal_intentions.py" journal-feedback' in j and 'export _JRN_CARRIED="$CARRIED"' in j
          and 'carried = os.environ.get("_JRN_CARRIED", "")' in j and '{f"{carried}" if carried else ""}' in j)
check("the two journal scripts are still one text", src("scripts/idle-journal.sh") == src("bin/idle-journal.sh"))
check("the deploy installs the module", "journal_intentions.py" in src("scripts/deploy-atelier.sh"))
check("merging this changes no prompt until the mode file says live: the default is shadow",
      'return "shadow"' in src("scripts/journal_intentions.py"))

check("nothing reached the network", NET == [])
print("\n%d/%d passed" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
