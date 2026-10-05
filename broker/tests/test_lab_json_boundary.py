#!/usr/bin/env python3
"""Strict JSON boundary in the Lab's parser (Vintos, from the Forge, SK-330c8fa6).

Gemma writes its object and then sometimes keeps going: a second object, or a sentence with braces in it. The
parser took the first "{" to the LAST "}" and so handed json two things at once; 'Extra data' 172 times. It now
decodes exactly one complete object from the opening brace and ignores the tail, and the truncation repairs
that already worked still work after it.

Pure parsing: scratch HOME, the model call stubbed to raise, the network stubbed to raise, both asserted.
"""
import importlib.util, json, os, socket, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="lab-json-boundary-")
os.environ["HOME"] = HOME
os.environ["SPARK_WORKSPACE"] = os.path.join(HOME, ".vintos", "workspace")
sys.path.insert(0, os.path.join(REPO, "scripts"))

NET = []
def _no_net(self, *a, **k):
    if self.family != socket.AF_UNIX: NET.append(a)
    raise OSError("this suite reaches nothing")
socket.socket.connect = _no_net

spec = importlib.util.spec_from_file_location("chemistry_lab_json_boundary", os.path.join(REPO, "scripts", "chemistry_lab.py"))
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

# A reply the way Gemma actually shapes it: pretty-printed, twenty-five lines, then more after the object.
first = {"browse_lane": "protein", "uniprot_query": "gene:KaiC AND organism_id:1140",
         "question": "Does the KaiC hexamer interface recur outside cyanobacteria?", "why_now": "a shape I keep seeing",
         "source_query": {"source": "pdb", "entry_id": "1TF7"}, "plugin_query": None,
         "material_terms": ["KaiC", "Synechococcus elongatus", "hexamer", "ATPase"],
         "line_id": None, "new_line": {"title": "circadian folds", "question": "what recurs?", "why": "curiosity"}}
pretty = json.dumps(first, indent=2)
check("the fixture is the shape he saw: a pretty object of about twenty-five lines", 20 <= pretty.count("\n") + 1 <= 30, pretty.count("\n") + 1)

second = {"note": "and here is an alternative", "question": "something else"}
check("a second object after the first is ignored, the first is the answer",
      LAB._json_object(pretty + "\n" + json.dumps(second)) == first)
check("prose with braces after the object is ignored",
      LAB._json_object(pretty + "\n\nI chose {this} because the {interface} is well sourced.") == first)
check("a fenced object with a tail outside the fence",
      LAB._json_object("```json\n" + pretty + "\n```\nHope that helps! {") == first)
check("a second object that is itself cut off still leaves the first whole",
      LAB._json_object(pretty + '\n{"note": "and the') == first)
check("a stray backslash in the first object does not let the tail win",
      LAB._json_object('{"path": "C:\\Users\\gloria"}\n{"x": 1}') == {"path": "C:\\Users\\gloria"})

# --- what the parser already repaired is still repaired after the strict pass ----------------------------------
check("cut off inside a string", LAB._json_object('{"attention": "the RT locus sits') == {"attention": "the RT locus sits"})
check("cut off after a key", LAB._json_object('{"attention": "x", "next_question":') == {"attention": "x", "next_question": ""})
check("the model talking around a whole object", LAB._json_object('Sure: {"a": "b"} hope that helps') == {"a": "b"})
for bad, what in (("", "nothing at all"), ("I cannot answer that.", "prose"), ("[1, 2, 3]", "a list, not an object")):
    try:
        LAB._json_object(bad); check("a reply that is %s is refused" % what, False, "parsed")
    except ValueError as exc:
        check("a reply that is %s is refused" % what, "no " in str(exc).lower() and "JSON" in str(exc), str(exc))

check("no model was called", not ASKED, ASKED)
check("nothing left the machine", not NET, NET)
check("nothing was written outside the scratch workspace", not os.path.exists(os.path.expanduser("~/.vintos/workspace/memory/chemistry-lab/faults.jsonl")) or os.path.expanduser("~").startswith(HOME))
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
