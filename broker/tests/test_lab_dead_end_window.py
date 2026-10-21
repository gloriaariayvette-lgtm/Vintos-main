#!/usr/bin/env python3
"""A subject is spent because asking it lately found nothing, never because an answer has been a long time coming
(Gloria, 22 October: "week three now of you not fixing the Lab". Her probe of 24 hours: 362 inquiries, 252 refused
before a source was called, 295 passes with nothing eligible, and 19 of 303 reviews answering. dead_ends() walked back
from the newest row until a review that answered; with reviews almost never answering it reached the whole notebook
tail, so every gene queried for days was marked spent, each re-stamped for another day by the next pass - and a spent
subject cannot be retrieved for, so the run could never earn the answer that would end it).

Scratch HOME and workspace; no model is asked; sockets are refused."""
import json, os, socket, sys, tempfile
from datetime import datetime, timedelta, timezone
HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="lab-dead-end-"); os.environ["HOME"] = HOME
os.environ["SPARK_WORKSPACE"] = os.path.join(HOME, ".vintos", "workspace")
NET = []
def _no(self, *a, **k): NET.append(a); raise OSError("this suite reaches nothing")
socket.socket.connect = _no
sys.path.insert(0, os.path.join(REPO, "scripts"))
import chemistry_lab as C
C._ask = lambda *a, **k: (_ for _ in ()).throw(AssertionError("no model in this suite"))
R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + ("" if ok else "  ->  %r" % (str(d)[:400],)))
check("the Lab's stores are scratch", C.ROOT.startswith(HOME) and C.SPENT.startswith(HOME))

NOW = datetime(2026, 10, 22, 9, 0, tzinfo=timezone.utc)
T = NOW.timestamp()
def at(hours_ago): return (NOW - timedelta(hours=hours_ago)).isoformat()
def asked(hours_ago, gene):
    return {"at": at(hours_ago), "kind": "inquiry", "inquiry": {
        "question": "What are the structural hallmarks of human %s?" % gene,
        "uniprot_query": "gene:%s AND organism_id:9606" % gene}}
def review(hours_ago, verdict):
    return {"at": at(hours_ago), "kind": "reflection", "answers_question": verdict}

# Three weeks of asking with no review that answered: the genes of days ago must not still be spent.
old = [r for h in range(300, 8, -1) for r in (asked(h, "KAIC"), asked(h, "OMPA"), review(h, "no: not established"))]
recent = [asked(5, "SLC26A4"), asked(4, "SLC26A4"), asked(3, "SLC26A4"), review(3, "no: not established")]
out = C.dead_ends(old + recent, now=T)
check("only the last few hours of asking make a run", out["count"] == len(recent) - 1, out)
check("the subject asked in those hours is spent", "SLC26A4" in out["subjects"], out["subjects"])
check("a gene last asked days ago is not", not {"KAIC", "OMPA"} & set(out["subjects"]), out["subjects"])

before = C.dead_ends(old + recent, now=T)["subjects"]
check("and it stays that way as the drought goes on: the run does not grow with it",
      C.dead_ends([asked(h, "KAIC") for h in range(900, 300, -1)] + old + recent, now=T)["subjects"] == before)

# A review that answered still ends a run inside the window.
out = C.dead_ends([asked(5, "TXN"), review(4, "yes: the records establish it"), asked(3, "GCLC"), asked(2, "GCLC")], now=T)
check("an answered review still ends the run where it falls", out["count"] == 2 and "TXN" not in out["subjects"], out)
check("a run shorter than DEAD_END_RUN names nothing",
      C.dead_ends([asked(2, "PRKCA"), asked(1, "PRKCA")], now=T)["subjects"] == [], C.dead_ends([asked(2, "PRKCA")], now=T))
check("rows with no timestamp are still read, not treated as ancient",
      "FUS" in C.dead_ends([{"kind": "inquiry", "inquiry": {"uniprot_query": "gene:FUS"}}] * 3, now=T)["subjects"])

# The hold itself expires: the subject leaves the window, so the next day's pass does not re-stamp it.
C.remember_spent(["SLC26A4"], now=T - 25 * 3600)
check("a day-old hold has expired", "SLC26A4" not in C.spent_subjects(now=T))
C.remember_spent(C.dead_ends(old + [asked(30, "SLC26A4")] * 3, now=T)["subjects"], now=T)
check("and a pass today does not put it back when it was not asked today",
      "SLC26A4" not in C.spent_subjects(now=T), C.spent_subjects(now=T))
src = open(os.path.join(REPO, "scripts", "chemistry_lab.py")).read()
check("the window is bounded in the module, not only here", "DEAD_END_WINDOW_H" in src and "stamp < cutoff" in src)
check("nothing reached the network", not NET)
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
