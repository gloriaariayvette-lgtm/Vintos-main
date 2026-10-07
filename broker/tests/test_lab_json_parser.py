#!/usr/bin/env python3
"""His Lab's JSON parser crashed 74 times in one day and took every reflect tick with it (Vintos found it himself,
2026-10-04: "that's the parser in scripts/chemistry_lab.py around 657, not a fold").

A local model truncates and sometimes writes a backslash it does not mean as an escape. The parser took the first
"{" to the last "}" and gave up on anything else. It repairs those two now, and a real non-answer fails with the
an opaque evidence ID on the error; model text is retained only in protected diagnostics.

Pure parsing: this suite loads the module into a scratch HOME, calls no model and reaches nothing.
"""
import importlib.util, json, os, socket, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="lab-json-")
os.environ["HOME"] = HOME
os.environ["SPARK_WORKSPACE"] = os.path.join(HOME, ".vintos", "workspace")
sys.path.insert(0, os.path.join(REPO, "scripts"))

NET = []
def _no_net(self, *a, **k):
    if self.family != socket.AF_UNIX: NET.append(a)
    raise OSError("this suite reaches nothing")
socket.socket.connect = _no_net

spec = importlib.util.spec_from_file_location("chemistry_lab_json", os.path.join(REPO, "scripts", "chemistry_lab.py"))
LAB = importlib.util.module_from_spec(spec); spec.loader.exec_module(LAB)

R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:300]) if d and not ok else ""))

check("it parses in the scratch workspace", LAB.ROOT.startswith(HOME), LAB.ROOT)

# --- what already worked keeps working ---------------------------------------------------------------------
check("a plain object", LAB._json_object('{"a": "b"}') == {"a": "b"})
check("a fenced one", LAB._json_object('```json\n{"a": "b"}\n```') == {"a": "b"})
check("one with the model talking around it", LAB._json_object('Sure: {"a": "b"} hope that helps') == {"a": "b"})
real = {"attention": "the RT locus", "factual_observation": "two loci within 2 kb of an array",
        "speculative_reading": "", "next_question": "which strand?"}
check("a whole reflection", LAB._json_object(json.dumps(real)) == real)

# --- the two breakages he actually saw -----------------------------------------------------------------------
check("cut off inside a string", LAB._json_object('{"attention": "the RT locus sits')
      == {"attention": "the RT locus sits"})
check("cut off after a key", LAB._json_object('{"attention": "x", "next_question":')
      == {"attention": "x", "next_question": ""})
check("cut off after a comma", LAB._json_object('{"attention": "x",') == {"attention": "x"})
check("cut off mid-key", LAB._json_object('{"attention": "x", "next_ques') == {"attention": "x"})
check("cut off inside a list", LAB._json_object('{"loci": [1, 2') == {"loci": [1, 2]})
check("cut off inside a nested object", LAB._json_object('{"plan": {"experiment": "fold')
      == {"plan": {"experiment": "fold"}})
check("a backslash it did not mean as an escape",
      LAB._json_object(r'{"path": "C:\Users\gloria"}') == {"path": r"C:\Users\gloria"})
check("... and one in a truncated reply too", LAB._json_object(r'{"path": "C:\Users\gl')
      == {"path": r"C:\Users\gl"})
check("an escape it did mean is left alone", LAB._json_object('{"a": "line\\none\\u00e9"}') == {"a": "line\none\u00e9"})

# --- a real non-answer still fails, and says what came back ----------------------------------------------------
for bad, what in (("", "nothing at all"), ("I cannot answer that.", "prose"), ("[1, 2, 3]", "a list, not an object")):
    try:
        LAB._json_object(bad); raise AssertionError("parsed " + what)
    except ValueError as exc:
        check("a reply that is %s is refused" % what, "no " in str(exc).lower() and "JSON" in str(exc), str(exc))
try:
    LAB._json_object("I could not answer; the context was too long.")
except ValueError as exc:
    said = str(exc)
check("errors identify evidence without exposing model text", "evidence=" in said and "the context was too long" not in said, said)
long_raw = '{"attention": "' + "x" * 4000
try:
    LAB._json_object(long_raw, keep=50)
except ValueError:
    said = "parsed"
check("a long truncated reply is repaired, not reported", said == "parsed" or LAB._json_object(long_raw)["attention"])

check("nothing left the machine", not NET, NET)
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
