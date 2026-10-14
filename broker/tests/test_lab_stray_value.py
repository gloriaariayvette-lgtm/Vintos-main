#!/usr/bin/env python3
"""A bare value on its own line inside the Lab's JSON (Vintos, from the Forge, SK-634430cb).

Gemma wrote a pair, then a line that was only "0,", then the next pair, and was cut off mid-string. The truncation
repairs closed what was open but left the stray line, so json refused it and the Lab logged ValueError 214 times.
The parser now drops a bare value where a key belongs, and only there: an array printed one item per line keeps
its items.

Pure parsing: scratch HOME, the model call stubbed to raise, the network stubbed to raise, both asserted.
"""
import importlib.util, json, os, socket, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="lab-json-stray-")
os.environ["HOME"] = HOME
os.environ["SPARK_WORKSPACE"] = os.path.join(HOME, ".vintos", "workspace")
sys.path.insert(0, os.path.join(REPO, "scripts"))

NET = []
def _no_net(self, *a, **k):
    if self.family != socket.AF_UNIX: NET.append(a)
    raise OSError("this suite reaches nothing")
socket.socket.connect = _no_net

spec = importlib.util.spec_from_file_location("chemistry_lab_json_stray", os.path.join(REPO, "scripts", "chemistry_lab.py"))
LAB = importlib.util.module_from_spec(spec); spec.loader.exec_module(LAB)

ASKED = []
def _no_ask(*a, **k):
    ASKED.append(a[:1]); raise AssertionError("this suite calls no model")
LAB._ask = _no_ask

R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:300]) if d and not ok else ""))

check("the module writes only below the scratch workspace", LAB.ROOT.startswith(HOME) and LAB.FAULTS.startswith(HOME), LAB.ROOT)
check("the model call is a stub", LAB._ask is _no_ask)

# The reply the Forge quoted: fenced, a stray "0," line between two pairs, cut off inside a string.
seen = ('```json\n{\n "browse_lane": "protein",\n "uniprot_query": "gene:LDLR AND organism_id:9606",\n0,\n'
        ' "question": "What is the specific chromatin')
try:
    got = LAB._json_object(seen)
except ValueError as exc:
    got = str(exc)
check("the reply he saw is recovered, not refused", isinstance(got, dict), got)
check("... with the pairs around the stray line intact",
      isinstance(got, dict) and got.get("browse_lane") == "protein"
      and got.get("uniprot_query") == "gene:LDLR AND organism_id:9606"
      and str(got.get("question", "")).startswith("What is the specific chromatin"), got)

whole = '{\n "a": 1,\n0,\n "b": "x"\n}'
check("a stray line in a complete object", LAB._json_object(whole) == {"a": 1, "b": "x"})
check("a stray line before the closing brace", LAB._json_object('{\n "a": 1,\n"orphan"\n}') == {"a": 1})

# An array printed one item per line is not a row of stray values.
pretty = json.dumps({"material_terms": ["KaiC", "hexamer", 3, True, None], "question": "q"}, indent=2)
check("array items on their own lines are kept",
      LAB._json_object(pretty) == {"material_terms": ["KaiC", "hexamer", 3, True, None], "question": "q"})
check("... and with a stray line in the object around them",
      LAB._json_object(pretty.replace('  "question"', '  0,\n  "question"'))
      == {"material_terms": ["KaiC", "hexamer", 3, True, None], "question": "q"})

# A real non-answer is still refused.
for bad, what in (("", "nothing at all"), ("I cannot answer that.", "prose"), ("[1, 2, 3]", "a list, not an object")):
    try:
        LAB._json_object(bad); check("a reply that is %s is refused" % what, False, "parsed")
    except ValueError as exc:
        check("a reply that is %s is refused" % what, "no " in str(exc).lower() and "JSON" in str(exc), str(exc))

check("no model was called", not ASKED, ASKED)
check("nothing left the machine", not NET, NET)
check("nothing was written outside the scratch workspace", os.path.expanduser("~").startswith(HOME))
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
