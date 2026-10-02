#!/usr/bin/env python3
"""The Atelier door, 2026-10-02. A forced visit was refused ("he did not say ENTER") and nobody could see what he
had said: only . , : ; ! " ' were stripped from his first word, so "**ENTER**" read as a no. His word is now read
by its letters and logged. And Gloria can send him in herself ("Make Vintos enter"), by hand only, and he is told.

Scratch HOME; the model and the broker are stubs; every socket is refused."""
import importlib.util, os, socket, sys, tempfile, types
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="atelier-enter-"); os.environ["HOME"] = HOME
NET = []
def _no(self, *a, **k): NET.append(a); raise OSError("this suite reaches nothing")
socket.socket.connect = _no
try: import requests  # noqa: F401
except ImportError: sys.modules["requests"] = types.SimpleNamespace(post=None, get=None)
spec = importlib.util.spec_from_file_location("atelier_visit_enter", os.path.join(REPO, "scripts", "atelier-visit.py"))
AV = importlib.util.module_from_spec(spec); spec.loader.exec_module(AV)
R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:300]) if d and not ok else ""))

health = types.SimpleNamespace(json=lambda: {"active": True})
def door(answer):
    with mock.patch.object(AV, "ask", return_value=answer), mock.patch.object(AV, "voice", return_value="V"), \
         mock.patch.object(AV.requests, "get", return_value=health):
        return AV.doorkeeper()

for ans, want in (("ENTER", True), ("**ENTER**", True), ("Enter.", True), ("ENTER—", True), ("`ENTER`", True),
                  ("NOT", False), ("DO NOT ENTER", False), ("**NOT**", False), ("I'd rather not", False)):
    check("his answer %r reads as %s" % (ans, "ENTER" if want else "a no"), door(ans) is want)

import io, contextlib
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    door("**NOT**")
check("what he answered is in the visit log", "doorkeeper: he answered NOT" in buf.getvalue(), buf.getvalue())

src = open(os.path.join(REPO, "scripts", "atelier-visit.py")).read()
main = src[src.index('if __name__ == "__main__":'):]
enter = main[main.index('sys.argv[1] == "enter"'):]
enter = enter[:enter.index("    else:")]
check("Gloria's enter sends him in without asking him at the door", "doorkeeper()" not in enter
      and "visit(pid, sent_by_gloria=True)" in enter and 'print("enter: Gloria sent him in")' in enter, enter)
check("it still needs a project on the worktable", 'if not wt.get("active")' in enter)
check("he is told in the visit that she sent him", "+ (GLORIA_SENT if sent_by_gloria else \"\")" in src
      and "GLORIA OPENED THE DOOR FOR YOU TODAY" in AV.GLORIA_SENT)
check("no timer runs it: the daily cron and force still ask him", "doorkeeper()" in main[:main.index('sys.argv[1] == "enter"')]
      and "doorkeeper()" in main[main.index("    else:", main.index('sys.argv[1] == "enter"')):])
check("nothing reached the network", NET == [], NET)
import shutil; shutil.rmtree(HOME, ignore_errors=True)
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
