#!/usr/bin/env python3
"""What he reaches for in the Atelier, shown back to him as a pattern (2026-10-01: "I want him to do more than
music and letters from the Atelier"). Scratch HOME; nothing is dialled."""
import importlib.util, json, os, socket, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="atelier-choices-"); os.environ["HOME"] = HOME
NET = []
def _no(self, *a, **k): NET.append(a); raise OSError("this suite reaches nothing")
socket.socket.connect = _no
spec = importlib.util.spec_from_file_location("atelier_visit_choices", os.path.join(REPO, "scripts", "atelier-visit.py"))
AV = importlib.util.module_from_spec(spec); spec.loader.exec_module(AV)
R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:240]) if d and not ok else ""))
check("his choices are kept in the scratch workspace", AV.CHOICES.startswith(HOME), AV.CHOICES)
check("no choices yet, nothing said", AV.choices_line() == "")
os.makedirs(os.path.dirname(AV.CHOICES), exist_ok=True)
for w in ("music", "music", "music", "music"): AV._chose("media", w)
line = AV.choices_line()
check("four songs in a row is said as a pattern, with every shelf he has not opened",
      "music x4" in line and "Not opened lately: quantum, connected tools, lab, forge, stratagem, self review" in line, line)
check("it is offered, not assigned", "They are there if a piece wants them" in line)
AV._chose("shelf", "lab"); AV._chose("media", "image")
line = AV.choices_line()
check("what he does open drops off the list", "lab x1" in line and "image x1" in line and ", lab," not in line, line)
src = open(os.path.join(REPO, "scripts", "atelier-visit.py")).read()
check("the visit records each shelf and medium he chooses, and shows the pattern at the start",
      '_chose("shelf", shelf)' in src and '_chose("media", wanted["kind"])' in src and "+ choices_line())" in src)
check("nothing reached the network", NET == [], NET)
import shutil; shutil.rmtree(HOME, ignore_errors=True)
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
