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

# --- the channel ---------------------------------------------------------------------------------------------------
dsrc = open(os.path.join(REPO, "scripts", "dot_channel.py")).read()
check("it is in his context, beside SOMETHING NEW", "prospect_line()" in dsrc and "new_block(), prospect_line()" in dsrc)
check("the search runs from his Lab's own session, beside his lines, not from the Slack tick",
      "line_prospect.prospect()" in open(os.path.join(REPO, "scripts", "chemistry_session.py")).read()
      and "line_prospect.prospect(" not in dsrc)
check("his rules tell him what it is and what to do with it", "WHAT ALREADY EXISTS FOR YOUR LINES is searched for you" in dsrc)
check("the deploy installs it", "line_prospect.py" in open(os.path.join(REPO, "scripts", "deploy-atelier.sh")).read())
check("nothing left the machine", not NET, NET)
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
