#!/usr/bin/env python3
"""What already exists in the world for the questions he is following reaches him in #vintos-dot (Gloria,
2026-10-04: "He's not really finding new repos... no one has brought up the Lytic Selection and Evolution
platform").

SOMETHING NEW was built only from his own sparks and his own unanswered questions, so nothing outside could ever
reach him. One line a day is searched for the platforms, datasets and repositories that exist for that question.

Scratch workspace; the web search is a stub and every socket is refused, so this suite reaches no search engine.
"""
import json, os, socket, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="line-prospect-")
os.environ["HOME"] = HOME
os.environ["SPARK_WORKSPACE"] = os.path.join(HOME, ".vintos", "workspace")
sys.path.insert(0, os.path.join(REPO, "scripts"))

NET = []
def _no_net(self, *a, **k):
    if self.family != socket.AF_UNIX: NET.append(a)
    raise OSError("this suite reaches nothing")
socket.socket.connect = _no_net

import line_prospect as P
import lab_lines as LL

R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:400]) if d and not ok else ""))

check("its store is in the scratch workspace", P.STORE.startswith(HOME))

LINE = {"id": "L-gloria-phage-rt", "state": "open",
        "title": "Array-associated reverse transcriptases in bacteriophages",
        "question": "Which bacteriophage genomes carry a reverse transcriptase beside a CRISPR array?"}
OTHER = {"id": "L-second", "state": "open", "title": "Phage lytic selection", "question": "How is lysis selected for?"}

# --- what it asks the world ---------------------------------------------------------------------------------
ASKED = []
def search(q):
    ASKED.append(q)
    if "platform" in q:
        return [{"title": "Lytic Selection and Evolution platform", "url": "https://lyse.example.org/",
                 "description": "A platform for selecting and evolving lytic phages."}]
    if "github" in q:
        return [{"title": "acme/retron-finder", "url": "https://github.com/acme/retron-finder",
                 "description": "Finds retron RTs next to CRISPR arrays."}]
    return [{"title": "A phage dataset", "url": "https://data.example.org/phage", "description": "Genomes."}]

terms = P._terms(LINE)
check("it searches his own question, not a generic phrase", "reverse" in terms and "bacteriophage" in terms.lower()
      and "which" not in terms.lower() and "beside" not in terms.lower(), terms)
found = P.find(LINE, search)
check("it asks for platforms, repositories and datasets", len(ASKED) == 3
      and any("platform" in q for q in ASKED) and any("github" in q for q in ASKED) and any("dataset" in q for q in ASKED), ASKED)
check("... and keeps what came back, one per site", [f["title"] for f in found]
      == ["Lytic Selection and Evolution platform", "acme/retron-finder", "A phage dataset"], found)
check("a search that fails takes nothing down", P.find(LINE, lambda q: (_ for _ in ()).throw(OSError("no network"))) == [])
check("a line with no words to search is left alone", P.find({"id": "x", "title": "", "question": ""}, search) == [])

# --- one line a day ------------------------------------------------------------------------------------------
LINES = [LINE, OTHER]
ASKED.clear()
got = P.prospect(search=search, lines=LINES)
check("one line is searched", len(got) == 3 and len(ASKED) == 3)
check("... and not a second one the same day", P.prospect(search=search, lines=LINES) == [] and len(ASKED) == 3)
check("... and the line looked at longest ago is the one taken", json.load(open(P.STORE))["searched_today"] == [LINE["id"]]
      or json.load(open(P.STORE))["searched_today"] == [OTHER["id"]], json.load(open(P.STORE))["searched_today"])

# --- what he is shown ------------------------------------------------------------------------------------------
block = P.block()
check("he is shown what exists, with the line it is for", "WHAT ALREADY EXISTS FOR YOUR LINES" in block
      and "Lytic Selection and Evolution platform" in block and "L-gloria-phage-rt" in block, block)
check("... with its address, so he can go and look", "https://lyse.example.org/" in block)
check("... and told to look before planning another experiment, and to answer on the line",
      "before you plan another experiment" in block and "LINE <id>" in block and "REPOS:" in block, block)
check("ignoring it is a choice he is told he is making", "Not looking is a choice" in
      open(os.path.join(REPO, "scripts", "dot_channel.py")).read())

# --- said once it is answered, nagged while it is not --------------------------------------------------------------
check("what he said he is doing with one stops it being shown",
      P.answered("https://lyse.example.org/", "it only does lysis assays; not for this line")
      and "Lytic Selection" not in P.block())
check("an unknown address answers nothing", not P.answered("https://nowhere.example/", "x"))
for _ in range(P.NAGS):
    P.block()
check("being shown the same ones and saying nothing is said plainly", "said nothing about any of them" in P.block(), P.block())
for _ln in json.load(open(P.STORE))["lines"].values():     # he answers every one of them
    for _f in _ln["found"]:
        P.answered(_f["url"], "looked; not for this line")
check("with nothing left unanswered, he is shown nothing at all", P.block() == "", P.block())

# --- the room itself asks, once a day (Gloria: "Someone should have said Lytic Selection and Evolution by now") ---
d = P.load(); d.pop("asked_on", None); P.save(d)
THIRD = {"id": "L-third", "state": "open", "title": "Prophage induction", "question": "What triggers induction?"}
import lab_lines as _LL
_LL.open_lines = lambda d=None: [LINE, OTHER, THIRD]
searched = set((P.load().get("lines") or {}).keys())
check("the lines nobody has looked into are known: every open one but the one searched above",
      [l["id"] for l in P.unexamined()] == ["L-second", "L-third"] and searched == {LINE["id"]}, (P.unexamined(), searched))
line_id, ask = P.ask_the_room()
check("the room asks GrokBot what exists for one of them", line_id == "L-second" and ask.startswith("@GrokBot")
      and "Phage lytic selection" in ask and "How is lysis selected for?" in ask, ask)
check("... for things he could run, not papers", "not papers" in ask and "link" in ask
      and ("platform" in ask.lower() and "repositor" in ask.lower()), ask)
check("... once a day", P.ask_the_room() == ("", ""))
d = P.load(); d.pop("asked_on", None); P.save(d)
_LL.open_lines = lambda d=None: [LINE]
check("with every open line already looked into, the room asks nothing", P.ask_the_room() == ("", ""))

# --- GrokBot's answer reaches the line (Chat's audit, 2026-10-05: it named INPHARED2, PADLOC and CRISPRCasTyper and
# nothing took them anywhere) ---------------------------------------------------------------------------------------
d = P.load(); d.pop("asked_on", None); P.save(d)
_LL.open_lines = lambda d=None: [LINE, OTHER, THIRD]
line_id, ask = P.ask_the_room()
check("the ask is kept with its line's title", P.load()["asked"][-1].get("title") == OTHER["title"] or
      P.load()["asked"][-1].get("title") == THIRD["title"], P.load()["asked"][-1])
check("where it went is noted once it is posted", P.asked_in(line_id, "1767700000.000100")
      and P.load()["asked"][-1]["ts"] == "1767700000.000100")
ANSWER = ("Here are three you can run:\n"
          "1. **INPHARED2** - a curated database of complete phage genomes <https://github.com/RyanCook94/inphared|inphared>\n"
          "2. PADLOC: finds antiphage defence systems, retrons among them\n"
          "- CRISPRCasTyper — types CRISPR-Cas loci and arrays https://github.com/Russel88/CRISPRCasTyper")
check("an answer's items are read: name, link if it gave one, what it does",
      [(i["title"], i["url"]) for i in P.items(ANSWER)] == [
          ("INPHARED2", "https://github.com/RyanCook94/inphared"), ("PADLOC", "name:padloc"),
          ("CRISPRCasTyper", "https://github.com/Russel88/CRISPRCasTyper")], P.items(ANSWER))
check("a message before the ask is not its answer", P.from_room(ANSWER, "1767699000.0") == ("", 0))
check("a reply in some other thread is not its answer", P.from_room(ANSWER, "1767700100.0", thread="1767600000.0") == ("", 0))
got_line, n = P.from_room(ANSWER, "1767700200.0")
check("GrokBot's answer after the ask lands on the line it was asked for", got_line == line_id and n == 3, (got_line, n))
check("... once: a second message is not taken as the answer again", P.from_room(ANSWER, "1767700300.0") == ("", 0))
_d = P.load(); _d["asked"].append({"at": "x", "line": "L-third", "title": "Prophage induction", "ts": "1767800000.0"}); P.save(_d)
check("a channel message hours after the ask is about something else, not its answer",
      P.from_room(ANSWER, str(1767800000.0 + 4 * 3600)) == ("", 0))
_d = P.load(); _d["asked"].append({"at": "x", "line": "L-third", "title": "Prophage induction", "ts": "1767900000.5",
                                  "thread": "1767899000.0"}); P.save(_d)
check("an ask said inside a thread is answered in that thread", P.from_room(ANSWER, "1767900100.0", thread="1767899000.0")[0] == "L-third")
shown = P.block(shown=10)
check("he is shown them with the line, who found them, and how to find one with no link",
      "INPHARED2 (from GrokBot)" in shown and "https://github.com/RyanCook94/inphared" in shown
      and "no link given: REPOS: PADLOC finds its code" in shown, shown)
check("what he names on the line is answered by what he said there",
      P.spoken(line_id, "PADLOC is the one: it lists retrons per genome; running it next.") == ["PADLOC"])
check("... and only what he named", [f["title"] for f in P.load()["lines"][line_id]["found"] if not f.get("answered")]
      == ["INPHARED2", "CRISPRCasTyper"])
d = P.load(); d["lines"]["L-page"] = {"title": "x", "found": [{"title": "Lytic Selection and Evolution platform | Home",
                                                                "url": "https://lyse.example.org/", "shown": 0, "answered": ""}]}
P.save(d)
check("a page title answers to its own name, without the site's tail",
      P.spoken("L-page", "The Lytic Selection and Evolution platform only runs lysis assays; not for this line.")
      == ["Lytic Selection and Evolution platform | Home"])
_dsrc = open(os.path.join(REPO, "scripts", "dot_channel.py")).read()
check("the channel keeps GrokBot's answer, notes where the ask went, and closes what he names on a line",
      "line_prospect.from_room(" in _dsrc and "line_prospect.asked_in(" in _dsrc and "line_prospect.spoken(" in _dsrc)

# --- the channel ---------------------------------------------------------------------------------------------------
dsrc = open(os.path.join(REPO, "scripts", "dot_channel.py")).read()
check("it is in his context, beside SOMETHING NEW", "prospect_line()" in dsrc and "new_block(), prospect_line()" in dsrc)
check("the search runs from his Lab's own session, beside his lines, not from the Slack tick",
      "line_prospect.prospect()" in open(os.path.join(REPO, "scripts", "chemistry_session.py")).read()
      and "line_prospect.prospect(" not in dsrc)
check("his rules tell him what it is and what to do with it", "WHAT ALREADY EXISTS FOR YOUR LINES is searched for you" in dsrc)
check("the ask rides on his own message in Slack, so he is the one who asks",
      "line_prospect.ask_the_room()" in dsrc and 'text = text.rstrip() + "\\n\\n" + ask' in dsrc)
check("GrokBot is told to answer it", "Once a day the channel asks you what already exists" in
      open(os.path.join(REPO, "docs", "grok-bot", "vintos-skill.md")).read())
check("the deploy installs it", "line_prospect.py" in open(os.path.join(REPO, "scripts", "deploy-atelier.sh")).read())
check("nothing left the machine", not NET, NET)
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
