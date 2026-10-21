#!/usr/bin/env python3
"""No generator asks a first question for a relationship no record states (21 October: 19 yes of 303 reviews).

The planner prompt, the sourced-record template and the fresh-protein fallback each told the Lab to ask, in one
question, for a structural feature, a function AND the source-backed relationship between them. The coverage checker
requires a verbatim quote for every part; a curated record lists features and a function but never the link, so the
review said no, and dead_ends() spent the protein. The narrower cannot see this form (no "and how", no "compared to"),
so it is fixed where it is written. The checker itself is unchanged and is asserted unchanged here.
The planner is a stub; scratch HOME; no socket."""
import json, os, re, socket, sys, tempfile, types
HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="lab-answerable-"); os.environ["HOME"] = HOME
os.environ["SPARK_WORKSPACE"] = os.path.join(HOME, ".vintos", "workspace")
NET = []
def _no(self, *a, **k): NET.append(a); raise OSError("this suite reaches nothing")
socket.socket.connect = _no
sys.path.insert(0, os.path.join(REPO, "scripts"))
import chemistry_lab as C
def _never(*a, **k): raise AssertionError("no model call in this suite")
C._ask = _never
C.urllib.request.urlopen = _never
R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:400]) if d and not ok else ""))
check("the Lab's stores are scratch", C.ROOT.startswith(HOME) and C.NOTEBOOK.startswith(HOME))
check("the model and the network are stubbed", C._ask is _never and socket.socket.connect is _no)

# The relationship asked as part of a first question, in the words the three generators used.
ASKS_LINK = re.compile(r"(?:and|,)\s+(?:any |the )?source-backed relationship|relationships? between (?:those|these|them|the)", re.I)
SRC = open(os.path.join(REPO, "scripts", "chemistry_lab.py")).read()

print("--- the sourced-record template asks what a record lists ---")
q = C._record_connection_question("Catalase", "P21179")
check("it names structural features and a function", "structural features" in q and "function" in q, q)
check("it does not ask for the relationship", not ASKS_LINK.search(q) and "relationship" not in q, q)
check("it is still one ask to the narrower, left as written", C._narrow({"question": q})["question"] == q)
check("it still opens a claim line (structure and function are named)", C._relational_question(q))

print("--- the fresh-protein fallback asks the same ---")
seen = []
C._plan = lambda system, prompt: (seen.append(prompt), {"browse_lane": "protein", "question": "x"})[1]
C._existing_model_read = lambda inq: inq
C._held_to_plan = lambda system, task, inq, value, lean, step, repeats, spent=None, replan=True: (inq, value)
C._fresh_free_inquiry(types.SimpleNamespace(repeat=lambda inq: None), {"subjects": []})
check("its planner prompt was built", seen, seen)
check("its prompt does not ask for the relationship in the first question",
      seen and not re.search(r"Ask for .{0,120}relationship between those features", seen[0]), seen[:1])

print("--- the main planner prompt ---")
o = SRC[SRC.index("def _orient("):SRC.index("def _atlas_text(")]
check("it no longer orders three claim types into one question", "Include three claim types" not in o)
check("it says the relationship is asked later, with a source that states it",
      "never asked whole" in o and "asked later with a source that states it" in o)
check("it still tells the planner to ask one thing", "Ask ONE thing its sources can answer whole" in o)

print("--- the scientific checks are untouched ---")
check("the coverage checker still requires every relationship the question asks to be covered",
      "domain or relationship in the question must be covered" in SRC)
check("and verbatim quotes for every requirement",
      "all original requirements must be supported by verbatim quotes" in SRC)
check("an answered review is still only a yes", C.review_answered({"answers_question": "no: missing"}) is False
      and C.review_answered({"answers_question": "yes: ok"}) is True)
check("nothing reached the network", not NET)
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
