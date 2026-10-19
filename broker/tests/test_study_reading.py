#!/usr/bin/env python3
"""The Study can read the code a fix lives in (19 October: three fixes to chemistry_lab.py's hold code were declined,
each "my read was cut off" - a whole file stops at 60,000 characters and that file is 334,000 - and a grep for the
callers came back "(no match)" when the pattern was one grep could not read).

Scratch workbench; no writer is called; nothing is sent."""
import os, socket, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="study-reading-"); os.environ["HOME"] = HOME
os.environ["SPARK_WORKSPACE"] = os.path.join(HOME, "workspace")
os.environ["VINTOS_STUDY_WORKBENCH"] = os.path.join(HOME, "workbench")
NET = []
def _no(self, *a, **k): NET.append(a); raise OSError("this suite reaches nothing")
socket.socket.connect = _no
sys.path.insert(0, os.path.join(REPO, "scripts"))
import study_fix as S
R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + ("" if ok else "  ->  %r" % (str(d)[:400],)))
ROOT = S.WORKBENCH; os.makedirs(os.path.join(ROOT, "scripts"))
check("the workbench is scratch", ROOT.startswith(HOME))

lines = ["# filler line %d %s" % (i, "x" * 60) for i in range(1, 5001)]
lines[4199] = "def _hold_owner(inquiry, strict=True):"
lines[4200] = "    raise ValueError('question hold lacks a named retrieval route')"
open(os.path.join(ROOT, "scripts", "lab.py"), "w").write("\n".join(lines) + "\n")

whole = S.read_for({"read": ["scripts/lab.py"]}, ROOT)
check("a long file read whole stops, and says where and how to read on",
      "_hold_owner" not in whole and "of 5000." in whole and '"scripts/lab.py:START-END"' in whole, whole[-300:])
part = S.read_for({"read": ["scripts/lab.py:4195-4205"]}, ROOT)
check("a line range reaches code deep in the file, numbered",
      "4200: def _hold_owner(inquiry, strict=True):" in part and "4201:     raise ValueError" in part
      and "4194:" not in part and "4206:" not in part, part)
big = S.read_for({"read": ["scripts/lab.py:1-5000"]}, ROOT)
check("a range is bounded (800 lines at most)", "800: " in big and "801: " not in big, big[-200:])
check("a range outside the workbench is refused", "(no such file)" in S.read_for({"read": ["../../etc/passwd:1-5"]}, ROOT))

g = S.read_for({"grep": [r"\b_hold_owner\(\w+"]}, ROOT)
check("a Perl-style search finds the code", "scripts/lab.py:4200:" in g, g)
g = S.read_for({"grep": ["_hold_owner(inquiry"]}, ROOT)
check("a pattern grep cannot read as a regex is tried literally", "scripts/lab.py:4200:" in g, g)
check("the writer is told it can ask for lines", "path:START-END" in S.SYSTEM)
check("nothing reached the network", not NET)
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
