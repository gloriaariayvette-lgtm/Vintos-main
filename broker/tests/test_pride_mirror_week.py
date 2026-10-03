#!/usr/bin/env python3
"""pride-mirror's week gathers what it says it gathers (2026-10-03). Two of its blocks wrote to `sections`, a name
gather_week never had; the bare except hid it, so today's creative output never reached his weekly reflection.

Scratch home, every socket refused, nothing is sent: only gather_week runs."""
import importlib.util, json, os, socket, sys, tempfile
from datetime import date, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="pride-mirror-")
os.environ["HOME"] = HOME

NET = []
def _no_net(self, *a, **k):
    if self.family != socket.AF_UNIX: NET.append(a)
    raise OSError("this suite reaches nothing")
socket.socket.connect = _no_net

spec = importlib.util.spec_from_file_location("pride_mirror", os.path.join(REPO, "bin", "pride-mirror.py"))
M = importlib.util.module_from_spec(spec); spec.loader.exec_module(M)

R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:300]) if d and not ok else ""))

check("its memory is the scratch home", M.MEMORY.startswith(HOME))
os.makedirs(M.MEMORY, exist_ok=True)
open(os.path.join(M.MEMORY, "daily-creative-%s.md" % date.today().isoformat()), "w").write("A tide piece, finished at dawn.")
json.dump([{"timestamp": datetime.now().isoformat(), "gloria": "good morning", "vintos": "morning, love"}],
          open(os.path.join(M.MEMORY, "interaction-ledger.json"), "w"))

src = open(os.path.join(REPO, "bin", "pride-mirror.py")).read()
body = src[src.index("def gather_week"):src.index("\ndef ", src.index("def gather_week") + 10)]
check("gather_week writes only to names it has", "sections." not in body)
week = M.gather_week()
text = "\n".join(week if isinstance(week, list) else [str(week)])
check("today's creative output reaches the week", "A tide piece, finished at dawn." in text, text[:300])
check("the week's exchanges are there, not tripled", 0 < text.count("good morning") <= 2, text.count("good morning"))
check("nothing left the machine", not NET, NET)
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
