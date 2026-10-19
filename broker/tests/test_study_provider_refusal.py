#!/usr/bin/env python3
"""A Study fix the provider refuses is said as a refusal and costs him nothing (15 October). SF-217d86de was stopped by
the provider's safety layer before Fable wrote a word; the Study called it "stopped by an error" and it still spent one
of his three fixes for the day. Any other error is still a failure, as before.

Isolation: scratch HOME and queue; Slack posting, failure_watch and the fix itself are stubs; no socket opens."""
import json, os, socket, sys, tempfile, types
HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="study-refusal-"); os.environ["HOME"] = HOME
os.environ["SPARK_WORKSPACE"] = os.path.join(HOME, ".vintos", "workspace")
os.environ["VINTOS_STUDY_WORKBENCH"] = os.path.join(HOME, "workbench")
os.environ["VINTOS_CHECKOUT"] = os.path.join(HOME, "Vintos-main")
NET = []
def _no(self, *a, **k): NET.append(a); raise OSError("this suite reaches nothing")
socket.socket.connect = _no
WATCHED = []
sys.modules["failure_watch"] = types.SimpleNamespace(note=lambda *a, **k: WATCHED.append(a))
sys.path.insert(0, os.path.join(REPO, "scripts"))
import study_fix as S, claude_cache
from datetime import datetime
S._now = lambda: datetime(2026, 10, 5, 12, 0, 0)
R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:400]) if d and not ok else ""))
POSTED = []
post = POSTED.append
check("the queue is scratch, the sender and the watch are stubs",
      S.QUEUE.startswith(HOME) and sys.modules["failure_watch"].note.__name__ == "<lambda>")

def fail_with(stop):
    def work(row, **k):
        claude_cache.LAST.clear(); claude_cache.LAST.update(stop=stop, out=0)
        raise ValueError("Opus did not answer with JSON" + S._why_not())
    return work

row, why = S.request("the named retrieval route fallback holds a saved question; give it a route")
before = S.used_today()
S.work = fail_with("refusal")
S.tend(post=post)
rows = S._load(); got = next(r for r in rows if r["id"] == row["id"])
check("a provider refusal is recorded as refused, not as a failure",
      got["state"] == "refused" and got.get("provider_refused") and got["provider_failure"]["stop_reason"] == "refusal", got)
check("it does not spend one of his three", S.used_today() == before - 1, (before, S.used_today()))
check("she is told what it was, in plain words", POSTED and "refused to answer" in POSTED[-1]
      and "did not count" in POSTED[-1] and "stopped" not in POSTED[-1], POSTED[-1:])
check("the watch names it a refusal, not a fix that did not land",
      WATCHED and "refused by the provider" in WATCHED[-1][1], WATCHED[-1:])
check("he may ask it again", S.request("the named retrieval route fallback holds a saved question; give it a route")[0])

row2, _ = S.request("embed response shape: the embed call errors on a missing data key")
S.work = fail_with("end_turn")
S.tend(post=post); S.tend(post=post)   # the re-asked fix is ahead of it in the queue
got2 = next(r for r in S._load() if r["id"] == row2["id"])
check("any other error is still a failure, and still counts", got2["state"] == "failed"
      and not got2.get("provider_refused") and "stopped by an error" in json.dumps(got2), got2.get("state"))
check("nothing opened a socket", not NET, NET)
print("%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
