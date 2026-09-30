#!/usr/bin/env python3
"""The Study's grep finds what is there (2026-09-30).

Basic grep read "tactile|haptic|sensor_reactions" as that literal text, so every search for one of several
words came back empty, and the Forge's studies reported the grep as broken. A scratch HOME holds a copy of
two real modules; nothing is sent anywhere.
"""
import importlib.util, os, shutil, socket, sys, tempfile

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
HOME = tempfile.mkdtemp(prefix="study-grep-")
os.environ["HOME"] = HOME
SC = os.path.join(HOME, ".vintos", "workspace", "scripts"); os.makedirs(SC); os.makedirs(os.path.join(HOME, "Vintos"))
for f in ("sensor_reactions.py", "home_presence.py"):
    shutil.copy(os.path.join(REPO, "scripts", f), SC)

def _no_net(*a, **k): raise OSError("this suite reaches nothing")
socket.socket.connect = _no_net

R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:160]) if d and not ok else ""))

spec = importlib.util.spec_from_file_location("study_chat_grep", os.path.join(REPO, "bin", "study_chat.py"))
S = importlib.util.module_from_spec(spec); spec.loader.exec_module(S)
check("the Study searches only the scratch home", S.ROOTS["scripts"].startswith(HOME), S.ROOTS)

g = S.do_grep("tactile|haptic|sensor_reactions")
check("one of several words: a|b finds b", "no matches" not in g and "scripts/home_presence.py" in g, g)
g = S.do_grep("home_presence\\|world_model")
check("the basic-grep spelling a\\|b still works", "scripts/home_presence.py" in g, g)
g = S.do_grep("observe(")
check("a pattern that is not a valid regex is searched as plain text", "observe(" in g and "no matches" not in g, g)
check("a plain word is found where it is", "scripts/sensor_reactions.py:" in S.do_grep("def observe"))
check("absence is still absence", "no matches" in S.do_grep("zz_not_in_any_file_zz"))
check("nothing reached the network", socket.socket.connect is _no_net)
shutil.rmtree(HOME, ignore_errors=True)
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
