#!/usr/bin/env python3
"""A stale RW id never lands on other work (Vintos's own ask, 2026-11-03: `_pick` fell through to goal similarity
when the id it was given was not open, so NEXT and WORK DONE naming a closed work moved, or closed, whatever was in
hand instead).

Drop A, open unrelated B, then NEXT and WORK DONE naming A: A stays closed, B is unchanged, and B has its own id.

Scratch workspace; every store room_work writes is repointed there, and every socket is refused.
"""
import os, socket, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="room-work-stale-")
os.environ["HOME"] = HOME
os.environ["SPARK_WORKSPACE"] = os.path.join(HOME, ".vintos", "workspace")
os.environ["VINTOS_SECRETS"] = os.path.join(HOME, "no-secrets")
sys.path.insert(0, os.path.join(REPO, "scripts"))

NET = []
def _no_net(self, *a, **k):
    if self.family != socket.AF_UNIX: NET.append(a)
    raise OSError("this suite reaches nothing")
socket.socket.connect = _no_net

import awaiting_evidence
import room_work as W

R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:300]) if d and not ok else ""))

# the one store room_work writes (the evidence ledger, touched on every close) is the scratch one
check("the evidence ledger room_work writes is in the scratch home",
      str(awaiting_evidence.store().path).startswith(HOME), awaiting_evidence.store().path)
check("sockets are stubbed: connect refuses", socket.socket.connect is _no_net)

st = {}
W.apply(st, "WORK: fold the phage RT locus beside its CRISPR array | done when: a pLDDT is reported", now=100)
a = W.active(st)
_, log, closed = W.apply(st, "WORK DROPPED %s: the locus is not in any assembly we can reach" % a["id"], now=200)
check("A is dropped", closed is a and not W.open_items(st) and a["state"] == "dropped", log)

W.apply(st, "WORK: price a 5 kg load cell for the bench | done when: a price in dollars", now=300)
b = W.active(st)
before = dict(b)
check("B has a distinct id", b and b["id"] != a["id"], (a["id"], b and b["id"]))

text, log, closed = W.apply(st, "NEXT: %s rerun the fold with the longer window\n"
                                "WORK DONE %s: fold.pdb pLDDT 86 across the domain" % (a["id"], a["id"]), now=400)
check("WORK DONE naming A closes nothing", closed is None, (closed, log))
check("B is still open and unchanged", W.open_items(st) == [b] and b == before, (W.open_items(st), before))
check("A stays closed, as dropped", a["state"] == "dropped" and a["closed_at"] == 200
      and not any(w.get("id") == a["id"] for w in W.open_items(st)), a)
check("he is shown there was nothing open by that id to close", "no work in hand to close" in text, text)

# the same line naming B's own id still reaches B
W.apply(st, "NEXT: %s ask Muse for the price" % b["id"], now=500)
check("an id that is open still finds its work", b["next"].startswith(b["id"]), b)

check("nothing was sent: no socket was reached", not NET, NET)
print("\n%d/%d passed" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
